"""Delivery times on the delivery tiers, set for the two Uzpost rows (§17 #301).

The owner's figures: one to two days to a post office, one to six to the door.
Any other row keeps 0, which states no time, until the owner sets one.
"""
from django.db import migrations, models

#: The owner's figures in days, (fewest, most), by tier code.
DAYS = {'uzpost_office': (1, 2), 'uzpost_door': (1, 6)}


def set_days(apps, schema_editor):
    """Write the owner's figures onto the rows that exist."""
    DeliveryOption = apps.get_model('payment', 'DeliveryOption')
    for code, (low, high) in DAYS.items():
        DeliveryOption.objects.filter(code=code).update(days_min=low, days_max=high)


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0023_consent_versions'),
    ]

    operations = [
        migrations.AddField(
            model_name='deliveryoption',
            name='days_min',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='deliveryoption',
            name='days_max',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.RunPython(set_days, migrations.RunPython.noop),
    ]
