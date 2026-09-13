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


class Command(BaseCommand):
    help = 'Delete anonymous carts that have not been touched for a while.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30,
                            help='Age in days above which a guest cart is deleted.')
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
