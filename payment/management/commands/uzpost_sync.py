"""Follow every live Uzpost shipment's status (§9 Phase 22 items 10 to 12).

Uzpost does not call the shop when a parcel moves, so the shop asks. Each
live shipment is read once a run; a new status is recorded, the order moves
forward if the status says so, the owner is told once about a status the shop
does not act on, and an office order's customer is sent one SMS when the
parcel waits at the office. ``payment.shipments.follow`` does all of it; this
only walks the list.

Calls are spaced, and a run stops after several failures in a row: Uzpost
down for a while is a run that ends early, not a run that asks a hundred times
and fills the log. Pages never wait on this; they read the database.

A delivered shipment is not read again: nothing after delivery moves an
order.

Run every 30 minutes by ``deploy/systemd/graphix-uzpost.timer``. Usage::

    python manage.py uzpost_sync
    python manage.py uzpost_sync --dry-run   # list what would be read
"""
import time

from django.core.management.base import BaseCommand

from core import uzpost
from payment import shipments
from payment.models import Shipment

#: Seconds between two calls to Uzpost.
PAUSE = 0.5

#: Failures in a row after which the run gives up until the next one.
MAX_FAILURES = 5


class Command(BaseCommand):
    help = "Read each live Uzpost shipment's status and follow it."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='List the shipments that would be read, and read none.')

    def handle(self, *args, **options):
        live = (Shipment.objects.filter(cancelled_at__isnull=True)
                .exclude(status__in=shipments.DELIVERED)
                .select_related('order__delivery_option')
                .order_by('read_at', 'id'))
        if options['dry_run']:
            rows = list(live)
            for shipment in rows:
                self.stdout.write(f"  {shipment.order.order_no}  {shipment.number}  "
                                  f"{shipment.status}")
            self.stdout.write(f"{len(rows)} live shipment(s).")
            return
        if not uzpost.configured():
            self.stdout.write('Uzpost is not set up (UZPOST_LOGIN, UZPOST_PASSWORD); nothing read.')
            return

        read = failed = in_a_row = 0
        for index, shipment in enumerate(live):
            if index:
                time.sleep(PAUSE)
            if shipments.follow(shipment):
                read += 1
                in_a_row = 0
                continue
            failed += 1
            in_a_row += 1
            if in_a_row >= MAX_FAILURES:
                self.stderr.write(f"Uzpost failed {in_a_row} times in a row; stopping.")
                break
        self.stdout.write(f"Read {read} shipment(s); Uzpost did not answer for {failed}.")
