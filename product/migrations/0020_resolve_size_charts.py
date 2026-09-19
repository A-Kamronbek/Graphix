"""Write each product's resolved size chart onto the product, before ``fit`` goes.

Qolip (``fit``) is being removed (§17 #172), and the column cannot simply be
dropped: a product with no chart of its own found one *through* it.
``resolve_size_chart`` fell back to the standard chart for the cut (§17 #96),
so dropping the column would silently take the size guide off every product
that was relying on that fallback. The fallback is resolved into the data here
instead — the chart is written onto the row — and 0021 drops the columns.

**Why this is its own migration.** Django wraps each migration in one
transaction, and Postgres refuses to `ALTER TABLE ... DROP COLUMN` on a table
that has pending deferred trigger events — which is exactly what this data
write leaves behind. Doing both in one file raises ``ObjectInUse`` the moment
there is a single row to update, so it passed against an empty test database
and failed against the first real one. Two migrations are two transactions:
this one commits, and the schema change starts clean.

Reversing does nothing. Once a product carries a chart there is no way to tell
whether the owner chose it or this migration did, and guessing would take a
chart away from a product he linked by hand.
"""
from django.db import migrations


def resolve_charts(apps, schema_editor):
    """Write the fit's standard chart onto every product that was relying on it.

    Only where nothing more specific already answers: the product's own chart
    and its category's both win over the fit fallback, so a product that has
    either is left exactly as it is.
    """
    Product = apps.get_model('product', 'Product')
    SizeChart = apps.get_model('product', 'SizeChart')

    by_fit = {}
    for chart in SizeChart.objects.exclude(fit=''):
        by_fit.setdefault(chart.fit, chart)
    if not by_fit:
        return

    candidates = (Product.objects
                  .filter(size_chart__isnull=True)
                  .exclude(fit='')
                  .select_related('category'))
    for product in candidates:
        if product.category_id and product.category.size_chart_id:
            continue
        chart = by_fit.get(product.fit)
        if chart is not None:
            product.size_chart = chart
            product.save(update_fields=['size_chart'])


def unresolve(apps, schema_editor):
    """Nothing to undo — see the module docstring."""


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0019_tagkind_printmethod'),
    ]

    operations = [
        migrations.RunPython(resolve_charts, unresolve),
    ]
