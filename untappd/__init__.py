#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# (c) 2013 Chris Betz
from __future__ import unicode_literals
from builtins import str
import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())
# Uncomment the line below to show debug logging in console
# logging.basicConfig(level=logging.DEBUG)

try:
    import urllib.parse as urllib
except ImportError:
    import urllib

import inspect
import time
import requests

__version__ = 0.4
__author__ = 'Christopher Betz'

AUTH_URL = 'https://untappd.com/oauth/authenticate/'
TOKEN_URL = 'https://untappd.com/oauth/authorize/'
API_URL_BASE = 'https://api.untappd.com/v4'

# Number of times to try http requests
NUM_REQUEST_TRIES = 3

# Generic untappd exception
class UntappdException(Exception): pass
# Specific exceptions
class InvalidAuth(UntappdException): pass

ERROR_TYPES = {
    'invalid_auth': InvalidAuth
}

class Untappd(object):
    """Untappd V4 API client"""
    def __init__(self, client_id=None, client_secret=None, access_token=None, redirect_url=None, user_agent=None):
        """Sets up the API client object"""
        # Either client_id and client_secret or access_token is required to access the API
        if (not client_id or not client_secret) and not access_token:
            error_message = 'You must specify a client_id and client_secret or an access_token'
            logging.error(error_message)
            raise UntappdException(error_message)
        # Set up requester
        self.requester = self.Requester(client_id, client_secret, access_token, user_agent)
        # Set up OAuth
        self.oauth = self.OAuth(self.requester, client_id, client_secret, redirect_url)
        # Dynamically enable endpoints
        self._attach_endpoints()

    def _attach_endpoints(self):
        """Dynamically attaches endpoint callables to this client"""
        for name, value in inspect.getmembers(self):
            if inspect.isclass(value) and issubclass(value, self._Endpoint) and (value is not self._Endpoint):
                endpoint_instance = value(self.requester)
                setattr(self, endpoint_instance.endpoint_base, endpoint_instance)
                if not hasattr(endpoint_instance, 'get_endpoints'):
                    endpoint_instance.get_endpoints = ()
                if not hasattr(endpoint_instance, 'post_endpoints'):
                    endpoint_instance.post_endpoints = ()
                if not hasattr(endpoint_instance, 'is_callable'):
                    endpoint_instance.is_callable = False
                for endpoint in (endpoint_instance.get_endpoints + endpoint_instance.post_endpoints):
                    function = endpoint_instance.create_endpoint_function(endpoint)
                    function_name = endpoint.replace('/', '_')
                    setattr(endpoint_instance, function_name, function)
                    function.__name__ = str(function_name)
                    function.__doc__ = 'Tells the object to make a request to the {0} endpoint'.format(endpoint)

    def set_access_token(self, access_token):
        """Updates the access token to use"""
        self.requester.set_access_token(access_token)

    class OAuth(object):
        """Handles OAuth authentication procedures and helps retrieve tokens"""
        def __init__(self, requester, client_id, client_secret, redirect_url):
            self.requester = requester
            self.client_id = client_id
            self.client_secret = client_secret
            self.redirect_url = redirect_url

        def get_auth_url(self):
            """Gets the URL a user needs to access to get an access token"""
            payload = {
                'client_id': self.client_id,
                'response_type': 'code',
                'redirect_url': self.redirect_url,
            }
            return '{0}?{1}'.format(AUTH_URL, urllib.urlencode(payload))

        def get_access_token(self, code):
            """Gets the access token from a user's response"""
            if not code:
                error_message = 'Code not provided'
                logging.error(error_message)
                raise UntappdException(error_message)
            payload = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'response_type': 'code',
                'redirect_url': self.redirect_url,
                'code': str(code),
            }
            # Get the response from the token uri and attempt to parse
            data = self.requester.request(TOKEN_URL, payload=payload, enrich_payload=False)
            return data.get('response').get('access_token')

    class Requester(object):
        """API requesting object"""
        def __init__(self, client_id=None, client_secret=None, access_token=None, user_agent=None):
            """Sets up the API requesting object"""
            self.client_id = client_id
            self.client_secret = client_secret
            self.headers =  requests.utils.default_headers()
            if user_agent:
                self.headers.update({'User-Agent': user_agent})
            self.set_access_token(access_token)

        def set_access_token(self, access_token):
            """Sets the OAuth access token for this requester"""
            self.access_token = access_token
            self.userless = not bool(access_token) # Userless if no access_token

        def _enrich_payload(self, payload):
            """Enriches the payload dict"""
            if self.userless:
                payload['client_id'] = self.client_id
                payload['client_secret'] = self.client_secret
            else:
                payload['access_token'] = self.access_token
            return payload

        def request(self, url, http_method='GET', payload={}, enrich_payload=True):
            """Tries to load data from an endpoint using retries"""
            if enrich_payload:
                payload = self._enrich_payload(payload)
            logging.debug('{http_method} url: {url} payload:{payload}'.format(
                http_method=http_method,
                url=url,
                payload='* {0}'.format(payload) if payload else ''
            ))
            try_number = 1
            while try_number <= NUM_REQUEST_TRIES:
                try:
                    return self._process_request(url, http_method, payload)
                except UntappdException as e:
                    # Some errors don't bear repeating
                    if e.__class__ in [InvalidAuth]:
                        raise
                    if (try_number == NUM_REQUEST_TRIES):
                        raise
                    try_number += 1
                time.sleep(1)

        def _process_request(self, url, http_method, payload):
            """Makes the request and handles exception processing"""
            try:
                if http_method == 'GET':
                    response = requests.get(url, headers=self.headers, params=payload)
                elif http_method == 'POST':
                    response = requests.post(url, headers=self.headers, data=payload)
                data = self._decode_json_response(response)
                if response.status_code == requests.codes.ok:
                    return data
                return self._check_response(data)
            except requests.exceptions.RequestException as e:
                logging.error(e)
                raise UntappdException('Error connecting with Untappd API')

        def _decode_json_response(self, response):
            """Decodes a json response"""
            try:
                return response.json()
            except ValueError as e:
                logging.error('Invalid response: {0}'.format(e))
                raise UntappdException(e)

        def _check_response(self, data):
            """Processes the response data"""
            # Check the meta-data for why this request failed
            meta = data.get('meta')
            if meta:
                # see: https://untappd.com/api/docs/v4
                if meta.get('code') in (200, 409):
                    return data
                exc = ERROR_TYPES.get(meta.get('error_type'))
                if exc:
                    raise exc(meta.get('error_detail'))
                else:
                    logging.error('Unknown error type: {0}'.format(meta.get('error_type')))
                    raise UntappdException(meta.get('error_detail'))
            else:
                error_message = 'Response format invalid, missing meta property'
                logging.error(error_message)
                raise UntappdException(error_message)

    class _Endpoint(object):
        """Generic endpoint class"""
        def __init__(self, requester):
            """Stores the request function for retrieving data"""
            self.requester = requester

        def __call__(self, id=None, **kwargs):
            """Tells the object to make a request if the endpoint base is callable"""
            if not self.is_callable:
                error_message = 'Endpoint {0} is not callable'.format(self.__class__.__name__)
                logging.error(error_message) # body is printed in warning above
                raise UntappdException(error_message)
            endpoint_parts = (id,)
            return self._make_request(endpoint_parts, 'GET', payload=kwargs)

        def create_endpoint_function(self, endpoint=None):
            """Dynamically creates a function to tell the object to make a request to an API endpoint"""
            def _function(id=None, **kwargs):
                http_method = 'POST' if endpoint in self.post_endpoints else 'GET'
                endpoint_parts = (endpoint, id)
                return self._make_request(endpoint_parts, http_method, payload=kwargs)
            return _function

        def _build_url(self, endpoint_parts):
            """Builds the full API endpoint URL for the request"""
            parts = ((API_URL_BASE, self.endpoint_base) + endpoint_parts)
            return '/'.join(str(p) for p in parts if p)

        def _make_request(self, endpoint_parts, http_method, payload=None):
            """Uses the requester to make a request to an API endpoint"""
            url = self._build_url(endpoint_parts)
            return self.requester.request(url, http_method, payload)

    class Beer(_Endpoint):
        """Beer endpoint class"""
        endpoint_base = 'beer'
        get_endpoints = ('info', 'checkins')

    class Brewery(_Endpoint):
        """Brewery endpoint class"""
        endpoint_base = 'brewery'
        get_endpoints = ('info', 'checkins')

    class Checkin(_Endpoint):
        """Checkin endpoint class"""
        endpoint_base = 'checkin'
        get_endpoints = ('recent',)
        post_endpoints = ('add', 'toast', 'addcomment', 'deletecomment')

    class Friend(_Endpoint):
        """Friend endpoint class"""
        endpoint_base = 'friend'
        get_endpoints = ('request', 'remove', 'accept', 'reject')

    class Notifications(_Endpoint):
        """Notifications endpoint class"""
        endpoint_base = 'notifications'
        is_callable = True

    class Search(_Endpoint):
        """Search endpoint class"""
        endpoint_base = 'search'
        get_endpoints = ('beer', 'brewery')

    class ThePub(_Endpoint):
        """ThePub endpoint class"""
        endpoint_base = 'thepub'
        get_endpoints = ('local',)

    class User(_Endpoint):
        """User endpoint class"""
        endpoint_base = 'user'
        get_endpoints = (
            'checkins',
            'info',
            'wishlist',
            'friends',
            'badges',
            'beers',
            'pending',
            'wishlist/add',
            'wishlist/delete'
        )

    class Venue(_Endpoint):
        """Venue endpoint class"""
        endpoint_base = 'venue'
        get_endpoints = ('info', 'checkins', 'foursquare_lookup')
