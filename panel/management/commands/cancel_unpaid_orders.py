"""Cancel orders nobody paid for within three days of placing them.

An order is placed before it is paid for. Most are paid within minutes; the
rest wait, some for a payment through the shop's admin on Telegram, most for
nothing at all. They used to wait forever, reading "Toʻlanmoqda" in the panel
as though someone might still pay. This moves each one to cancelled once it
is older than ``payment.services.UNPAID_ORDER_DAYS`` (§17 #373).

Nothing comes back when it does: an unpaid order holds no stock and no use of
a promo code. A payment that lands later is still taken - a gateway's
callback makes a cancelled order paid, and staff can mark it paid in the
panel - so a customer who pays late is not lost, only the order's place in
the list of ones to chase.

Each move goes through ``panel.services.set_status``, so it is in the order's
trail with the note ``AUTO_CANCEL_NOTE`` and the panel shows who did it as
"avtomatik".

Run daily by ``deploy/systemd/graphix-cancel-unpaid.timer``. Usage::

    python manage.py cancel_unpaid_orders             # older than 3 days
    python manage.py cancel_unpaid_orders --days 7
    python manage.py cancel_unpaid_orders --dry-run   # list them, change nothing
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from panel.models import AUTO_CANCEL_NOTE
from panel.services import set_status
from payment.models import Order
from payment.services import UNPAID_ORDER_DAYS, stale_unpaid_orders


class Command(BaseCommand):
    # Said as the filter does it: counted from when the order was placed.
    help = 'Cancel orders still awaiting payment more than --days days after they were placed.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=UNPAID_ORDER_DAYS,
                            help='Age in days, counted from when the order was placed, '
                                 'above which an unpaid order is cancelled.')
        parser.add_argument('--dry-run', action='store_true',
                            help='List what would be cancelled, but change nothing.')

    def handle(self, *args, **options):
        days = options['days']
        # Nought would cancel an order placed a second ago, while its customer
        # is on the gateway's page paying for it.
        if days < 1:
            raise CommandError('--days must be 1 or more.')
        stale = stale_unpaid_orders(days, timezone.now())

        if options['dry_run']:
            orders = list(stale)
            for order in orders:
                self.stdout.write('  %s  %s  %s  %s' % (
                    order.order_no or order.pk,
                    timezone.localtime(order.created_at).strftime('%Y-%m-%d %H:%M'),
                    order.payment_method, order.total_price))
            self.stdout.write(f'{len(orders)} unpaid order(s) older than {days} days.')
            return

        cancelled = []
        for pk in list(stale.values_list('pk', flat=True)):
            with transaction.atomic():
                # Asked again of the row itself, locked: a payment may have
                # landed since the list was read, and a paid order is a sale
                # this must never cancel.
                order = stale.select_for_update().filter(pk=pk).first()
                if order is None:
                    continue
                set_status(order, Order.Status.CANCELLED, note=AUTO_CANCEL_NOTE)
            cancelled.append(order.order_no or str(order.pk))

        # The numbers go in the log, so "why was my order cancelled" can be
        # answered from the journal as well as from the trail.
        self.stdout.write(self.style.SUCCESS(
            f'Cancelled {len(cancelled)} unpaid order(s) older than {days} days'
            + (': ' + ', '.join(cancelled) if cancelled else '.')))
