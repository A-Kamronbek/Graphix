"""Replace the local catalogue with the eight demo designs used for review.

Why this exists as a command rather than a script: the same eight products are
what every screenshot, every breakpoint sweep and every interaction check in
`docs/design/phase5/` is measured against, and until now they only existed
inside a throwaway test database that `.git/render_all.py` built and destroyed.
A developer opening the site saw whatever scratch rows happened to be there
instead - which is how a real layout defect sat on the product page for days
without anyone noticing: nobody was looking at a page that had four photographs
and four sizes on it.

**This deletes catalogue data.** Products, their images and variants, the
categories, the sizes, and everything that hangs off them - carts, cart lines
and orders - go, because a variant cannot be deleted while an order line still
points at it. It leaves alone the things that are not catalogue: user accounts
(so nobody is locked out of their own dev site), delivery and payment options,
regions and districts, and contact messages.

The photographs live in `docs/design/demo-catalogue/` because `vm/media/` is
gitignored, and are copied into place when they are missing - so this works on a
fresh clone with no further setup.

It refuses to run against anything but a local database: "reset the catalogue"
is a sentence that should never be able to reach production by accident.

    python manage.py seed_demo_catalogue           # asks first
    python manage.py seed_demo_catalogue --noinput
"""
import shutil
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

# slug, Uzbek, Russian, English, price, tag slugs
CATALOGUE = [
    ('rampage',   'Rampage',        'Rampage',        'Rampage',        189000, ['oversize', 'streetwear']),
    ('overdrive', 'Overdrive',      'Overdrive',      'Overdrive',      165000, ['oversize', 'music']),
    ('asterisk',  'Asterisk',       'Asterisk',       'Asterisk',       155000, ['minimal']),
    ('signal',    'Noise / Signal', 'Noise / Signal', 'Noise / Signal', 175000, ['minimal', 'vintage']),
    ('indeks',    'Indeks 100000',  'Индекс 100000',  'Index 100000',   165000, ['vintage']),
    ('quyosh',    'Quyosh',         'Солнце',         'Sun',            179000, ['boxy']),
    ('halqa',     'Halqa',          'Кольцо',         'Ring',           169000, ['minimal', 'boxy']),
    ('fade',      'Fade',           'Fade',           'Fade',           185000, ['streetwear']),
]

SIZES = ('S', 'M', 'L', 'XL')

DESCRIPTION = (
    'Qalin paxta, yuvilgandan keyin shaklini saqlaydi. '
    'Bosma DTF usulida, yorqin va uzoq muddatli.'
)
DESCRIPTION_RU = (
    'Плотный хлопок, держит форму после стирки. '
    'Печать DTF — яркая и долговечная.'
)
DESCRIPTION_EN = (
    'Heavy cotton that keeps its shape after washing. '
    'DTF print: bright, and it lasts.'
)

LOCAL_HOSTS = {'', 'localhost', '127.0.0.1', '::1'}


