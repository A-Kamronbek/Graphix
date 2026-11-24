"""Hold "Siz uchun" by likes against the most-liked list (plan §9 Phase 13 item 4).

    python manage.py recommend_report            # the last 30 days
    python manage.py recommend_report --days 7

For each counted row: how often a signed-in visitor was shown it, how often a
design was opened from it, and the one as a share of the other. If the row
ordered by likes does not beat the most-liked one, the plan says to keep the
simpler thing.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils import timezone

from product import recommend
from product.models import RowStat

NAMES = {
    recommend.FOR_YOU: '"Siz uchun", by the visitor\'s likes',
    recommend.POPULAR: '"Siz uchun", most liked (the baseline)',
    recommend.SIMILAR: 'Similar designs on a product page',
}


class Command(BaseCommand):
    help = 'Shows how often the recommended rows are shown and opened.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30,
                            help='How many days back to count (default 30).')

    def handle(self, *args, days, **options):
        since = timezone.localdate() - timedelta(days=days - 1)
        totals = {row['row']: row for row in
                  RowStat.objects.filter(day__gte=since).values('row')
                  .annotate(shown_sum=Sum('shown'), clicked_sum=Sum('clicked'))}
        self.stdout.write('Since %s:' % since.isoformat())
        for row in recommend.ROWS:
            found = totals.get(row, {})
            shown, clicked = found.get('shown_sum') or 0, found.get('clicked_sum') or 0
            share = '%.1f%%' % (100 * clicked / shown) if shown else 'no data'
            self.stdout.write('  %-42s shown %6d · opened %6d · %s'
                              % (NAMES[row], shown, clicked, share))
