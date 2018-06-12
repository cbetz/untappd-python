#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# (c) 2013 Chris Betz
import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())

try:
    import simplejson as json
except ImportError:
    import json

import inspect
import math
import time

try:
    import urllib.parse as urllib
except ImportError:
    import urllib

from builtins import range

# 3rd party libraries that might not be present during initial install
#  but we need to import for the version #
try:
    import httplib2
    import poster
except ImportError:
    pass

__version__ = 0.2
__author__ = u'Christopher Betz'

AUTH_ENDPOINT = 'https://untappd.com/oauth/authenticate'
TOKEN_ENDPOINT = 'https://untappd.com/oauth/authorize/'
API_ENDPOINT = 'https://api.untappd.com/v4'

# Number of times to retry http requests
NUM_REQUEST_RETRIES = 3

# Max number of sub-requests per multi request
MAX_MULTI_REQUESTS = 5

# Keyworded Arguments passed to the httplib2.Http() request
HTTP_KWARGS = {}


# Generic untappd exception
class UntappdException(Exception): pass
# Specific exceptions
class InvalidAuth(UntappdException): pass

ERROR_TYPES = {
    'invalid_auth': InvalidAuth
}

class Untappd(object):
    """Untappd V4 API wrapper"""

    def __init__(self, client_id=None, client_secret=None, access_token=None, redirect_url=None,):
        """Sets up the api object"""
        # Set up OAuth
        self.oauth = self.OAuth(client_id, client_secret, redirect_url)
        # Set up endpoints
        self.base_requester = self.Requester(client_id, client_secret, access_token)
        # Dynamically enable endpoints
        self._attach_endpoints()

    def _attach_endpoints(self):
        """Dynamically attach endpoint callables to this client"""
        for name, endpoint in inspect.getmembers(self):
            if inspect.isclass(endpoint) and issubclass(endpoint, self._Endpoint) and (endpoint is not self._Endpoint):
                endpoint_instance = endpoint(self.base_requester)
                setattr(self, endpoint_instance.endpoint, endpoint_instance)

    def set_access_token(self, access_token):
        """Update the access token to use"""
        self.base_requester.set_token(access_token)

    class OAuth(object):
        """Handles OAuth authentication procedures and helps retrieve tokens"""
        def __init__(self, client_id, client_secret, redirect_url):
            self.client_id = client_id
            self.client_secret = client_secret
            self.redirect_url = redirect_url

        def auth_url(self):
            """Gets the url a user needs to access to give up a user token"""
            data = {
                'client_id': self.client_id,
                'response_type': u'code',
                'redirect_url': self.redirect_url,
            }
            return '{AUTH_ENDPOINT}?{params}'.format(
                AUTH_ENDPOINT=AUTH_ENDPOINT,
                params=urllib.urlencode(data))

        def get_token(self, code):
            """Gets the auth token from a user's response"""
            if not code:
                logging.error(u'Code not provided')
                return None
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': u'authorization_code',
                'redirect_url': self.redirect_url,
                'code': unicode(code),
            }
            # Build the token uri to request
            url = u'{TOKEN_ENDPOINT}?{params}'.format(
                TOKEN_ENDPOINT=TOKEN_ENDPOINT,
                params=urllib.urlencode(data))
            logging.debug(u'GET: {0}'.format(url))
            # Get the response from the token uri and attempt to parse
            response = _request_with_retry(url)
            return response.get('response').get('access_token')


    class Requester(object):
        """Api requesting object"""
        def __init__(self, client_id=None, client_secret=None, access_token=None):
            """Sets up the api object"""
            self.client_id = client_id
            self.client_secret = client_secret
            self.set_token(access_token)
            self.multi_requests = list()

        def set_token(self, access_token):
            """Set the OAuth token for this requester"""
            self.access_token = access_token
            self.userless = not bool(access_token) # Userless if no access_token

        def GET(self, path, params={}, **kwargs):
            """GET request that returns processed data"""
            params = self._enrich_params(params)
            url = '{API_ENDPOINT}{path}?{params}'.format(
                API_ENDPOINT=API_ENDPOINT,
                path=path,
                params=urllib.urlencode(params)
            )
            print(url)
            return self._request(url)

        def POST(self, path, params={}):
            """POST request that returns processed data"""
            params = self._enrich_params(params)
            url = '{API_ENDPOINT}{path}'.format(
                API_ENDPOINT=API_ENDPOINT,
                path=path
            )
            return self._request(url, params)

        def _enrich_params(self, params):
            """Enrich the params dict"""
            if self.userless:
                params['client_id'] = self.client_id
                params['client_secret'] = self.client_secret
            else:
                params['access_token'] = self.access_token
            return params

        def _request(self, url, data=None):
            """Performs the passed request and returns meaningful data"""
            headers = {}
            logging.debug(u'{method} url: {url} headers:{headers} data:{data}'.format(
                method='POST' if data else 'GET',
                url=url,
                headers=headers,
                data=u'* {0}'.format(data) if data else u''))
            return _request_with_retry(url, headers, data)['response']


    class _Endpoint(object):
        """Generic endpoint class"""
        def __init__(self, requester):
            """Stores the request function for retrieving data"""
            self.requester = requester

        def __call__(self, identity):
            return self.GET('info/{id}'.format(id=identity))

        def search(self, query, *args, **kwargs):
            if not self.searchable:
                error_message = u'This Untappd API endpoint is not searchable'
                logging.error(error_message)
                raise UntappdException(error_message)
            params = {'q' : query}
            if kwargs and self.search_options:
                for option in self.search_options:
                    if option in kwargs:
                        params[option] = kwargs[option]
            return self.GET('search', params=params, reverse_path=True)

        def _expanded_path(self, path=None, reverse_path=False):
            """Gets the expanded path, given this endpoint"""
            if reverse_path:
                parts = (path, self.endpoint)
            else:
                parts = (self.endpoint, path)
            return '/{expanded_path}'.format(
                expanded_path='/'.join(p for p in parts if p)
            )

        def GET(self, path=None, *args, **kwargs):
            """Use the requester to get the data"""
            return self.requester.GET(self._expanded_path(path, kwargs.pop('reverse_path', False)), *args, **kwargs)

        def POST(self, path=None, *args, **kwargs):
            """Use the requester to post the data"""
            return self.requester.POST(self._expanded_path(path, kwargs.pop('reverse_path', False)), *args, **kwargs)

    class Beer(_Endpoint):
        endpoint = 'beer'
        searchable = True
        search_options = ('offset', 'limit', 'sort')

    class User(_Endpoint):
        endpoint = 'user'
        searchable = False

    class Venue(_Endpoint):
        endpoint = 'venue'
        searchable = False

    class Brewery(_Endpoint):
        endpoint = 'brewery'
        searchable = True
        search_options = ('offset', 'limit')