class Command(BaseCommand):
    help = 'Replace the local catalogue with the eight demo designs (destructive).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--noinput', '--no-input', action='store_true', dest='noinput',
            help='Do not ask for confirmation before deleting the catalogue.',
        )

    def handle(self, *args, **options):
        from cart.models import Cart, CartItem
        from payment.models import Order
        from product import size_charts
        from product.models import (Category, ImageP, PrintMethod, Product,
                                    ProductLike, Review, ReviewImage, Size,
                                    SizeChart, SizeChartRow, Tag, Variant,
                                    default_colour)

        db = settings.DATABASES['default']
        host = (db.get('HOST') or '').strip()
        if host.lower() not in LOCAL_HOSTS:
            raise CommandError(
                'refusing to run: DB_HOST is %r, which is not a local database. '
                'This command deletes the catalogue and is for development only.' % host
            )

        copied = self._place_images()
        if copied:
            self.stdout.write('copied %d photograph(s) into %s'
                              % (copied, settings.MEDIA_ROOT / 'products'))

        counts = {
            'products': Product.objects.count(),
            'variants': Variant.objects.count(),
            'categories': Category.objects.count(),
            'sizes': Size.objects.count(),
            'carts': Cart.objects.count(),
            'orders': Order.objects.count(),
        }
        self.stdout.write('database: %s on %s' % (db['NAME'], host or 'local socket'))
        self.stdout.write('about to delete: ' + ', '.join(
            '%d %s' % (n, label) for label, n in counts.items()))
        self.stdout.write(self.style.WARNING(
            'user accounts, delivery options, pickup points and contact messages '
            'are kept.'))

        if not options['noinput']:
            if input('type "yes" to replace the catalogue: ').strip().lower() != 'yes':
                raise CommandError('cancelled, nothing was deleted')

        with transaction.atomic():
            # Order matters only for readability; the FKs cascade either way.
            Order.objects.all().delete()
            CartItem.objects.all().delete()
            Cart.objects.all().delete()
            ProductLike.objects.all().delete()
            ReviewImage.objects.all().delete()
            Review.objects.all().delete()
            ImageP.objects.all().delete()
            Variant.objects.all().delete()
            Product.objects.all().delete()
            # The CHARTS survive; only their rows go, because the rows point at
            # the Size objects this command is about to replace. Deleting the
            # charts themselves would take the seeded size guide away from every
            # developer who resets the catalogue, which is precisely the
            # "verification and development looking at different sites" problem
            # this command exists to fix (§17 #78).
            SizeChartRow.objects.all().delete()
            Category.objects.all().delete()
            Size.objects.all().delete()

            category = Category.objects.create(
                name='Futbolkalar', name_ru='Футболки', name_en='T-shirts',
                slug='futbolkalar',
            )
            colour = default_colour()
            sizes = [Size.objects.create(size=s) for s in SIZES]
            # Rebuilt against the sizes that now exist, from the one table the
            # measurements live in.
            size_charts.rebuild_rows({s.size: s for s in sizes})
            # A product used to find a chart through its cut; the cut is gone
            # (§17 #172) and a chart now reaches a product only because
            # somebody attached it. The seeded catalogue attaches them itself,
            # alternating, so both charts render somewhere and the size guide
            # is on every demo product exactly as it was before.
            chart_names = list(size_charts.BY_NAME)
            demo_charts = [SizeChart.objects.filter(name=n).first() for n in chart_names]
            demo_charts = [c for c in demo_charts if c is not None]

            for i, (slug, uz, ru, en, price, tag_slugs) in enumerate(CATALOGUE):
                product = Product.objects.create(
                    name=uz, name_ru=ru, name_en=en, slug=slug, category=category,
                    description=DESCRIPTION,
                    description_ru=DESCRIPTION_RU,
                    description_en=DESCRIPTION_EN,
                    gsm=200,
                    material='100% paxta', material_ru='100% хлопок',
                    material_en='100% cotton',
                    # A row now rather than a choice (§17, Phase 7 recheck);
                    # migration 0019 seeds the four the code used to hold.
                    print_method=PrintMethod.objects.filter(slug='dtf').first(),
                    # Alternated so both seeded charts are on something.
                    size_chart=(demo_charts[i % len(demo_charts)] if demo_charts else None),
                    # Phase 6b maintains this; seeded so the hearts are not all zero.
                    likes_count=(i * 7) % 23,
                )
                product.tags.set(Tag.objects.filter(slug__in=tag_slugs))

                if slug == 'rampage':
                    # One product with four photographs, so the gallery rail and
                    # its arrow-key navigation are exercised by the default data.
                    for n in range(1, 5):
                        ImageP.objects.create(product=product, order=n,
                                              picture='products/hero-%d.jpg' % n)
                else:
                    ImageP.objects.create(product=product, order=1,
                                          picture='products/%s.jpg' % slug)

                for size in sizes:
                    Variant.objects.create(
                        product=product, size=size, colour=colour,
                        price=Decimal(price), available=True,
                        # One sold-out size on the first product, so the
                        # struck-through state is visible without editing anything.
                        stock=0 if (slug == 'rampage' and size.size == 'S') else 12,
                    )

        self.stdout.write(self.style.SUCCESS(
            'seeded %d products, %d variants, %d sizes, 1 category'
            % (Product.objects.count(), Variant.objects.count(), Size.objects.count())))
        self.stdout.write('tags reused: %s' % ', '.join(
            Tag.objects.order_by('slug').values_list('slug', flat=True)))

    # ------------------------------------------------------------------ files
    @staticmethod
    def image_names():
        """Every file the catalogue refers to, relative to MEDIA_ROOT."""
        names = ['products/hero-%d.jpg' % n for n in range(1, 5)]
        names += ['products/%s.jpg' % row[0] for row in CATALOGUE if row[0] != 'rampage']
        return names

    def _place_images(self):
        """Copy any missing photograph out of the tracked folder into media.

        `vm/media/` is gitignored, so on a fresh clone the photographs only exist
        under `docs/design/demo-catalogue/`. Copying rather than symlinking keeps
        this working on Windows without developer mode.
        """
        source = settings.BASE_DIR.parent / 'docs' / 'design' / 'demo-catalogue'
        target = settings.MEDIA_ROOT / 'products'
        target.mkdir(parents=True, exist_ok=True)

        copied, missing = 0, []
        for name in self.image_names():
            dest = settings.MEDIA_ROOT / name
            if dest.exists():
                continue
            src = source / dest.name
            if not src.exists():
                missing.append(src)
                continue
            shutil.copyfile(src, dest)
            copied += 1

        if missing:
            raise CommandError(
                'missing %d demo photograph(s); expected them in %s:\n  %s'
                % (len(missing), source, '\n  '.join(p.name for p in missing))
            )
        return copied
