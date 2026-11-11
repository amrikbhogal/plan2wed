"""Local receipt OCR. Images are processed temporarily, never stored publicly."""
import re
import subprocess
import tempfile
from decimal import Decimal

from django.core.exceptions import ValidationError


def scan_receipt(upload):
    if upload.size > 8 * 1024 * 1024:
        raise ValidationError('Choose a receipt image smaller than 8 MB.')
    data = upload.read()
    if not (data.startswith(b'\xff\xd8\xff') or data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith((b'II*\x00', b'MM\x00*'))):
        raise ValidationError('Upload a JPEG, PNG or TIFF receipt image.')
    try:
        with tempfile.NamedTemporaryFile(suffix='.image') as image:
            image.write(data)
            image.flush()
            result = subprocess.run(
                ['tesseract', image.name, 'stdout', '-l', 'eng', '--psm', '6'],
                capture_output=True, timeout=25, check=True,
            )
    except FileNotFoundError:
        raise ValidationError('Receipt scanning is not configured on this server. Please add items manually until scanning is available.')
    except (subprocess.SubprocessError, OSError):
        raise ValidationError('We could not read this image. Try a clearer photo or add items manually.')
    text = result.stdout.decode('utf-8', errors='replace')[:20000]
    if not text.strip():
        raise ValidationError('No text was found. Try a clearer photo or add items manually.')
    return text


def receipt_items(text):
    """Conservative suggestions: trailing line prices, with explicit quantity only."""
    items = []
    for line in text.splitlines():
        if re.search(r'\b(total|subtotal|vat|tax|change|cash|card|payment|discount|saving|balance)\b', line, re.I):
            continue
        match = re.fullmatch(r'\s*(.+?)\s+[£$€]?\s*(\d{1,8}[.,]\d{2})\s*[A-Z]?\s*', line)
        if not match:
            continue
        name, price = match.groups()
        quantity = 1
        qty = re.match(r'^(\d{1,4})\s*[x×]\s+(.+)$', name, re.I)
        if qty:
            quantity, name = int(qty[1]), qty[2]
        if not quantity or not re.search(r'[a-zA-Z]', name):
            continue
        total = Decimal(price.replace(',', '.'))
        items.append({'name': name[:160], 'quantity': quantity,
                      'unit_cost': (total / quantity).quantize(Decimal('.01'))})
        if len(items) == 50:
            break
    return items
