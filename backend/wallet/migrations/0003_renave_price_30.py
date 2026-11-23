from django.db import migrations

# RENAVE passa a R$ 30,00 por entrada ou saída (decisão de 2026-11-22).
CODES = ("renave.entrada", "renave.saida")


def forward(apps, schema_editor):
    ServicePrice = apps.get_model("wallet", "ServicePrice")
    for code in CODES:
        ServicePrice.objects.update_or_create(code=code, defaults={"price_cents": 3000, "is_active": True})


class Migration(migrations.Migration):
    dependencies = [("wallet", "0002_remove_wallet_wallet_non_negative_and_more")]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
