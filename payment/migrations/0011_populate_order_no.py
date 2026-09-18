"""Give every existing order a customer-facing number so ``order_no`` can be
made NOT NULL.

Numbers are ``GX-YYMMDD-NNNN``, sequential within the order's own creation day
in local time, assigned in ``created_at`` order — so the historical numbering
reads the way it would have if the field had existed all along.
"""
from django.db import migrations
from django.utils import timezone


def populate(apps, schema_editor):
    Order = apps.get_model('payment', 'Order')

    counters = {}
    for order in Order.objects.filter(order_no__isnull=True).order_by('created_at', 'pk'):
        day = timezone.localtime(order.created_at).date()
        prefix = f"GX-{day:%y%m%d}-"
        seq = counters.get(prefix, 0) + 1
        counters[prefix] = seq
        order.order_no = f"{prefix}{seq:04d}"
        order.save(update_fields=['order_no'])


def unpopulate(apps, schema_editor):
    """Clear the numbers again so 0010 can be unapplied."""
    apps.get_model('payment', 'Order').objects.update(order_no=None)


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0010_deliveryoption_pickuppoint_order_delivery_price_and_more'),
    ]

    operations = [
        migrations.RunPython(populate, unpopulate),
    ]
