from django.db import migrations

SEED_EVENTS = [{'name': 'Roka / Thaka',
  'description': 'A family gathering to confirm the couple’s intention to marry, often marked by blessings, '
                 'sweets and gifts.',
  'source_url': 'https://www.sikhmissionarysociety.org/sms/smssikhism/ceremonies/marriage/',
  'items': [('Refreshments (if hosting)', 'food', 'Plan for guest numbers and dietary needs.')]},
 {'name': 'Chunni Chadana',
  'description': 'The groom’s family welcomes the bride with a chunni (scarf), often accompanied by gifts '
                 'and blessings.',
  'source_url': 'https://www.sikhmissionarysociety.org/sms/smssikhism/ceremonies/marriage/',
  'items': [('Chunni / scarf', 'clothing', 'Choose with your family.'),
            ('Outfit (optional)', 'clothing', 'Only if part of your family’s plans.'),
            ('Gifts (optional)', 'gifts', 'Agree recipients and budget with your family.'),
            ('Sweets / mithai', 'food', 'Choose quantities and check dietary needs.'),
            ('Gift wrapping / presentation tray', 'ceremony', 'Optional presentation supplies.'),
            ('Refreshments (if hosting)', 'food', 'Plan for guest numbers and dietary needs.')]},
 {'name': 'Kurmai / Sagai (engagement)',
  'description': 'An engagement gathering where the families acknowledge the forthcoming marriage, often '
                 'with prayers, gifts and an exchange of rings.',
  'source_url': 'https://www.sikhmissionarysociety.org/sms/smssikhism/ceremonies/marriage/',
  'items': [('Refreshments (if hosting)', 'food', 'Plan for guest numbers and dietary needs.')]},
 {'name': 'Akhand Path',
  'description': 'An uninterrupted reading of the Guru Granth Sahib, usually lasting about 48 hours, held to '
                 'seek blessings.',
  'source_url': 'https://www.punjabiweddingorganizer.com/blog/order-of-a-sikh-wedding',
  'items': [('Refreshments (if hosting)', 'food', 'Plan for guest numbers and dietary needs.')]},
 {'name': 'Sangeet',
  'description': 'A musical celebration bringing relatives and friends together for wedding songs, dancing '
                 'and performances.',
  'source_url': 'https://www.punjabiweddingorganizer.com/blog/order-of-a-sikh-wedding',
  'items': [('Refreshments (if hosting)', 'food', 'Plan for guest numbers and dietary needs.')]},
 {'name': 'Mehndi',
  'description': 'A pre-wedding gathering where henna designs are applied to the bride’s hands and feet, '
                 'often with music and family celebrations.',
  'source_url': 'https://www.punjabiweddingorganizer.com/blog/order-of-a-sikh-wedding',
  'items': [('Henna supplies', 'ceremony', 'Confirm supplies with your mehndi artist.'),
            ('Refreshments (if hosting)', 'food', 'Plan for guest numbers and dietary needs.')]},
 {'name': 'Maiyan / Vatna',
  'description': 'A Punjabi pre-wedding custom in which relatives apply a turmeric-based paste to the bride '
                 'or groom at their respective homes.',
  'source_url': 'https://www.sikhmissionarysociety.org/sms/smssikhism/ceremonies/marriage/',
  'items': [('Vatna preparation supplies',
             'ceremony',
             'Confirm ingredients and skin sensitivities with family.'),
            ('Refreshments (if hosting)', 'food', 'Plan for guest numbers and dietary needs.')]},
 {'name': 'Khare Charhna',
  'description': 'A traditional pre-wedding bath following the Vatna ceremony; the bride is seated on a '
                 'small stool for bathing.',
  'source_url': 'https://www.sikhmissionarysociety.org/sms/smssikhism/ceremonies/marriage/',
  'items': [('Refreshments (if hosting)', 'food', 'Plan for guest numbers and dietary needs.')]},
 {'name': 'Jaggo',
  'description': 'A lively night-time Punjabi celebration featuring singing, dancing and a decorated pot '
                 'with lights, traditionally carried through the neighbourhood.',
  'source_url': 'https://www.punjabiweddingorganizer.com/blog/order-of-a-sikh-wedding',
  'items': [('Decorated Jaggo pot / lights',
             'ceremony',
             'Check what your family or supplier already provides.'),
            ('Refreshments (if hosting)', 'food', 'Plan for guest numbers and dietary needs.')]},
 {'name': 'Choora ceremony',
  'description': 'The bride receives her wedding bangles, traditionally red and white, from her maternal '
                 'family; kaleere may also be attached.',
  'source_url': 'https://www.punjabiweddingorganizer.com/blog/order-of-a-sikh-wedding',
  'items': [('Choora bangles', 'clothing', 'Confirm sizes and family preferences.'),
            ('Kaleere (optional)', 'clothing', 'If part of your family’s plans.'),
            ('Refreshments (if hosting)', 'food', 'Plan for guest numbers and dietary needs.')]},
 {'name': 'Baraat',
  'description': 'The groom’s wedding party travels to the ceremony venue, where the bride’s family welcomes '
                 'them before the wedding.',
  'source_url': 'https://www.sikhmissionarysociety.org/sms/smssikhism/ceremonies/marriage/',
  'items': [('Refreshments (if hosting)', 'food', 'Plan for guest numbers and dietary needs.')]},
 {'name': 'Milni',
  'description': 'A welcome gathering where corresponding relatives from each family meet and greet one '
                 'another before the wedding ceremony.',
  'source_url': 'https://www.sikhmissionarysociety.org/sms/smssikhism/ceremonies/marriage/',
  'items': [('Refreshments (if hosting)', 'food', 'Plan for guest numbers and dietary needs.')]},
 {'name': 'Anand Karaj',
  'description': 'The Sikh marriage ceremony, celebrated in the presence of the Guru Granth Sahib. The '
                 'couple walks around the scripture during the four Laavan hymns, reflecting a shared '
                 'spiritual journey and commitment to married life.',
  'source_url': 'https://www.sikhmissionarysociety.org/sms/smssikhism/ceremonies/marriage/',
  'items': [('Refreshments (if hosting)', 'food', 'Plan for guest numbers and dietary needs.')]},
 {'name': 'Doli / Vidaai',
  'description': 'The farewell after the wedding, when the bride leaves her family home or wedding venue '
                 'with her spouse.',
  'source_url': 'https://www.punjabiweddingorganizer.com/blog/order-of-a-sikh-wedding',
  'items': [('Refreshments (if hosting)', 'food', 'Plan for guest numbers and dietary needs.')]},
 {'name': 'Reception',
  'description': 'A celebration after the wedding where family and friends gather for a meal, speeches, '
                 'music and dancing.',
  'source_url': 'https://www.punjabiweddingorganizer.com/blog/order-of-a-sikh-wedding',
  'items': [('Table decorations', 'decorations', 'Check what the venue supplies.'),
            ('Table stationery', 'stationery', 'If you are using table numbers or place cards.'),
            ('Refreshments (if hosting)', 'food', 'Plan for guest numbers and dietary needs.')]}]


def seed_events(apps, schema_editor):
    Template = apps.get_model('planner', 'EventTemplate')
    Item = apps.get_model('planner', 'SuggestedShoppingItem')
    alias = schema_editor.connection.alias
    for row in SEED_EVENTS:
        template, created = Template.objects.using(alias).get_or_create(name=row['name'], defaults={
            'description': row['description'], 'source_url': row['source_url'],
            'guidance': 'Customs vary between families. Review these optional ideas with your family and venue; they are not religious requirements.',
            'is_published': True,
        })
        if created:
            for name, category, notes in row['items']:
                Item.objects.using(alias).create(event_template=template, name=name, list_category=category, quantity=1, notes=notes)


class Migration(migrations.Migration):
    dependencies = [('planner', '0018_eventtemplate_suggestedshoppingitem_and_more')]
    operations = [migrations.RunPython(seed_events, migrations.RunPython.noop)]
