from django.db import migrations


def seed(apps, schema_editor):
    from billing.catalog import PLANS

    Plan = apps.get_model("billing", "Plan")
    for data in PLANS:
        Plan.objects.update_or_create(code=data["code"], defaults=data)


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
