"""Write the WebP renditions of every photograph uploaded before Phase 9.

New photographs are re-encoded by the signal that runs when their row commits;
everything already in ``media/`` predates it. Run once after deploying Phase 9,
and again any time the rendition widths change::

    python manage.py build_renditions            # only what is missing
    python manage.py build_renditions --force    # everything, again

Idempotent, and it deletes nothing: a row whose file has gone missing is
counted and skipped, never cleared.
"""
from django.core.management.base import BaseCommand

from product.models import ImageP, ReviewImage, SizeChart, Slide
from product.signals import build_renditions, measure_image


class Command(BaseCommand):
    """Backfill renditions for product and review photographs, and chart sizes."""

    help = 'Build the WebP renditions of photographs uploaded before Phase 9.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help='re-encode photographs that already have their renditions')

    def handle(self, *args, **options):
        """Walk the photograph tables, then measure the size charts.

        `Slide` is here so that `--force` can rebuild the home page's cards
        after a rendition width changes. Slides are newer than Phase 9 and so
        never need the backfill this command was written for, but a table
        left out of a loop like this one is a table nobody notices is missing
        until the widths move.
        """
        force = options['force']
        for model in (ImageP, ReviewImage, Slide):
            done = skipped = failed = 0
            for row in model.objects.all().iterator():
                if not row.has_photo:
                    skipped += 1
                    continue
                if row.sources() and not force:
                    skipped += 1
                    continue
                if build_renditions(model, row.pk):
                    done += 1
                    self.stdout.write('  %s' % row.photo_file.name)
                else:
                    failed += 1
            self.stdout.write(self.style.SUCCESS(
                '%s: %d built, %d already done, %d unreadable'
                % (model.__name__, done, skipped, failed)))

        charts = 0
        for chart in SizeChart.objects.all().iterator():
            if chart.has_photo and (force or not chart.width):
                charts += measure_image(SizeChart, chart.pk)
        self.stdout.write(self.style.SUCCESS('SizeChart: %d measured' % charts))
