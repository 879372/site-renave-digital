from django.db import migrations


def sync(apps, schema_editor):
    from billing.catalog import PLANS

    Plan = apps.get_model("billing", "Plan")
    for data in PLANS:
        Plan.objects.filter(code=data["code"]).update(features=data["features"])


class Migration(migrations.Migration):
    dependencies = [("billing", "0002_seed_plans")]

    operations = [migrations.RunPython(sync, migrations.RunPython.noop)]
