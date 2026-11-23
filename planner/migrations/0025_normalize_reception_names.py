import re

from django.db import migrations


def rename_reception_variants(apps, schema_editor):
    WeddingEvent = apps.get_model('planner', 'WeddingEvent')
    events = WeddingEvent.objects.using(schema_editor.connection.alias)
    for event in events.only('pk', 'name').iterator():
        if re.fullmatch(r'\s*wedding\s+meal\s*/\s*reception\s*', event.name, re.IGNORECASE):
            events.filter(pk=event.pk).update(name='Reception')


class Migration(migrations.Migration):
    dependencies = [('planner', '0024_rename_wedding_meal_reception')]
    operations = [migrations.RunPython(rename_reception_variants, migrations.RunPython.noop)]
