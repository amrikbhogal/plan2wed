import csv
import io

from django.core.exceptions import ValidationError
from .forms import ShoppingListItemForm
from .models import ShoppingListItem


def read_shopping_csv(upload, event, default_list):
    if upload.size > 1024 * 1024:
        raise ValidationError('Choose a CSV smaller than 1 MB.')
    try:
        reader = csv.DictReader(io.StringIO(upload.read().decode('utf-8-sig')), strict=True)
        if not reader.fieldnames:
            raise ValidationError('The CSV needs an Item column.')
        reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]
        if 'item' not in reader.fieldnames:
            raise ValidationError('The CSV needs an Item column.')
        categories = {label.casefold(): value for value, label in ShoppingListItem.ListCategory.choices}
        categories.update({value: value for value, label in ShoppingListItem.ListCategory.choices})
        rows = []
        for number, raw in enumerate(reader, 2):
            if number > 201:
                raise ValidationError('Import up to 200 rows at a time.')
            if None in raw:
                raise ValidationError(f'Row {number}: too many columns. Quote values containing commas.')
            row = {key: (value or '').strip() for key, value in raw.items()}
            if not any(row.values()):
                continue
            if row.get('event') and row['event'].casefold() != event.name.casefold():
                raise ValidationError(f'Row {number}: event must be {event.name}. Import other events from their own shopping lists.')
            category = categories.get(row.get('list', '').casefold(), default_list if not row.get('list') else None)
            if category is None:
                raise ValidationError(f'Row {number}: choose one of the predefined shopping lists.')
            form = ShoppingListItemForm({'name': row.get('item'), 'quantity': row.get('quantity') or '1',
                'unit_cost': row.get('unit cost', ''), 'list_category': category,
                'supplier_name': row.get('supplier', ''), 'notes': row.get('notes', '')})
            if not form.is_valid():
                errors = '; '.join(f'{field}: {", ".join(messages)}' for field, messages in form.errors.items())
                raise ValidationError(f'Row {number}: {errors}')
            cleaned = {key: form.cleaned_data[key] for key in ('name', 'quantity', 'unit_cost', 'list_category', 'supplier_name', 'notes')}
            if cleaned['unit_cost'] is not None:
                cleaned['unit_cost'] = str(cleaned['unit_cost'])
            rows.append(cleaned)
    except (UnicodeDecodeError, csv.Error):
        raise ValidationError('Upload a UTF-8 CSV exported from Excel or Google Sheets.')
    if not rows:
        raise ValidationError('The CSV contains no items.')
    return rows
