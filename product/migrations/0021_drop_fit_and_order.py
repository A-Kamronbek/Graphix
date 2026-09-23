"""Drop ``fit`` from products and size charts, and ``order`` from the lookups.

Two decisions, in one migration because they touch one app and
neither writes a row.

**Qolip (``fit``) is gone** (§17 #172). It was two fixed values, regular and
oversize, settled in §17 #70 and deliberately left alone a day earlier. He
reversed it: a cut is something the owner wants to *say* about a garment, and a
tag says it already — at any value he likes, with no schema behind it. Two
choices had been buying a select on the product form, a select on every size
chart, a column on two tables and a third cut that would have been a migration.
Migration 0020 has already resolved the chart fallback into the data, so no
product loses its size guide when the column goes.

**``order`` is gone from ``TagKind`` and ``PrintMethod``** (§17 #171). Four rows
in each; a sort number the owner has to invent before he can add a print method
is a box that costs a decision and returns nothing. Both order by id now, which
is oldest first — the order he added them in.

Reversing re-creates all four columns empty. The columns come back; what was in
them does not, which is the honest half of a reversal.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0020_resolve_size_charts'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='printmethod',
            options={'ordering': ['id'], 'verbose_name': 'Bosma usuli',
                     'verbose_name_plural': 'Bosma usullari'},
        ),
        migrations.AlterModelOptions(
            name='tagkind',
            options={'ordering': ['id'], 'verbose_name': 'Teg turi',
                     'verbose_name_plural': 'Teg turlari'},
        ),
        migrations.RemoveField(
            model_name='printmethod',
            name='order',
        ),
        migrations.RemoveField(
            model_name='product',
            name='fit',
        ),
        migrations.RemoveField(
            model_name='sizechart',
            name='fit',
        ),
        migrations.RemoveField(
            model_name='tagkind',
            name='order',
        ),
    ]
