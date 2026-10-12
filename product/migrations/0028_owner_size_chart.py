"""Replace the two provisional size charts with the owner's one.

The two charts seeded by 0016, a regular cut and an oversize one, carried
typical figures "until a real garment is measured" (§17 #95). The owner has
now supplied the shop's own chart: one cut, five sizes from XS to XL, and the
chest given all the way round (§17 #357).

One chart is kept and takes the new figures; a product or a category that
pointed at the other is moved to it, and the other is deleted. A chart the
owner made himself, under any other name, is left exactly as it is. On a
database where neither seeded chart exists any more, the owner's chart is
made new and attached to nothing: which products it describes is his choice.

Run a second time it finds the chart it made the first time, by its new name,
and writes the same rows onto it: it never makes a second one.

The figures are repeated here and not imported from ``product/size_charts``,
for the reason 0016 gives: a migration is a frozen snapshot.

There is no way back. The figures this replaces were placeholders, and
reversing leaves the owner's in place.
"""
from django.db import migrations

#: The two charts 0016 seeded, by the names it gave them.
SEEDED = ('Oddiy qolip (regular)', 'Oversize qolip')
#: The one that is kept when both are there. Either would do; this is the
#: cut nearer to the owner's figures.
KEEP = 'Oversize qolip'

NAME = 'Futbolka'

# size: (chest all round, length, shoulder, sleeve), in centimetres.
MEASURES = {
    'XS': ('110.0', '65.0', '60.0', '17.0'),
    'S':  ('114.0', '68.0', '62.0', '18.0'),
    'M':  ('118.0', '70.0', '63.0', '19.0'),
    'L':  ('124.0', '75.0', '66.0', '20.0'),
    'XL': ('126.0', '76.0', '68.0', '21.0'),
}

# The line under the table: how far a shirt may differ from it. The Uzbek and
# the Russian are the owner's own words; each language is written, not
# translated from another (§9 Phase 3). That the figures are centimetres
# taken from the garment is said by the page above the table.
NOTE_UZ = 'Oʻlchashda 1–3 sm farq boʻlishi mumkin.'
NOTE_RU = 'Допустимая погрешность: 1–3 см.'
NOTE_EN = 'Allow a difference of 1–3 cm.'

#: The place of each of these sizes, as 0027 gives it. A size this
#: migration has to create is written with its place, because a migration's
#: models do not run the ``save`` that works it out.
ORDER = {'XS': 20, 'S': 30, 'M': 40, 'L': 50, 'XL': 60}


def replace(apps, schema_editor):
    """Put the owner's figures on one chart and fold the other into it."""
    Size = apps.get_model('product', 'Size')
    SizeChart = apps.get_model('product', 'SizeChart')
    SizeChartRow = apps.get_model('product', 'SizeChartRow')
    Product = apps.get_model('product', 'Product')
    Category = apps.get_model('product', 'Category')

    # Whatever case a label was typed in, it is the same size: a second "XS"
    # beside an "xs" would be a size no product is made in.
    sizes = {}
    for label in MEASURES:
        sizes[label] = (Size.objects.filter(size__iexact=label).order_by('pk').first()
                        or Size.objects.create(size=label, order=ORDER[label]))

    # The chart this made on an earlier run comes first, then the seeded one
    # that is kept, then the other seeded one.
    known = list(SizeChart.objects.filter(name__in=SEEDED + (NAME,)).order_by('pk'))
    chart = (next((one for one in known if one.name == NAME), None)
             or next((one for one in known if one.name == KEEP), None)
             or (known[0] if known else None)
             or SizeChart.objects.create(name=NAME))

    chart.name = NAME
    chart.note, chart.note_ru, chart.note_en = NOTE_UZ, NOTE_RU, NOTE_EN
    chart.save()

    SizeChartRow.objects.filter(chart=chart).delete()
    for order, (label, values) in enumerate(MEASURES.items()):
        chest, length, shoulder, sleeve = values
        SizeChartRow.objects.create(
            chart=chart, size=sizes[label], chest_cm=chest, length_cm=length,
            shoulder_cm=shoulder, sleeve_cm=sleeve, order=order,
        )

    for other in known:
        if other.pk == chart.pk:
            continue
        Product.objects.filter(size_chart=other).update(size_chart=chart)
        Category.objects.filter(size_chart=other).update(size_chart=chart)
        other.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0027_place_sizes'),
    ]

    operations = [
        migrations.RunPython(replace, migrations.RunPython.noop),
    ]
