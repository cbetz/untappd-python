untappd-python
==============

Python wrapper for the [Untappd v4 API](https://untappd.com/api/docs/v4). Developed to power [No Gluten Beer](http://noglutenbeer.com).

Based almost entirely on the excellent [foursquare](https://github.com/mLewisLogic/foursquare).

## Installation

    pip install untappd

## Usage

    # Construct the client object (user_agent is optional, at least 'authorize' endpoint responds with 'HTTP 429 Too Many Requests' to default User-Agent header string like 'python-requests/2.24.0')
    client = untappd.Untappd(client_id='YOUR_CLIENT_ID', client_secret='YOUR_CLIENT_SECRET', redirect_url='YOUR_REDIRECT_URL', user_agent='letmein')

### Authentication

For endpoints that access a user's data, you must obtain an access token before you can request data from the API:

    # Build the authorization url for your app
    auth_url = client.oauth.get_auth_url()

Redirect your user to the address *auth_url* and let them authorize your app. They will then be redirected to your *redirect_url*, with a query paramater of code=XX_CODE_RETURNED_IN_REDIRECT_XX. In your webserver, parse out the *code* value, and use it to call client.oauth.get_access_token()

    # Interrogate Untappd to get the user's access_token
    access_token = client.oauth.get_access_token('XX_CODE_RETURNED_IN_REDIRECT_XX')

    # Apply the returned access token to the client
    client.set_access_token(access_token)

    # Grab authenticated data
    user = client.user.info()

### Making Requests

Making requests to the Untappd API is simple. This wrapper mirrors the API endpoint structure detailed in the [documentation](https://untappd.com/api/docs/v4). For example, the [Activity Feed endpoint](https://untappd.com/api/docs#activityfeed) is */v4/checkin/recent* so you can pull data from this endpoint like this:

    activity_feed = client.checkin.recent()

You can send parameters using keyword arguments:

    activity_feed = client.checkin.recent(min_id=10, limit=50)

For endpoints that require a parameter in the endpoint URL, like [Brewery Info](https://untappd.com/api/docs#breweryinfo) (*/v4/brewery/info/BREWERY_ID*), you include that parameter as the first argument in your request:

    brewery_info = client.brewery.info('BREWERY_ID')

Any additional parameters you want to include should be keyword arguments:

    brewery_info = client.brewery.info('BREWERY_ID', compact='true')

If the endpoint URL has three components, like [Add to Wish List](https://untappd.com/api/docs#addwish) (*/v4/user/wishlist/add*), you must separate the second and third component with an underscore:

    result = client.user.wishlist_add(bid='BEER_ID')
