"""Uzpost's ids for regions and districts, and each district's centre (§17 #378, #381).

Columns only, all empty: Uzpost's lists are loaded by `sync_uzpost_regions`,
as the official ones are by `seed_regions`, and no migration loads either.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payment", "0027_seed_telegram_option"),
    ]

    operations = [
        migrations.AddField(
            model_name="district",
            name="latitude",
            field=models.DecimalField(
                blank=True, decimal_places=6, max_digits=9, null=True
            ),
        ),
        migrations.AddField(
            model_name="district",
            name="longitude",
            field=models.DecimalField(
                blank=True, decimal_places=6, max_digits=9, null=True
            ),
        ),
        migrations.AddField(
            model_name="district",
            name="uzpost_id",
            field=models.PositiveBigIntegerField(blank=True, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="region",
            name="uzpost_id",
            field=models.PositiveBigIntegerField(blank=True, null=True, unique=True),
        ),
    ]
