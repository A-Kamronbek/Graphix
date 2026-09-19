"""The measurements behind the two size charts, in one place.

Two charts, a regular cut and an oversize one, seeded by migration 0016 back
when a product carried its cut as a field. The field is gone (§17 #172) and the
charts are not: they are two ordinary charts the owner attaches to whichever
products they describe. The numbers live here so anything that needs to rebuild
the rows — the demo-catalogue reset, a future admin action — uses the same table
rather than its own copy.

Migration ``0016_seed_size_charts`` deliberately keeps its own copy instead of
importing this module. A migration is a frozen snapshot and has to keep working
when the code moves on; that is the same reason ``unique_slug``'s logic is
repeated in the migration that backfilled slugs.

**The numbers are provisional until a real garment is measured.** Phase 11
verifies them against actual stock before launch — a chart that disagrees with
what arrives in the parcel is worse than no chart (§17 #95). They are typical
values for a 200 g/m² cotton tee, measured flat, in centimetres.
"""

# size: (chest, length, shoulder, sleeve)
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

#: Which measurements belong to which chart, by the name migration 0016 seeded
#: it under. The charts used to be found by their ``fit``; that column is gone
#: with the cut it named (§17 #172), and a chart has nothing else stable on it —
#: a name and a picture is the whole of it. Matching on the seeded name is
#: therefore the key, and it is only ever used by the demo-catalogue reset,
#: which is a developer command. A chart the owner has renamed or added simply
#: is not in here and keeps whatever rows it has.
BY_NAME = {
    'Oddiy qolip (regular)': REGULAR,
    'Oversize qolip': OVERSIZE,
}


def rebuild_rows(sizes):
    """Re-create the seeded charts' rows against the ``sizes`` mapping given.

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