"""
Network helper functions
"""
def _request_with_retry(url, headers={}, data=None):
    """Tries to load data from an endpoint using retries"""
    for i in range(NUM_REQUEST_RETRIES):
        try:
            return _process_request_with_httplib2(url, headers, data)
        except UntappdException as e:
            # Some errors don't bear repeating
            if e.__class__ in [InvalidAuth]: raise
            if ((i + 1) == NUM_REQUEST_RETRIES): raise
        time.sleep(1)

def _process_request_with_httplib2(url, headers={}, data=None):
    """Make the request and handle exception processing"""
    h = httplib2.Http(**HTTP_KWARGS)
    try:
        if data:
            datagen, multipart_headers = poster.encode.multipart_encode(data)
            data = ''.join(datagen)
            headers.update(multipart_headers)
            method = 'POST'
        else:
            method = 'GET'
        response, body = h.request(url, method, headers=headers, body=data)
        data = _json_to_data(body)
        # Default case, Got proper response
        if response.status == 200:
            return data
        return _check_response(data)
    except httplib2.HttpLib2Error as e:
        logging.error(e)
        raise UntappdException(u'Error connecting with Untappd API')

def _json_to_data(s):
    """Convert a response string to data"""
    try:
        return json.loads(s)
    except ValueError as e:
        logging.error('Invalid response: {0}'.format(e))
        raise UntappdException(e)

def _check_response(data):
    """Processes the response data"""
    # Check the meta-data for why this request failed
    meta = data.get('meta')
    if meta:
        # see: https://untappd.com/api/docs/v4
        if meta.get('code') in (200, 409): return data
        exc = ERROR_TYPES.get(meta.get('error_type'))
        if exc:
            raise exc(meta.get('error_detail'))
        else:
            logging.error(u'Unknown error type: {0}'.format(meta.get('error_type')))
            raise UntappdException(meta.get('error_detail'))
    else:
        logging.error(u'Response format invalid, missing meta property') # body is printed in warning above
        raise UntappdException('Missing meta')
