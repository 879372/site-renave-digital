"""Contas criadas antes da verificação de e-mail continuam com acesso (já estavam em uso)."""

from django.db import migrations


def forwards(apps, schema_editor):
    apps.get_model("accounts", "User").objects.filter(email_verified=False).update(email_verified=True)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_user_anonymized_at_user_legal_version_and_more")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
