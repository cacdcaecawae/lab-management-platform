from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    # settings.CACHES uses the database cache; this keeps `migrate` the only setup step.
    call_command("createcachetable", database=schema_editor.connection.alias, verbosity=0)


class Migration(migrations.Migration):
    dependencies = []
    operations = [migrations.RunPython(create_cache_table, migrations.RunPython.noop)]
