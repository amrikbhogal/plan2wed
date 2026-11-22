"""Build external venue searches without calling a provider API."""
from urllib.parse import urlencode


def venue_search_url(filters, provider):
    kind = {
        'gurdwara': 'Gurdwara', 'hall': 'wedding reception hall',
        'hotel': 'wedding hotel', 'restaurant': 'wedding restaurant',
        'outdoor': 'outdoor wedding venue',
    }.get(filters.get('venue_type'), 'wedding venue')
    parts = [kind, filters.get('query', '')]
    if filters.get('location'):
        parts.append('near ' + filters['location'])
    if filters.get('capacity'):
        parts.append(f"for {filters['capacity']} guests")
    query = ' '.join(part for part in parts if part)
    if provider == 'maps':
        return 'https://www.google.com/maps/search/?' + urlencode({'api': 1, 'query': query})
    return 'https://www.google.com/search?' + urlencode({'q': query})
