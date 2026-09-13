"""Seed the two size charts — one per fit — and their measured rows.

The catalogue has exactly two cuts (§17 #70), and measurements are a property
of the cut, so two charts cover everything. Tagging each with its ``fit`` is
what lets ``Product.resolve_size_chart`` find them without the owner linking a
chart to every product by hand.

The chart *image* is not seeded here. It lives in the static tree as
``img/size_guide.png`` so the owner can overwrite it with no deploy (§17 #69);
these rows are the structured half, which is what a screen reader and a search
engine read, and what the product page highlights the chosen size in.

**The numbers are provisional until a real garment is measured.** Phase 11
verifies them against actual stock before launch — a chart that disagrees with
what arrives in the parcel is worse than no chart (§17 #95). They are typical
values for a 200 g/m² cotton tee, flat, in centimetres.

``get_or_create`` throughout, so a re-run never overwrites a correction the
owner has since made in the admin.
"""
from django.db import migrations


# size: (chest, length, shoulder, sleeve), measured flat, in centimetres.
REGULAR = {
    'S':  ('48.0', '69.0', '43.0', '19.0'),
    'M':  ('51.0', '71.0', '46.0', '20.0'),
    'L':  ('54.0', '73.0', '49.0', '21.0'),
    'XL': ('57.0', '75.0', '52.0', '22.0'),
}
OVERSIZE = {
    'S':  ('54.0', '70.0', '52.0', '21.0'),
    'M':  ('57.0', '72.0', '55.0', '22.0'),
    'L':  ('60.0', '74.0', '58.0', '23.0'),
    'XL': ('63.0', '76.0', '61.0', '24.0'),
}

# Written in three languages, not translated from one (§9 Phase 3). The ±1 cm
# line is the honest disclaimer: these are hand-measured garments, not a spec.
NOTE_UZ = ('Oʻlchamlar kiyim tekis yotqizilgan holda, santimetrda olingan. '
           'Ishlab chiqarish xususiyatiga koʻra ±1 sm farq boʻlishi mumkin. '
           'Koʻkrak — qoʻltiq ostidan boʻylab oʻlchangan yarim aylana.')
NOTE_RU = ('Замеры сняты с изделия, разложенного на плоскости, в сантиметрах. '
           'Допустимое отклонение — ±1 см. Грудь — половина обхвата, '
           'измеренная под проймой.')
NOTE_EN = ('Measured flat, in centimetres. Allow ±1 cm — these are real '
           'garments, not a spec sheet. Chest is the half-circumference taken '
           'just below the armhole.')

CHARTS = [
    {
        'name': 'Oddiy qolip (regular)',
        'fit': 'regular',
        'rows': REGULAR,
    },
    {
        'name': 'Oversize qolip',
        'fit': 'oversize',
        'rows': OVERSIZE,
    },
]


def seed(apps, schema_editor):
    Size = apps.get_model('product', 'Size')
    SizeChart = apps.get_model('product', 'SizeChart')
    SizeChartRow = apps.get_model('product', 'SizeChartRow')

    # The sizes the charts describe have to exist as rows, and on a fresh
    # database they do not. get_or_create rather than create: an existing shop
    # already has them and must keep the ones its variants point at.
    sizes = {}
    for label in ('S', 'M', 'L', 'XL'):
        sizes[label] = Size.objects.filter(size=label).first() or Size.objects.create(size=label)

    for spec in CHARTS:
        chart, _created = SizeChart.objects.get_or_create(
            fit=spec['fit'],
            defaults={
                'name': spec['name'],
                'note': NOTE_UZ, 'note_ru': NOTE_RU, 'note_en': NOTE_EN,
            },
        )
        for order, (label, values) in enumerate(spec['rows'].items()):
            chest, length, shoulder, sleeve = values
            SizeChartRow.objects.get_or_create(
                chart=chart, size=sizes[label],
                defaults={
                    'chest_cm': chest, 'length_cm': length,
                    'shoulder_cm': shoulder, 'sleeve_cm': sleeve,
                    'order': order,
                },
            )


def unseed(apps, schema_editor):
    """Remove the seeded charts — but never one a product or category points at."""
    SizeChart = apps.get_model('product', 'SizeChart')
    SizeChart.objects.filter(
        fit__in=[spec['fit'] for spec in CHARTS],
        products__isnull=True, categories__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0015_sizechart_fit'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
