"""Make ``order_no`` required, now that 0011 has numbered every existing order.

Stays ``blank=True`` so forms and the admin don't demand it: ``Order.save()``
assigns the number on first save.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0011_populate_order_no'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='order_no',
            field=models.CharField(blank=True, db_index=True, max_length=20, unique=True),
        ),
    ]
