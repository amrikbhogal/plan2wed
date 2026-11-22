"""Read public venue websites and suggest details without saving a venue."""
import http.client
import ipaddress
import json
import socket
import ssl
import time
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

MAX_BYTES = 1024 * 1024


class VenueImportError(Exception):
    pass


def public_destination(url):
    try:
        parts = urlsplit(url)
        if (parts.scheme != 'https' or not parts.hostname or parts.username is not None
                or parts.password is not None or parts.port not in (None, 443)):
            raise ValueError()
        hostname = parts.hostname.encode('idna').decode('ascii')
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        if not addresses:
            raise ValueError()
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global or getattr(ip, 'ipv4_mapped', None) is not None:
                raise ValueError()
        return hostname, addresses[0][4][0], urlunsplit(('https', parts.netloc, parts.path or '/', parts.query, ''))
    except (ValueError, UnicodeError, OSError) as error:
        raise VenueImportError('Use a public venue website beginning with https://.') from error


class PublicHTTPSConnection(http.client.HTTPSConnection):
    """Connect to the validated IP while preserving hostname TLS verification."""
    def __init__(self, hostname, ip, timeout):
        super().__init__(hostname, timeout=timeout, context=ssl.create_default_context())
        self.public_ip = ip

    def connect(self):
        raw_socket = socket.create_connection((self.public_ip, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


def fetch_website(url):
    deadline = time.monotonic() + 12
    try:
        for _ in range(4):
            hostname, ip, url = public_destination(url)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            connection = PublicHTTPSConnection(hostname, ip, timeout=min(4, remaining))
            try:
                parts = urlsplit(url)
                path = urlunsplit(('', '', parts.path, parts.query, ''))
                connection.request('GET', path, headers={
                    'User-Agent': 'Plan2Wed Venue Preview/1.0',
                    'Accept': 'text/html,application/xhtml+xml', 'Accept-Encoding': 'identity',
                })
                response = connection.getresponse()
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader('Location')
                    if not location:
                        raise VenueImportError('The website redirected without a destination. Try its main website link.')
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    raise VenueImportError('This website could not be read. You can still enter the venue details manually.')
                content_type = response.getheader('Content-Type', '')
                if content_type.split(';')[0].strip().lower() not in ('text/html', 'application/xhtml+xml'):
                    raise VenueImportError('Please use the venue’s website page, rather than a document or image.')
                if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                    raise VenueImportError('This website could not be read. Please enter the venue details manually.')
                data = bytearray()
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError()
                    if connection.sock:
                        connection.sock.settimeout(min(4, remaining))
                    chunk = response.read1(min(65536, MAX_BYTES + 1 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise VenueImportError('This page is too large to import. Try a simpler contact page or enter details manually.')
                return bytes(data).decode('utf-8', errors='replace'), url
            finally:
                connection.close()
        raise VenueImportError('This website has too many redirects. Try its final website link.')
    except VenueImportError:
        raise
    except (OSError, ValueError, http.client.HTTPException) as error:
        raise VenueImportError('The website could not be reached. Try again or enter the venue details manually.') from error


class VenuePageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = []
        self.in_title = False
        self.json_script = None
        self.schemas = []
        self.meta_name = ''
        self.email = ''
        self.phone = ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title':
            self.in_title = True
        elif tag == 'script' and attrs.get('type', '').lower() == 'application/ld+json':
            self.json_script = []
        elif tag == 'meta' and attrs.get('property', '').lower() in ('og:site_name', 'og:title'):
            if not self.meta_name or attrs['property'].lower() == 'og:site_name':
                self.meta_name = attrs.get('content', '')
        elif tag == 'a':
            href = attrs.get('href', '')
            if href.lower().startswith('mailto:') and not self.email:
                self.email = unquote(href[7:].split('?')[0])
            elif href.lower().startswith('tel:') and not self.phone:
                self.phone = unquote(href[4:].split('?')[0])

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        elif tag == 'script' and self.json_script is not None:
            try:
                self.schemas.append(json.loads(''.join(self.json_script)))
            except (ValueError, RecursionError):
                pass
            self.json_script = None

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if self.json_script is not None:
            self.json_script.append(data)


def text(value, limit):
    return ' '.join(value.split())[:limit] if isinstance(value, str) else ''


def schema_nodes(data, depth=0):
    if depth > 12:
        return
    if isinstance(data, list):
        for item in data:
            yield from schema_nodes(item, depth + 1)
    elif isinstance(data, dict):
        yield data
        for key in ('@graph', 'mainEntity', 'about'):
            if key in data:
                yield from schema_nodes(data[key], depth + 1)


def extract_details(html, url):
    parser = VenuePageParser()
    try:
        parser.feed(html)
    except (ValueError, RecursionError) as error:
        raise VenueImportError('This page could not be read. Please enter the venue details manually.') from error
    candidates = []
    excluded = {'WebSite', 'WebPage', 'BreadcrumbList', 'Person', 'PostalAddress', 'ImageObject'}
    for schema in parser.schemas:
        for node in schema_nodes(schema):
            types = node.get('@type', [])
            types = [types] if isinstance(types, str) else types
            if not isinstance(types, list) or not all(isinstance(t, str) for t in types):
                continue
            if set(types) & excluded or not node.get('name'):
                continue
            if any(key in node for key in ('address', 'telephone', 'email')):
                candidates.append(node)
    node = max(candidates, key=lambda n: sum(bool(n.get(k)) for k in ('address', 'telephone', 'email')), default={})
    address = node.get('address', '')
    if isinstance(address, dict):
        address = ', '.join(filter(None, (text(address.get(k), 160) for k in ('streetAddress', 'addressLocality', 'addressRegion', 'postalCode'))))
    email = text(node.get('email') or parser.email, 254)
    if email.lower().startswith('mailto:'):
        email = email[7:]
    try:
        validate_email(email)
    except ValidationError:
        email = ''
    return {
        'name': text(node.get('name') or parser.meta_name or ''.join(parser.title), 160),
        'address': text(address, 300), 'email': email,
        'phone': text(node.get('telephone') or parser.phone, 40), 'website': url,
    }


def import_venue_website(url):
    html, final_url = fetch_website(url)
    details = extract_details(html, final_url)
    if not details['name']:
        raise VenueImportError('No venue name was found. Please enter the venue details manually.')
    return details
