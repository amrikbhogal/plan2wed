from django.db import migrations


def rename_reception(apps, schema_editor):
    WeddingEvent = apps.get_model('planner', 'WeddingEvent')
    WeddingEvent.objects.using(schema_editor.connection.alias).filter(
        name__in=['Wedding Meal / Reception', 'Wedding Meal/Reception'],
    ).update(name='Reception')


class Migration(migrations.Migration):
    dependencies = [('planner', '0023_weddingevent_requires_table_plan')]
    operations = [migrations.RunPython(rename_reception, migrations.RunPython.noop)]
