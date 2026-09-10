"""Make the catalogue slugs required, now that 0011 has filled them in.

Step 3 of the three-step pattern for adding a unique NOT NULL column to a table
that already has rows: add it nullable (0010), populate it (0011), tighten it
(here). Splitting it this way means the migration never has to invent a value.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0011_populate_slugs_and_stock'),
    ]

    operations = [
        migrations.AlterField(
            model_name='category',
            name='slug',
            field=models.SlugField(max_length=255, unique=True),
        ),
        migrations.AlterField(
            model_name='product',
            name='slug',
            field=models.SlugField(max_length=255, unique=True),
        ),
    ]
