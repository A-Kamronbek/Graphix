"""Narrow ``Product.fit`` to two values: regular and oversize.

Phase 4 shipped a third, ``boxy``, taken from the tag examples in plan §7 rather
than from anything the catalogue needed. The owner has confirmed two fits, so
the third goes before any real product is entered against it - changing this
after the catalogue exists is a data problem, not a schema one.

Any row already carrying ``boxy`` is folded into ``oversize``, the nearer of the
two, rather than blanked: a product that was described as a loose fit should not
silently lose its spec. The reverse leaves those rows as ``oversize``, because
the migration cannot know which of them started out that way - it restores the
choice, not the data, and that is stated here so nobody assumes otherwise.
"""
from django.db import migrations, models


def boxy_to_oversize(apps, schema_editor):
    """Fold the dropped fit into the nearest surviving one."""
    Product = apps.get_model('product', 'Product')
    Product.objects.filter(fit='boxy').update(fit='oversize')


def noop(apps, schema_editor):
    """Reverse is a no-op: see the module docstring."""


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0013_seed_tags'),
    ]

    operations = [
        migrations.RunPython(boxy_to_oversize, noop),
        migrations.AlterField(
            model_name='product',
            name='fit',
            field=models.CharField(
                blank=True,
                choices=[('regular', 'Oddiy'), ('oversize', 'Oversize')],
                default='',
                max_length=20,
            ),
        ),
    ]
