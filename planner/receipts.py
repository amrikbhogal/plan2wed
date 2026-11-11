"""Local receipt OCR. Images are processed temporarily, never stored publicly."""
import io
import re
import warnings
import subprocess
import tempfile
from decimal import Decimal

from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError


def scan_receipt(upload):
    if upload.size > 8 * 1024 * 1024:
        raise ValidationError('Choose a receipt image smaller than 8 MB.')
    data = upload.read()
    if not (data.startswith(b'\xff\xd8\xff') or data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith((b'II*\x00', b'MM\x00*'))):
        raise ValidationError('Upload a JPEG, PNG or TIFF receipt image.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.width * source.height > 50_000_000:
                    raise ValidationError('This photo is too large to process. Resize it to 50 megapixels or less.')
                # JPEG draft decoding reduces memory before full pixel loading.
                source.draft('RGB', (4000, 4000))
                source.thumbnail((4000, 4000))
                prepared = ImageOps.exif_transpose(source)
                # Composite transparency against paper white before greyscale OCR.
                rgba = prepared.convert('RGBA')
                paper = Image.new('RGBA', rgba.size, 'white')
                paper.alpha_composite(rgba)
                prepared = ImageOps.autocontrast(paper.convert('L'))
                prepared.thumbnail((4000, 4000))
        with tempfile.NamedTemporaryFile(suffix='.png') as image:
            prepared.save(image, format='PNG', dpi=(300, 300))
            image.flush()
            result = subprocess.run(
                ['tesseract', image.name, 'stdout', '-l', 'eng', '--psm', '1'],
                capture_output=True, timeout=25, check=True,
            )
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError('This image could not be decoded safely. Export it as a smaller JPEG or PNG and try again.')
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
    pending_quantity = None
    for line in text.splitlines():
        if re.search(r'\b(total|subtotal|vat|tax|change|cash|card|payment|discount|saving|balance)\b', line, re.I) or re.match(r'^\s*t\s*o\s*t\s*a\s*l\b', line, re.I):
            pending_quantity = None
            continue
        # ALDI-style receipts put the quantity and unit price before the
        # product line. Use the product's line total for the final cost.
        quantity_line = re.fullmatch(r'\s*(\d{1,4})\s*[x×]\s+[£$€]?\s*\d+[.,]\d{2}\s*', line, re.I)
        if quantity_line:
            pending_quantity = int(quantity_line[1]) or None
            continue
        # OCR often inserts spaces around decimal marks or reads trailing tax
        # codes as separate words. Some tills place a currency symbol after prices.
        line = line.replace('\u00a0', ' ')
        line = re.sub(r'(?<=\d)\s*([.,])\s*(?=\d{2}\b)', r'\1', line)
        match = re.fullmatch(
            r'\s*(.+?)\s*[£$€]?\s*(\d{1,8}(?:[ ,]\d{3})*[.,]\d{2})'
            r'\s*(?:[£$€]|GBP|USD|EUR)?\s*[A-Z*]{0,2}\s*',
            line,
        )
        if not match:
            pending_quantity = None
            continue
        name, price = match.groups()
        name = re.sub(r'^\d{5,8}\s+', '', name)
        quantity = pending_quantity or 1
        pending_quantity = None
        qty = re.match(r'^(\d{1,4})\s*[x×]\s+(.+)$', name, re.I)
        if qty:
            quantity, name = int(qty[1]), qty[2]
        if not quantity or not re.search(r'[a-zA-Z]', name):
            continue
        total = Decimal(price.replace(' ', '').replace(',', '') if '.' in price else price.replace(' ', '').replace(',', '.'))
        items.append({'name': name[:160], 'quantity': quantity,
                      'unit_cost': (total / quantity).quantize(Decimal('.01'))})
        if len(items) == 50:
            break
    return items
