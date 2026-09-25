"""Replace the local catalogue with the eight demo designs used for review.

Why this exists as a command rather than a script: the same eight products are
what every screenshot, every breakpoint sweep and every interaction check in
the screenshots are measured against, and until now they only existed
inside a throwaway test database that `.git/render_all.py` built and destroyed.
A developer opening the site saw whatever scratch rows happened to be there
instead - which is how a real layout defect sat on the product page for days
without anyone noticing: nobody was looking at a page that had four photographs
and four sizes on it.

**This deletes catalogue data.** Products, their images and variants, the
categories, the sizes, the home page's slide cards, and everything that hangs
off them - carts, cart lines and orders - go, because a variant cannot be
deleted while an order line still points at it. It leaves alone the things
that are not catalogue: user accounts (so nobody is locked out of their own
dev site), delivery and payment options, regions and districts, and contact
messages.

The photographs live in `data/demo-catalogue/` because `media/` is
gitignored, and are copied into place when they are missing - so this works on a
fresh clone with no further setup.

It refuses to run against anything but a local database: "reset the catalogue"
is a sentence that should never be able to reach production by accident.

    python manage.py seed_demo_catalogue           # asks first
    python manage.py seed_demo_catalogue --noinput
"""
import shutil
from decimal import Decimal
from pathlib import Path

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

# slug, link, and the alt in the three languages.
#
# The home page renders the no-slides branch when this table is empty, which
# is what every developer's machine showed until these existed - so the
# carousel could not be looked at, and its CLS could not be measured at all
# (§9 Phase 9, measured rather than asserted). The pictures are drawn by
# `docs/design/slides/build.py`; the words on them are Uzbek, because a slide
# is one file for all three languages and the alt is what carries the meaning
# across (§17 #275).
#
# The links carry **no language prefix**, and that is the point: every page on
# this site sits under one (`/uz/`, `/ru/`, `/en/`), a slide holds one link for
# all three, and `LocaleMiddleware` redirects an unprefixed path to the
# visitor's own language. `/uz/shop/` in this column would drop a Russian
# customer into an Uzbek page. Worth knowing before the owner types one.
SLIDES = [
    ('yangi', '/shop/',
     'Yangi dizaynlar: butun kolleksiyani koʻring',
     'Новые дизайны: посмотреть коллекцию',
     'New designs: see the collection'),
    ('yetkazib-berish', '/yetkazib-berish/',
     'Oʻzbekiston boʻylab yetkazib berish, 1–6 kun',
     'Доставка по Узбекистану, 1–6 дней',
     'Delivery across Uzbekistan, 1–6 days'),
    ('olcham', '/olcham-jadvali/',
     'Oʻlcham jadvali: oʻlchamni toʻgʻri tanlang',
     'Таблица размеров: выберите свой размер',
     'Size guide: find your size'),
]

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
                                    SizeChart, SizeChartRow, Slide, Tag,
                                    Variant, default_colour)

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
                              % (copied, settings.MEDIA_ROOT))

        counts = {
            'products': Product.objects.count(),
            'variants': Variant.objects.count(),
            'categories': Category.objects.count(),
            'sizes': Size.objects.count(),
            'carts': Cart.objects.count(),
            'orders': Order.objects.count(),
            'slides': Slide.objects.count(),
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
            # The cards go with the catalogue: they advertise it, and one of
            # them points at a page the catalogue defines. Their files are not
            # lost with them — the delete receiver checks after the commit
            # whether any row still names the file, and by then the new rows
            # do (§17 #220), which is the same path the product photographs
            # have taken since this command existed.
            Slide.objects.all().delete()
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

            for order, (slug, link, uz, ru, en) in enumerate(SLIDES, start=1):
                Slide.objects.create(
                    picture='slides/slide-%s.jpg' % slug,
                    link=link, alt=uz, alt_ru=ru, alt_en=en,
                    is_active=True, sort_order=order,
                )

        self.stdout.write(self.style.SUCCESS(
            'seeded %d products, %d variants, %d sizes, %d slides, 1 category'
            % (Product.objects.count(), Variant.objects.count(),
               Size.objects.count(), Slide.objects.count())))
        self.stdout.write('tags reused: %s' % ', '.join(
            Tag.objects.order_by('slug').values_list('slug', flat=True)))

    # ------------------------------------------------------------------ files
    @staticmethod
    def image_names():
        """Every file the catalogue refers to, relative to MEDIA_ROOT."""
        names = ['products/hero-%d.jpg' % n for n in range(1, 5)]
        names += ['products/%s.jpg' % row[0] for row in CATALOGUE if row[0] != 'rampage']
        names += ['slides/slide-%s.jpg' % row[0] for row in SLIDES]
        return names

    def _place_images(self):
        """Copy any missing photograph out of the tracked folder into media.

        `media/` is gitignored, so on a fresh clone the photographs only exist
        under `data/demo-catalogue/`. Copying rather than symlinking keeps
        this working on Windows without developer mode.
        """
        source = settings.BASE_DIR / 'data' / 'demo-catalogue'
        # `Path(...)` rather than the setting as it stands: the test runner
        # replaces MEDIA_ROOT with a throwaway directory as a plain string
        # (§17 #271), and `str / str` is a TypeError. Nothing had called this
        # command from a test until the slides needed one, so it had never
        # come up.
        media = Path(settings.MEDIA_ROOT)

        copied, missing = 0, []
        for name in self.image_names():
            dest = media / name
            # Per file, not once: the slides live in their own folder, and a
            # fresh clone has neither of them.
            dest.parent.mkdir(parents=True, exist_ok=True)
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
