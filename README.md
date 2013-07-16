untappd-python
==============

Python wrapper for the [Untappd v4 API](https://untappd.com/api/docs/v4). Developed to power [No Gluten Beer](http://noglutenbeer.com).

Based almost entirely on the excellent [foursquare](https://github.com/mLewisLogic/foursquare).

## Installation

    pip install untappd

## Usage

### Authentication

    # Construct the client object
    client = untappd.Untappd(client_id='YOUR_CLIENT_ID', client_secret='YOUR_CLIENT_SECRET', redirect_url='YOUR_REDIRECT_URL')

    # Build the authorization url for your app
    auth_url = client.oauth.auth_url()

Redirect your user to the address *auth_uri* and let them authorize your app. They will then be redirected to your *redirect_url*, with a query paramater of code=XX_CODE_RETURNED_IN_REDIRECT_XX. In your webserver, parse out the *code* value, and use it to call client.oauth.get_token()

    # Interrogate Untappd to get the user's access_token
    access_token = client.oauth.get_token('XX_CODE_RETURNED_IN_REDIRECT_XX')

    # Apply the returned access token to the client
    client.set_access_token(access_token)

    # Grab authenticated data 
    beer = client.beer(BID)
