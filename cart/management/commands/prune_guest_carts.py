"""Delete abandoned guest carts.

A guest cart is created the first time an anonymous visitor adds something, and
most are never claimed by an account. They are harmless but they accumulate,
and each one holds PROTECT references to variants, so an old cart can stop the
owner tidying the catalogue.

Only carts with no user are touched, and only open ones: a cart claimed at
login belongs to a customer, and a closed cart is the record of an order.

Usage::

    python manage.py prune_guest_carts               # older than 30 days
    python manage.py prune_guest_carts --days 7
    python manage.py prune_guest_carts --dry-run
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from cart.models import Cart
from cart.services import GUEST_CART_DAYS


class Command(BaseCommand):
    # Said as the filter below does it: by the day the cart was created, not
    # the day it was last used - which is also how the privacy policy states it.
    help = 'Delete open anonymous carts created more than --days days ago.'

    def add_arguments(self, parser):
        # The default is the figure the privacy policy promises (§17 #183).
        parser.add_argument('--days', type=int, default=GUEST_CART_DAYS,
                            help='Age in days, counted from creation, above which a '
                                 'guest cart is deleted.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would go, but delete nothing.')

    def handle(self, *args, **options):
        days = options['days']
        cutoff = timezone.now() - timedelta(days=days)
        stale = Cart.objects.filter(user__isnull=True, status=True, created_at__lt=cutoff)
        count = stale.count()

        if options['dry_run']:
            self.stdout.write(f'{count} guest cart(s) older than {days} days.')
            return

        stale.delete()
        self.stdout.write(self.style.SUCCESS(
            f'Deleted {count} guest cart(s) older than {days} days.'
        ))
