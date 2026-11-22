from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Member, WeddingBudget


class ExternalVenueSearchTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='internet-venues')
        self.member = Member.objects.create(user=user, email='internet@example.com')
        WeddingBudget.objects.create(member=self.member, wedding_location='London')
        self.client.force_login(user)
        self.url = reverse('venue_directory')

    def test_maps_search_uses_saved_location_and_current_filters(self):
        response = self.client.get(self.url, {'external_search': 'maps', 'venue_type': 'hall', 'capacity': '150'})
        self.assertEqual(response.status_code, 302)
        url = urlsplit(response.url)
        self.assertEqual(url.netloc, 'www.google.com')
        self.assertEqual(url.path, '/maps/search/')
        self.assertEqual(parse_qs(url.query), {'api': ['1'], 'query': ['wedding reception hall near London for 150 guests']})

    def test_web_search_encodes_user_input_and_uses_current_location(self):
        response = self.client.get(self.url, {'external_search': 'web', 'location': 'York', 'query': 'A & B', 'venue_type': 'hotel'})
        url = urlsplit(response.url)
        self.assertEqual(url.netloc, 'www.google.com')
        self.assertEqual(url.path, '/search')
        self.assertEqual(parse_qs(url.query), {'q': ['wedding hotel A & B near York']})

    def test_buttons_render_without_api_interface(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Search Google Maps')
        self.assertContains(response, 'Search the web')
        self.assertNotContains(response, 'Search internet venues')
        self.assertContains(response, 'Add it to your venues')

    def test_unknown_provider_does_not_redirect(self):
        response = self.client.get(self.url, {'external_search': 'https://example.com'})
        self.assertEqual(response.status_code, 200)
