"""Give the shop's size chart to the products that have none (§17 #363).

`0028` put the owner's figures on one chart and left alone the products that
pointed at no chart at all: which products a chart describes was his choice.
He has made it. Every product without a chart takes the shop's.

A product takes it only where that cannot be wrong:

* the shop has exactly one chart, so there is no question of which;
* the product reaches no chart through its category either;
* every size the product is made in has a row on the chart. A product in a
  size the chart does not have is some other garment, and a table that
  leaves its size out would be worse than no table.

A product that already has a chart is never touched, so running this again
changes nothing.

There is no way back: which products had no chart is not written down
anywhere, and taking the chart off all of them would undo the owner's own
choices as well.
"""
from django.db import migrations


def attach(apps, schema_editor):
    """Point each product with no chart at the shop's only one."""
    Product = apps.get_model('product', 'Product')
    SizeChart = apps.get_model('product', 'SizeChart')
    SizeChartRow = apps.get_model('product', 'SizeChartRow')
    Variant = apps.get_model('product', 'Variant')

    charts = list(SizeChart.objects.order_by('pk')[:2])
    if len(charts) != 1:
        return
    chart = charts[0]
    on_chart = set(SizeChartRow.objects.filter(chart=chart)
                   .values_list('size_id', flat=True))

    bare = Product.objects.filter(size_chart__isnull=True).exclude(
        category__size_chart__isnull=False)
    for product in bare:
        made_in = set(Variant.objects.filter(product=product)
                      .values_list('size_id', flat=True))
        if made_in and made_in <= on_chart:
            Product.objects.filter(pk=product.pk).update(size_chart=chart)


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0028_owner_size_chart'),
    ]

    operations = [
        migrations.RunPython(attach, migrations.RunPython.noop),
    ]
