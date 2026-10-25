"""Delete return and exchange requests closed more than a year ago.

The privacy policy tells the customer a request and its photographs are kept
a year after it is closed (§17 #406). Nothing else deletes one, so this is
what makes that sentence true. A request is closed when staff mark it
"Rad etildi" or "Yakunlandi"; opening it again clears the date, and an open
request is never touched however old it is.

The photographs go with their rows: each one's file and renditions are
deleted by the same receiver every other photograph uses.

Usage::

    python manage.py prune_return_requests             # closed over a year ago
    python manage.py prune_return_requests --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.legal import RETURN_KEEP_MONTHS
from payment.models import ReturnRequest


def cutoff(now=None):
    """The moment before which a closed request has been kept long enough.

    Months counted as calendar months, the way the policy says them: closed
    on 15 March, deleted from 15 March a year later.
    """
    now = now or timezone.now()
    years, months = divmod(now.month - 1 - RETURN_KEEP_MONTHS, 12)
    year, month = now.year + years, months + 1
    # The 31st of a month without one is the last day of that month.
    for day in (now.day, 30, 29, 28):
        try:
            return now.replace(year=year, month=month, day=day)
        except ValueError:
            continue
    return now.replace(year=year, month=month, day=28)


class Command(BaseCommand):
    help = 'Delete return requests closed more than the kept period ago, with their photographs.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would go, but delete nothing.')

    def handle(self, *args, **options):
        stale = ReturnRequest.objects.filter(status__in=ReturnRequest.CLOSED,
                                             closed_at__lt=cutoff())
        count = stale.count()
        if options['dry_run']:
            self.stdout.write(f'{count} closed return request(s) past the kept period.')
            return
        with transaction.atomic():
            # Row by row, so each photograph's delete receiver runs.
            for request in stale:
                request.delete()
        self.stdout.write(self.style.SUCCESS(
            f'Deleted {count} closed return request(s) past the kept period.'))
