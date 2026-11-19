from django.db import migrations, models
from django.utils.text import slugify


def fill_codes(apps, schema_editor):
    Product = apps.get_model("consultas", "Product")
    used = set()
    for product in Product.objects.order_by("id"):
        base = slugify(product.name)[:50] or f"produto-{product.pk}"
        code, n = base, 2
        while code in used:
            code, n = f"{base}-{n}", n + 1
        used.add(code)
        product.code = code
        product.save(update_fields=["code"])


class Migration(migrations.Migration):
    dependencies = [("consultas", "0001_initial")]

    operations = [
        migrations.AddField(model_name="product", name="code", field=models.SlugField(max_length=60, null=True, db_index=False)),
        migrations.RunPython(fill_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="product",
            name="code",
            field=models.SlugField(help_text="Código público do produto (exibido no app).", max_length=60, unique=True),
        ),
        migrations.AlterField(
            model_name="product",
            name="sku",
            field=models.CharField(help_text="Código do produto no fornecedor (interno).", max_length=80, unique=True),
        ),
        migrations.AlterField(
            model_name="product",
            name="cost_cents",
            field=models.PositiveIntegerField(default=0, help_text="Custo no fornecedor."),
        ),
    ]
