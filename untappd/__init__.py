#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# (c) 2013 Chris Betz
from __future__ import unicode_literals
import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())

try:
    import urllib.parse as urllib
except ImportError:
    import urllib

import inspect
import time
import requests

__version__ = 0.2
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
    """Untappd V4 API wrapper"""

    def __init__(self, client_id=None, client_secret=None, redirect_url=None,):
        """Sets up the api object"""
        # Set up requester
        self.requester = self.Requester(client_id, client_secret)
        # Set up OAuth
        self.oauth = self.OAuth(self.requester, client_id, client_secret, redirect_url)
        # Dynamically enable endpoints
        self._attach_endpoints()

    def _attach_endpoints(self):
        """Dynamically attach endpoint callables to this client"""
        for name, value in inspect.getmembers(self):
            if inspect.isclass(value) and issubclass(value, self._Endpoint) and (value is not self._Endpoint):
                endpoint_instance = value(self.requester)
                setattr(self, endpoint_instance.endpoint_base, endpoint_instance)
                if not hasattr(endpoint_instance, 'get_endpoints'):
                    endpoint_instance.get_endpoints = ()
                if not hasattr(endpoint_instance, 'post_endpoints'):
                    endpoint_instance.post_endpoints = ()
                if endpoint_instance.get_endpoints or endpoint_instance.post_endpoints:
                    for endpoint in (endpoint_instance.get_endpoints + endpoint_instance.post_endpoints):
                        function = endpoint_instance.create_endpoint_function(endpoint)
                        setattr(endpoint_instance, endpoint.replace('/', '_'), function)
                else:
                    endpoint_instance.__call__ = endpoint_instance.create_endpoint_function()

    def set_access_token(self, access_token):
        """Update the access token to use"""
        self.requester.set_access_token(access_token)

    class OAuth(object):
        """Handles OAuth authentication procedures and helps retrieve tokens"""
        def __init__(self, requester, client_id, client_secret, redirect_url):
            self.requester = requester
            self.client_id = client_id
            self.client_secret = client_secret
            self.redirect_url = redirect_url

        def get_auth_url(self):
            """Gets the url a user needs to access to give up a user token"""
            payload = {
                'client_id': self.client_id,
                'response_type': 'code',
                'redirect_url': self.redirect_url,
            }
            return '{0}?{1}'.format(AUTH_URL, urllib.urlencode(payload))

        def get_access_token(self, code):
            """Gets the auth token from a user's response"""
            if not code:
                logging.error('Code not provided')
                return None
            payload = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'response_type': 'code',
                'redirect_url': self.redirect_url,
                'code': unicode(code),
            }
            # Get the response from the token uri and attempt to parse
            data = self.requester.request(TOKEN_URL, payload=payload, enrich_payload=False)
            return data.get('response').get('access_token')

    class Requester(object):
        """Api requesting object"""
        def __init__(self, client_id=None, client_secret=None):
            """Sets up the api object"""
            self.client_id = client_id
            self.client_secret = client_secret
            self.userless = True

        def set_access_token(self, access_token):
            """Set the OAuth token for this requester"""
            self.access_token = access_token
            self.userless = False

        def _enrich_payload(self, payload):
            """Enrich the payload dict"""
            if self.userless:
                payload['client_id'] = self.client_id
                payload['client_secret'] = self.client_secret
            else:
                payload['access_token'] = self.access_token
            return payload

        def request(self, url, http_method='GET', payload={}, enrich_payload=True):
            """Performs the passed request and returns meaningful data"""
            if enrich_payload:
                payload = self._enrich_payload(payload)
            logging.debug('{http_method} url: {url} payload:{payload}'.format(
                http_method=http_method,
                url=url,
                payload='* {0}'.format(payload) if payload else ''
            ))
            """Tries to load data from an endpoint using retries"""
            try_number = 1
            while try_number <= NUM_REQUEST_TRIES:
                try:
                    return self._process_request(url, http_method, payload)
                except UntappdException as e:
                    # Some errors don't bear repeating
                    if e.__class__ in [InvalidAuth]: raise
                    if (try_number == NUM_REQUEST_TRIES): raise
                    try_number += 1
                time.sleep(1)

        def _process_request(self, url, http_method, payload):
            """Make the request and handle exception processing"""
            try:
                if http_method == 'GET':
                    response = requests.get(url, params=payload)
                elif http_method == 'POST':
                    response = requests.post(url, data=payload)
                data = self._decode_json_response(response)
                if response.status_code == requests.codes.ok:
                    return data
                return self._check_response(data)
            except requests.exceptions.RequestException as e:
                logging.error(e)
                raise UntappdException('Error connecting with Untappd API')

        def _decode_json_response(self, response):
            """Decode a json response"""
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
                if meta.get('code') in (200, 409): return data
                exc = ERROR_TYPES.get(meta.get('error_type'))
                if exc:
                    raise exc(meta.get('error_detail'))
                else:
                    logging.error('Unknown error type: {0}'.format(meta.get('error_type')))
                    raise UntappdException(meta.get('error_detail'))
            else:
                error_message = 'Response format invalid, missing meta property'
                logging.error(error_message) # body is printed in warning above
                raise UntappdException(error_message)

    class _Endpoint(object):
        """Generic endpoint class"""
        def __init__(self, requester):
            """Stores the request function for retrieving data"""
            self.requester = requester

        def create_endpoint_function(self, endpoint=None):
            def _function(self, id=None, **kwargs):
                http_method = 'POST' if endpoint in self.post_endpoints else 'GET'
                endpoint_parts = (endpoint, id)
                return self._make_request(endpoint_parts, http_method, payload=kwargs)
            return _function

        def _make_request(self, endpoint_parts, http_method, payload=None):
            parts = ((API_URL_BASE, self.endpoint_base) + endpoint_parts)
            url = '/'.join(p for p in parts if p)
            return self.requester.request(url, http_method, payload)

    class Beer(_Endpoint):
        endpoint_base = 'beer'
        get_endpoints = ('info', 'checkins')

    class Brewery(_Endpoint):
        endpoint_base = 'brewery'
        get_endpoints = ('info', 'checkins')

    class Checkin(_Endpoint):
        endpoint_base = 'checkin'
        get_endpoints = ('recent',)
        post_endpoints = ('add', 'toast', 'addcomment', 'deletecomment')

    class Friend(_Endpoint):
        endpoint_base = 'friend'
        get_endpoints = ('request', 'remove', 'accept', 'reject')

    class Notifications(_Endpoint):
        endpoint_base = 'notifications'

    class Search(_Endpoint):
        endpoint_base = 'search'
        get_endpoints = ('beer', 'brewery')

    class ThePub(_Endpoint):
        endpoint_base = 'thepub'
        get_endpoints = ('local',)

    class User(_Endpoint):
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
        endpoint_base = 'venue'
        get_endpoints = ('info', 'checkins', 'foursquare_lookup')
