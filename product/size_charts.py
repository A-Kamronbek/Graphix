"""The shop's size chart, in one place: what each size measures, and who it fits.

The figures are the owner's own, from the chart he supplied on 2026-10-11
(§17 #357). They replaced two provisional charts, a regular cut and an
oversize one, that had stood in "until a real garment is measured" (§17 #95).
Migration ``0028_owner_size_chart`` wrote them onto the live rows; they live
here as well so that anything that has to build the rows again, such as the
demo-catalogue reset, uses the same table and not a copy of its own. The
drawn chart, ``docs/brand/size-guide.html``, carries the same figures, and a
test holds the two together.

Migration 0028 deliberately keeps its own copy and does not import this
module. A migration is a frozen snapshot and has to keep working when the
code moves on.
"""

#: The name the chart is kept under. The owner sees it in the panel, where a
#: product is given its chart; a shopper never does while it is the only one.
NAME = 'Futbolka'

# size: (chest, length, shoulder, sleeve), in centimetres, taken from the
# garment. The chest is the measure all the way round, not half of it.
MEASURES = {
    'XS': ('110.0', '65.0', '60.0', '17.0'),
    'S':  ('114.0', '68.0', '62.0', '18.0'),
    'M':  ('118.0', '70.0', '63.0', '19.0'),
    'L':  ('124.0', '75.0', '66.0', '20.0'),
    'XL': ('126.0', '76.0', '68.0', '21.0'),
}

# size: ((height from, to) in centimetres, (weight from, to) in kilograms).
# The owner's guide to choosing: a range, and the ranges overlap on purpose,
# because between two sizes the choice is how loose the shirt should sit.
FIT = {
    'XS': ((155, 165), (45, 55)),
    'S':  ((160, 170), (55, 65)),
    'M':  ((165, 178), (65, 75)),
    'L':  ((170, 185), (75, 85)),
    'XL': ((175, 190), (85, 100)),
}

#: Which measurements belong to which chart, by name. A chart has nothing
#: else stable on it: a name and a picture is the whole of it (§17 #172). It
#: is only ever used by the demo-catalogue reset, which is a developer
#: command. A chart the owner has renamed or added is not in here and keeps
#: whatever rows it has.
BY_NAME = {
    NAME: MEASURES,
}


def fit_rows(sizes=()):
    """The choosing table as rows a template can print.

    ``sizes`` are the :class:`~product.models.Size` rows a page already has.
    A row whose label one of them carries is given that size's id, which is
    how the product page marks the row for the size the customer has picked.
    """
    ids = {size.size.strip().upper(): size.pk for size in sizes}
    return [
        {'label': label, 'size_id': ids.get(label), 'height': height, 'weight': weight}
        for label, (height, weight) in FIT.items()
    ]


def rebuild_rows(sizes):
    """Re-create the seeded chart's rows against the ``sizes`` mapping given.

    ``sizes`` maps a label ('S', 'M', …) to a :class:`~product.models.Size`.
    Used after something has replaced the Size rows — the demo-catalogue reset
    does exactly that, and before this existed it took the charts down with
    them, so a developer's local site quietly lost its size guide (§17 #78).
    """
    from .models import SizeChart, SizeChartRow

    for chart in SizeChart.objects.filter(name__in=BY_NAME):
        table = BY_NAME[chart.name]
        SizeChartRow.objects.filter(chart=chart).delete()
        for order, (label, values) in enumerate(table.items()):
            size = sizes.get(label)
            if size is None:
                continue
            chest, length, shoulder, sleeve = values
            SizeChartRow.objects.create(
                chart=chart, size=size, chest_cm=chest, length_cm=length,
                shoulder_cm=shoulder, sleeve_cm=sleeve, order=order,
            )
