"""On-demand Google Places searches; results are not stored in the directory."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.conf import settings


class VenueSearchError(Exception):
    pass


def safe_link(value):
    if isinstance(value, str) and urlsplit(value).scheme == 'https' and urlsplit(value).netloc:
        return value
    return ''


def search_internet_venues(location, venue_type='', query=''):
    key = settings.GOOGLE_PLACES_API_KEY
    if not key:
        raise VenueSearchError('Internet venue search is not available yet. Please use the venue directory for now.')
    if not location.strip():
        raise VenueSearchError('Enter a town, city or region to search for venues nearby.')
    venue_kind = {
        'gurdwara': 'Gurdwara', 'hall': 'wedding reception hall',
        'hotel': 'wedding hotel', 'restaurant': 'wedding restaurant',
        'outdoor': 'outdoor wedding venue',
    }.get(venue_type, 'wedding venue')
    request = Request(
        'https://places.googleapis.com/v1/places:searchText',
        data=json.dumps({'textQuery': f'{venue_kind} {query} near {location}', 'pageSize': 12}).encode(),
        headers={'Content-Type': 'application/json', 'X-Goog-Api-Key': key,
                 'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.googleMapsUri,places.attributions'},
        method='POST',
    )
    try:
        with urlopen(request, timeout=8) as response:
            data = json.load(response)
        if not isinstance(data, dict) or not isinstance(data.get('places', []), list):
            raise ValueError('Invalid response')
        results = []
        for place in data.get('places', [])[:12]:
            name = place.get('displayName', {}).get('text', '')
            if not name:
                continue
            results.append({
                'name': name, 'address': place.get('formattedAddress', ''),
                'maps_url': safe_link(place.get('googleMapsUri')),
                'attributions': [{'name': a.get('provider', ''), 'url': safe_link(a.get('providerUri'))}
                                 for a in place.get('attributions', [])],
            })
        return results
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError, AttributeError) as error:
        raise VenueSearchError('Internet venue search is temporarily unavailable. Please try again later.') from error
