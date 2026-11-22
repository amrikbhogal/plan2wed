import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import URLError

from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse

from .models import Member
from .venue_search import search_internet_venues, VenueSearchError


@override_settings(GOOGLE_PLACES_API_KEY='test-key')
class InternetVenueSearchTests(SimpleTestCase):
    @patch('planner.venue_search.urlopen')
    def test_search_sends_location_and_type_and_parses_results(self, urlopen):
        urlopen.return_value = BytesIO(json.dumps({'places': [{
            'displayName': {'text': 'Example Hall'}, 'formattedAddress': 'London',
            'googleMapsUri': 'https://maps.google.com/example',
        }]}).encode())
        results = search_internet_venues('London', 'hall', 'parking')
        request = urlopen.call_args.args[0]
        self.assertEqual(json.loads(request.data)['textQuery'], 'wedding reception hall parking near London')
        self.assertEqual(results[0]['name'], 'Example Hall')
        self.assertEqual(urlopen.call_args.kwargs['timeout'], 8)

    @patch('planner.venue_search.urlopen', side_effect=URLError('unavailable'))
    def test_network_failure_is_friendly(self, urlopen):
        with self.assertRaisesMessage(VenueSearchError, 'temporarily unavailable'):
            search_internet_venues('London')

    @override_settings(GOOGLE_PLACES_API_KEY='')
    @patch('planner.venue_search.urlopen')
    def test_missing_key_does_not_call_provider(self, urlopen):
        with self.assertRaisesMessage(VenueSearchError, 'not available yet'):
            search_internet_venues('London')
        urlopen.assert_not_called()


class InternetVenueViewTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='internet-venues')
        Member.objects.create(user=user, email='internet@example.com')
        self.client.force_login(user)

    @patch('planner.views.search_internet_venues')
    def test_normal_browsing_does_not_search_internet(self, search):
        self.assertEqual(self.client.get(reverse('venue_directory')).status_code, 200)
        search.assert_not_called()

    @override_settings(GOOGLE_PLACES_API_KEY='')
    def test_unconfigured_search_renders_helpful_message(self):
        response = self.client.post(reverse('venue_directory'), {'action': 'internet_search', 'location': 'London'})
        self.assertContains(response, 'not available yet')

    @patch('planner.views.search_internet_venues')
    def test_search_renders_results_and_escapes_provider_text(self, search):
        search.return_value = [{'name': '<script>venue</script>', 'address': 'London', 'maps_url': '', 'attributions': []}]
        response = self.client.post(reverse('venue_directory'), {'action': 'internet_search', 'location': 'London'})
        search.assert_called_once_with('London', '', '')
        self.assertContains(response, '&lt;script&gt;venue&lt;/script&gt;')
        self.assertContains(response, 'Google Maps')
