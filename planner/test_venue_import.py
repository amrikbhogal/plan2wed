import socket
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import Member, Venue
from .venue_import import (MAX_BYTES, VenueImportError, extract_details,
                           fetch_website, public_destination)


def dns(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))]


class VenueExtractionTests(SimpleTestCase):
    def test_structured_business_details_and_graph(self):
        html = '''<title>Wrong title</title><script type="application/ld+json">{"@graph":[
        {"@type":"WebSite","name":"Wrong site","email":"wrong@example.com"},
        {"@type":"EventVenue","name":"Example Hall","telephone":"01234 567890",
        "email":"hello@example.com","address":{"streetAddress":"1 High Street",
        "addressLocality":"London","postalCode":"E1 1AA"}}]}</script>'''
        details = extract_details(html, 'https://example.com/')
        self.assertEqual(details['name'], 'Example Hall')
        self.assertEqual(details['address'], '1 High Street, London, E1 1AA')
        self.assertEqual(details['email'], 'hello@example.com')
        self.assertEqual(details['phone'], '01234 567890')

    def test_meta_and_contact_fallbacks_with_invalid_json(self):
        html = '''<script type="application/ld+json">invalid</script>
        <meta property="og:site_name" content="A &amp; B Hall">
        <a href="mailto:hello@example.com?subject=Wedding">Email</a>
        <a href="tel:%2B441234567890">Phone</a>'''
        details = extract_details(html, 'https://example.com/')
        self.assertEqual(details['name'], 'A & B Hall')
        self.assertEqual(details['email'], 'hello@example.com')
        self.assertEqual(details['phone'], '+441234567890')


class PublicFetchTests(SimpleTestCase):
    @patch('planner.venue_import.socket.getaddrinfo')
    def test_private_and_mixed_dns_addresses_are_blocked(self, lookup):
        for addresses in [dns('127.0.0.1'), dns('169.254.169.254'), dns('10.0.0.1'), dns('93.184.216.34') + dns('192.168.1.1')]:
            lookup.return_value = addresses
            with self.assertRaises(VenueImportError):
                public_destination('https://example.com/')

    @patch('planner.venue_import.socket.getaddrinfo')
    def test_credentials_ports_and_non_https_are_blocked_before_dns(self, lookup):
        for url in ['http://example.com/', 'https://user:pass@example.com/', 'https://example.com:8443/', 'file:///etc/passwd']:
            with self.assertRaises(VenueImportError):
                public_destination(url)
        lookup.assert_not_called()

    @patch('planner.venue_import.PublicHTTPSConnection')
    @patch('planner.venue_import.socket.getaddrinfo')
    def test_redirect_to_private_address_is_not_connected(self, lookup, connection):
        lookup.side_effect = [dns('93.184.216.34'), dns('127.0.0.1')]
        response = connection.return_value.getresponse.return_value
        response.status = 302
        response.getheader.return_value = 'https://127.0.0.1/'
        with self.assertRaises(VenueImportError):
            fetch_website('https://example.com/')
        self.assertEqual(connection.call_count, 1)
        self.assertEqual(connection.call_args.args[:2], ('example.com', '93.184.216.34'))

    @patch('planner.venue_import.PublicHTTPSConnection')
    @patch('planner.venue_import.socket.getaddrinfo', return_value=dns('93.184.216.34'))
    def test_oversize_response_is_rejected(self, lookup, connection):
        response = connection.return_value.getresponse.return_value
        response.status = 200
        response.getheader.side_effect = lambda key, default=None: 'text/html' if key == 'Content-Type' else default
        response.read1.side_effect = BytesIO(b'x' * (MAX_BYTES + 1)).read1
        with self.assertRaisesMessage(VenueImportError, 'too large'):
            fetch_website('https://example.com/')


class VenueImportViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username='venue-import')
        self.member = Member.objects.create(user=self.user, email='import@example.com')
        self.client.force_login(self.user)
        self.url = reverse('venue_list')

    @patch('planner.views.import_venue_website')
    def test_import_only_previews_and_user_can_save_edited_details(self, importer):
        importer.return_value = {'name': 'Suggested Hall', 'address': 'London', 'website': 'https://example.com/'}
        response = self.client.post(self.url, {'action': 'import_website', 'website_url': 'https://example.com/'})
        self.assertContains(response, 'Review venue details')
        self.assertEqual(response.context['venue_form'].initial['name'], 'Suggested Hall')
        self.assertFalse(Venue.objects.exists())
        response = self.client.post(self.url, {'action': 'save_venue', 'name': 'Reviewed Hall', 'website': 'https://example.com/'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Venue.objects.get().budget.member, self.member)
        self.assertEqual(Venue.objects.get().name, 'Reviewed Hall')

    @patch('planner.views.import_venue_website', side_effect=VenueImportError('Website unavailable'))
    def test_failure_keeps_manual_form_available(self, importer):
        response = self.client.post(self.url, {'action': 'import_website', 'website_url': 'https://example.com/'})
        self.assertContains(response, 'Website unavailable')
        self.assertContains(response, 'Add a venue')
        self.assertFalse(Venue.objects.exists())

    @patch('planner.views.import_venue_website', return_value={'name': 'Hall'})
    def test_repeat_import_is_throttled(self, importer):
        data = {'action': 'import_website', 'website_url': 'https://example.com/'}
        self.client.post(self.url, data)
        response = self.client.post(self.url, data)
        self.assertContains(response, 'Please wait')
        importer.assert_called_once()
