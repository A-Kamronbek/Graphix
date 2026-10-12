"""Write each existing size's place in the order sizes are sold in.

The place is worked out from the label, as ``Size.save`` works it out for a
size saved from now on. The ladder is repeated here and not imported from the
model: a migration is a frozen snapshot and has to give the same answer when
the code has moved on.
"""
from django.db import migrations

LADDER = ('XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', '2XL', 'XXXL', '3XL', '4XL', '5XL')
OFF_LADDER = 1000


def rank(label):
    """The place a size's label asks for; after the ladder when it is not on it."""
    label = (label or '').strip().upper()
    return (LADDER.index(label) + 1) * 10 if label in LADDER else OFF_LADDER


def place(apps, schema_editor):
    """Write each existing size's place onto its row."""
    Size = apps.get_model('product', 'Size')
    for size in Size.objects.all():
        Size.objects.filter(pk=size.pk).update(order=rank(size.size))


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0026_size_order'),
    ]

    operations = [
        # Going back needs nothing undone: the column goes with 0026.
        migrations.RunPython(place, migrations.RunPython.noop),
    ]
