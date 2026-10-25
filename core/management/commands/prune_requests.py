"""Delete customers' requests the privacy policy says are no longer kept.

Two kinds, each kept a year (§17 #406):

* a return or exchange request, a year after it is closed. A request is
  closed when staff mark it "Rad etildi" or "Yakunlandi"; opening it again
  clears the date, and an open request is never touched however old it is;
* a suggested design, a year after it was sent. It has no closing: the owner
  answers it by phone or Telegram and marks it read, and a design nobody had
  read would otherwise be kept for ever.

Nothing else deletes either, so this is what makes the policy's sentences
true. The photographs go with their rows: each one's file and renditions are
deleted by the same receiver every other photograph uses.

It replaces `prune_return_requests` (Phase 23 part B), which knew only the
first kind, before either was deployed.

Usage::

    python manage.py prune_requests             # past the kept period
    python manage.py prune_requests --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.legal import REQUEST_KEEP_MONTHS
from core.models import DesignRequest
from payment.models import ReturnRequest


def cutoff(now=None):
    """The moment before which a request has been kept long enough.

    Months counted as calendar months, the way the policy says them: closed
    on 15 March, deleted from 15 March a year later.
    """
    now = now or timezone.now()
    years, months = divmod(now.month - 1 - REQUEST_KEEP_MONTHS, 12)
    year, month = now.year + years, months + 1
    # The 31st of a month without one is the last day of that month.
    for day in (now.day, 30, 29, 28):
        try:
            return now.replace(year=year, month=month, day=day)
        except ValueError:
            continue
    return now.replace(year=year, month=month, day=28)


def stale(now=None):
    """What has been kept long enough: ``(label, queryset)`` for each kind."""
    before = cutoff(now)
    return (
        ('closed return request(s)',
         ReturnRequest.objects.filter(status__in=ReturnRequest.CLOSED,
                                      closed_at__lt=before)),
        ('design suggestion(s)',
         DesignRequest.objects.filter(created_at__lt=before)),
    )


class Command(BaseCommand):
    help = ('Delete return requests closed, and design suggestions sent, more than '
            'the kept period ago, with their photographs.')

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would go, but delete nothing.')

    def handle(self, *args, **options):
        for label, rows in stale():
            count = rows.count()
            if options['dry_run']:
                self.stdout.write(f'{count} {label} past the kept period.')
                continue
            with transaction.atomic():
                # Row by row, so each photograph's delete receiver runs.
                for row in rows:
                    row.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Deleted {count} {label} past the kept period.'))
