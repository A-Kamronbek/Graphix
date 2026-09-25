"""Phase 9 — performance, SEO and accessibility.

The three halves of this phase fail in different ways, so they are tested in
different ways:

* **performance** is a promise about bytes and queries. A photograph has to
  arrive as a WebP rendition of the right width, a listing has to cost the same
  number of queries with twenty products as with two, and the numbers that make
  both true have to be on the row rather than read off disk while a page
  renders. Lighthouse measures the result; these keep the machinery honest
  between measurements.
* **SEO** is a promise about markup nobody looks at. A canonical pointing at
  the wrong host, a `noindex` missing from the checkout, or a `Product` node
  with no offer are all invisible on the page and expensive in a search result,
  which is exactly the shape of thing a test is for.
* **accessibility** is a promise to somebody who is not looking at the screen.
  What can be asserted here is the machinery — the control border's own token,
  the live region, the role and the name on a zoomable photograph; the rest is
  a keyboard and a screen reader, which is what the Definition of Done asks
  for.

The backlog items this phase closes (§18 #14, #22, #24, #27, #31, #34) are
tested beside the work they belong to rather than in a file of their own, and
so are two settled questions: a product needs a tag (§19 Q35) and a staff
account is verified from the Django admin (§19 Q34).
"""
import io
import json
import os
import re
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation
from PIL import Image, ImageFilter

from panel import catalogue, reference
from product import images, services
from product.models import (Category, ImageP, PrintMethod, Product, Size,
                            SizeChart, Tag, TagKind, Variant)
from product.models import ReviewImage
from product.signals import build_renditions
from product.templatetags import image_tags

from .test_backlog import TempMedia, jpeg, superuser
from .test_phase4 import make_product
from .test_phase6 import make_user
from .test_phase7 import make_staff
from .test_phase12 import make_order

ROOT = Path(settings.BASE_DIR)
TEMPLATES = ROOT / 'templates'
STATIC = ROOT / 'static'


def at(lang, name, *args, **kwargs):
    """``reverse`` in ``lang``: every page carries its language's prefix."""
    with translation.override(lang):
        return reverse(name, args=args, kwargs=kwargs or None)


def picture(width, height, block=30, blur=3.0):
    """An image that compresses like a photograph rather than like a swatch.

    Random blocks, enlarged and blurred: smooth gradients with detail
    everywhere, which is what a camera produces and what the byte budget is
    about. A flat colour would compress to three kilobytes at any quality and
    the budget checks below would pass without measuring anything; per-pixel
    noise is the opposite mistake, and compresses worse than any photograph
    ever taken. ``block`` and ``blur`` set how much detail there is.
    """
    small = Image.frombytes('RGB', (max(1, width // block), max(1, height // block)),
                            os.urandom(max(1, width // block) * max(1, height // block) * 3))
    return small.resize((width, height), Image.BICUBIC).filter(
        ImageFilter.GaussianBlur(blur))


def shot(width=1200, height=1500, name='shot.jpg', **detail):
    """A real JPEG of a given size, ready to be saved into an ImageField."""
    buf = io.BytesIO()
    picture(width, height, **detail).save(buf, format='JPEG', quality=92)
    return ContentFile(buf.getvalue(), name=name)


def with_photo(product, width=1200, height=1500):
    """Give ``product`` one photograph, with its renditions built."""
    image = ImageP.objects.create(product=product,
                                  picture=shot(width, height), order=0)
    build_renditions(ImageP, image.pk)
    image.refresh_from_db()
    return image


def tagged(name='Tegli', **kwargs):
    """A product with one tag on it — which every product needs (§19 Q35)."""
    product, variant = make_product(name, **kwargs)
    product.tags.add(Tag.objects.create(slug='teg-%d' % product.pk, name='Teg'))
    return product, variant


# ========================================================== 1. the pipeline

class RenditionTests(TempMedia, TestCase):
    """A photograph is stored once and delivered as WebP at several widths."""

    def setUp(self):
        self.product, self.variant = make_product('Rendition', stock=3)

    def test_a_photograph_is_written_at_every_width_below_its_own(self):
        image = with_photo(self.product, 2000, 2500)
        self.assertEqual([w for w, _name in image.sources()], [400, 800, 1600])
        for _width, name in image.sources():
            self.assertTrue(image.picture.storage.exists(name), name)

    def test_a_small_photograph_is_never_upscaled(self):
        """Invented pixels cost bytes and buy nothing."""
        image = with_photo(self.product, 900, 1125)
        self.assertEqual([w for w, _name in image.sources()], [400, 800, 900])

    def test_the_renditions_are_webp_at_the_width_they_claim(self):
        image = with_photo(self.product, 1200, 1500)
        for width, name in image.sources():
            with image.picture.storage.open(name, 'rb') as handle:
                with Image.open(handle) as rendition:
                    self.assertEqual(rendition.format, 'WEBP')
                    self.assertEqual(rendition.size[0], width)

    def test_a_photograph_arrives_inside_the_budget(self):
        """§5: no image the site delivers may exceed 250 KB."""
        image = with_photo(self.product, 2000, 2500)
        biggest = image.sources()[-1][1]
        self.assertLessEqual(image.picture.storage.size(biggest),
                             images.RENDITION_BUDGET)

    def test_the_quality_steps_down_until_the_file_fits(self):
        """The ladder, measured rather than assumed.

        The budget is set from this very image - one byte under what the top
        quality produces - so the encoder has to come down a step, and the
        test says nothing about how big any particular picture happens to be.
        """
        frame = picture(1600, 2000, block=16, blur=2.0)
        best = io.BytesIO()
        frame.save(best, format='WEBP', quality=images.QUALITY_STEPS[0],
                   method=images.WEBP_METHOD)
        budget = len(best.getvalue()) - 1024
        with mock.patch.object(images, 'RENDITION_BUDGET', budget):
            written = images._encode_webp(frame)
        self.assertLessEqual(len(written), budget)

    def test_a_photograph_that_cannot_fit_is_still_written(self):
        """Nothing is refused for being hard to compress; the smallest wins."""
        frame = Image.frombytes('RGB', (1600, 2000), os.urandom(1600 * 2000 * 3))
        with mock.patch.object(images, 'RENDITION_BUDGET', 1024):
            written = images._encode_webp(frame)
        self.assertTrue(written)
        floor = io.BytesIO()
        frame.save(floor, format='WEBP', quality=images.QUALITY_STEPS[-1],
                   method=images.WEBP_METHOD)
        self.assertEqual(len(written), len(floor.getvalue()))

    def test_the_row_records_the_photograph_s_own_size(self):
        """So the markup can hold the space before the file arrives (item 4)."""
        image = with_photo(self.product, 1200, 1500)
        self.assertEqual((image.width, image.height), (1200, 1500))

    def test_the_renditions_are_named_after_the_file_they_came_from(self):
        image = with_photo(self.product)
        self.assertEqual(image.renditions['src'], image.picture.name)
        for _width, name in image.sources():
            self.assertIn('/w/', name)

    def test_a_row_whose_file_changed_is_described_by_nothing(self):
        """Renditions of the previous file must never be served for this one."""
        image = with_photo(self.product)
        image.renditions = dict(image.renditions, src='products/somebody-else.jpg')
        self.assertEqual(image.sources(), [])
        self.assertEqual(image.srcset(), '')

    def test_an_unreadable_file_is_reported_rather_than_raised(self):
        """A photograph that cannot be re-encoded is slow, not broken."""
        image = ImageP.objects.create(product=self.product, picture=jpeg('bad.jpg'),
                                      order=0)
        image.picture.storage.delete(image.picture.name)
        self.assertIsNone(images.build_renditions(image.picture))

    def test_uploading_through_the_panel_builds_them(self):
        """The signal runs on commit, wherever the photograph came from."""
        upload = SimpleUploadedFile('panel.jpg', shot(600, 750).read(),
                                    content_type='image/jpeg')
        with self.captureOnCommitCallbacks(execute=True):
            made = catalogue.add_images(self.product, [upload])
        made[0].refresh_from_db()
        self.assertTrue(made[0].sources())

    def test_saving_a_row_again_does_not_encode_it_twice(self):
        """Dragging a gallery into order saves eight rows and changes no file."""
        image = with_photo(self.product)
        with mock.patch('product.signals.build_renditions') as again:
            with self.captureOnCommitCallbacks(execute=True):
                image.order = 3
                image.save(update_fields=['order'])
        again.assert_not_called()

    def test_deleting_the_row_takes_the_renditions_with_the_original(self):
        image = with_photo(self.product)
        storage = image.picture.storage
        original, derived = image.picture.name, [n for _w, n in image.sources()]
        with self.captureOnCommitCallbacks(execute=True):
            image.delete()
        self.assertFalse(storage.exists(original))
        for name in derived:
            self.assertFalse(storage.exists(name), name)

    def test_a_file_two_rows_share_keeps_its_renditions(self):
        """The demo seed recreates rows over the very same photographs."""
        image = with_photo(self.product)
        twin = ImageP.objects.create(product=self.product,
                                     picture=image.picture.name, order=1)
        storage = image.picture.storage
        derived = [n for _w, n in image.sources()]
        with self.captureOnCommitCallbacks(execute=True):
            image.delete()
        self.assertTrue(storage.exists(twin.picture.name))
        for name in derived:
            self.assertTrue(storage.exists(name), name)

    def test_a_review_photograph_goes_through_the_same_pipeline(self):
        user = make_user('rendition', '+998901400001')
        order = make_order(user, self.variant)
        upload = SimpleUploadedFile('review.jpg', shot(900, 1125).read(),
                                    content_type='image/jpeg')
        with self.captureOnCommitCallbacks(execute=True):
            services.create_review(user, order, self.product, 5, text='Zoʻr',
                                   photos=[upload])
        picture = ReviewImage.objects.get()
        self.assertTrue(picture.sources())

    def test_a_size_chart_is_measured_and_left_alone(self):
        """A chart is a drawing of a table; three widths of it buy nothing."""
        with self.captureOnCommitCallbacks(execute=True):
            chart = SizeChart.objects.create(name='Oversize', image=shot(800, 600))
        chart.refresh_from_db()
        self.assertEqual((chart.width, chart.height), (800, 600))
        self.assertEqual(chart.sources(), [])


class BackfillCommandTests(TempMedia, TestCase):
    """Everything uploaded before Phase 9 is re-encoded by one command."""

    def setUp(self):
        self.product, _ = make_product('Backfill', stock=1)

    def test_it_builds_what_is_missing(self):
        image = ImageP.objects.create(product=self.product, picture=shot(600, 750),
                                      order=0)
        self.assertEqual(image.renditions, {})
        call_command('build_renditions', verbosity=0)
        image.refresh_from_db()
        self.assertEqual([w for w, _n in image.sources()], [400, 600])

    def test_running_it_twice_changes_nothing(self):
        image = ImageP.objects.create(product=self.product, picture=shot(600, 750),
                                      order=0)
        call_command('build_renditions', verbosity=0)
        image.refresh_from_db()
        before = image.renditions
        call_command('build_renditions', verbosity=0)
        image.refresh_from_db()
        self.assertEqual(image.renditions, before)


class ImageTagTests(TempMedia, TestCase):
    """The tag that renders a photograph, including when there is not one."""

    def setUp(self):
        self.product, _ = make_product('Teg', stock=1)

    def test_it_renders_the_source_set_and_the_size(self):
        image = with_photo(self.product, 1200, 1500)
        html = image_tags.photo_attrs(image, 'card')
        self.assertIn('srcset="', html)
        self.assertIn('400w', html)
        self.assertIn('sizes="%s"' % image_tags.SIZES['card'], html)
        self.assertIn('width="1200"', html)
        self.assertIn('height="1500"', html)

    def test_a_missing_photograph_renders_the_placeholder_at_its_own_size(self):
        html = image_tags.photo_attrs(None, 'card')
        self.assertIn('no-image', html)
        self.assertIn('width="%d"' % image_tags.FALLBACK_WIDTH, html)
        self.assertNotIn('srcset="', html)

    def test_a_row_with_no_renditions_still_renders_its_file(self):
        """Before the backfill has run, every page still shows its pictures."""
        image = ImageP.objects.create(product=self.product, picture=jpeg(), order=0)
        html = image_tags.photo_attrs(image, 'card')
        self.assertIn(image.picture.url, html)
        # `srcset=`, not `srcset`: the fallback names the attribute it clears.
        self.assertNotIn('srcset="', html)

    def test_the_fallback_drops_the_source_set_with_the_source(self):
        """A browser with `srcset` ignores `src`, so setting that alone shows nothing.

        This read the inline `onerror=` until Phase 10 moved the behaviour into
        `main.js` for the CSP (§17 #269). The rule is unchanged and so is the
        test's point; only the place that clears `srcset` has moved, and
        `core.test_phase10.PhotoFallbackTests` asserts it is still done.
        """
        image = with_photo(self.product)
        html = image_tags.photo_attrs(image, 'card')
        self.assertIn('data-fallback="', html)
        self.assertNotIn('onerror', html)

    def test_the_viewer_is_offered_the_full_width_file(self):
        image = with_photo(self.product, 2000, 2500)
        self.assertEqual(image_tags.photo_zoom(image), image.zoom_url())
        self.assertIn('-1600.webp', image.zoom_url())

    def test_the_placeholder_is_the_size_the_tag_claims(self):
        """A wrong intrinsic size on the fallback is layout shift of its own."""
        with Image.open(STATIC / 'img' / 'no-image.jpg') as placeholder:
            self.assertEqual(placeholder.size,
                             (image_tags.FALLBACK_WIDTH, image_tags.FALLBACK_HEIGHT))


class MarkupTests(TempMedia, TestCase):
    """What the pages render once a product has a photograph."""

    def setUp(self):
        self.product, self.variant = make_product('Koʻrinish', stock=4)
        self.image = with_photo(self.product, 1200, 1500)

    def test_the_product_page_asks_for_its_photograph_first(self):
        html = self.client.get(at('uz', 'item', slug=self.product.slug)).content.decode()
        self.assertIn('fetchpriority="high"', html)
        self.assertIn('srcset=', html)
        self.assertIn('data-zoom-src=', html)

    def test_one_image_asks_for_priority_and_the_rest_do_not(self):
        for n in range(6):
            other, _ = make_product('Karta %d' % n, stock=2)
            with_photo(other, 600, 750)
        html = self.client.get(at('uz', 'shop')).content.decode()
        self.assertEqual(html.count('fetchpriority="high"'), 1)
        self.assertIn('loading="lazy"', html)

    def test_every_photograph_on_the_page_states_its_size(self):
        """Nothing may reflow when a picture lands (item 4)."""
        html = self.client.get(at('uz', 'item', slug=self.product.slug)).content.decode()
        for tag in re.findall(r'<img [^>]+>', html):
            with self.subTest(tag=tag[:90]):
                self.assertIn('width="', tag)
                self.assertIn('height="', tag)

    def test_the_cart_shows_the_photograph_at_a_thumbnail_s_width(self):
        self.client.force_login(make_user('savatchi', '+998901400002'))
        self.client.post(at('uz', 'cart_add', self.product.pk),
                         {'size': self.variant.size_id, 'quantity': 1})
        html = self.client.get(at('uz', 'cart')).content.decode()
        self.assertIn('sizes="%s"' % image_tags.SIZES['thumb'], html)


# ============================================================= 2. the queries

class QueryCountTests(TempMedia, TestCase):
    """A listing must cost the same whether it lists two products or twenty.

    Written as a comparison rather than as a number: the exact count changes
    with any honest refactor and a test that pins it becomes a test somebody
    edits without reading. What must never change is the *shape* — a query per
    product is what turns a catalogue of eighty into a page that times out.
    """

    def setUp(self):
        self.user = make_user('sanoq', '+998901410001')

    def stock(self, count, prefix='Mahsulot'):
        made = []
        for n in range(count):
            product, variant = make_product('%s %d' % (prefix, n), stock=3)
            with_photo(product, 400, 500)
            made.append((product, variant))
        return made

    def count(self, url):
        # The footer's delivery tiers are cached for a minute (§17 #111), so
        # the second render of a page can legitimately cost one query less than
        # the first. Cleared here, because this measures the page's shape and
        # not the cache's timing.
        cache.clear()
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(queries)

    def assertFlat(self, url, grow):
        """The page costs the same with more rows on it."""
        small = self.count(url)
        grow()
        self.assertEqual(self.count(url), small)

    def test_the_shop_does_not_grow_a_query_per_product(self):
        self.stock(2)
        self.assertFlat(at('uz', 'shop'), lambda: self.stock(6, 'Yana'))

    def test_the_home_page_does_not_grow_a_query_per_product(self):
        self.stock(2)
        self.assertFlat(at('uz', 'home'), lambda: self.stock(6, 'Yana'))

    def test_the_saved_page_does_not_grow_a_query_per_product(self):
        from product.models import ProductLike
        made = self.stock(2)
        self.client.force_login(self.user)
        for product, _v in made:
            ProductLike.objects.create(user=self.user, product=product)

        def like_more():
            for product, _v in self.stock(6, 'Yana'):
                ProductLike.objects.create(user=self.user, product=product)

        self.assertFlat(at('uz', 'liked'), like_more)

    def test_the_cart_does_not_grow_a_query_per_line(self):
        self.client.force_login(self.user)
        made = self.stock(6)

        def add(pair):
            product, variant = pair
            self.client.post(at('uz', 'cart_add', product.pk),
                             {'size': variant.size_id, 'quantity': 1})

        add(made[0])
        add(made[1])
        self.assertFlat(at('uz', 'cart'), lambda: [add(p) for p in made[2:]])

    def test_an_order_page_does_not_grow_a_query_per_line(self):
        """It reads a variant's size for every line, which was one query each."""
        from cart.models import Cart, CartItem
        from payment.models import Order
        self.client.force_login(self.user)
        made = self.stock(6)
        cart = Cart.objects.create(user=self.user, status=False)
        for product, variant in made[:2]:
            CartItem.objects.create(cart=cart, variant=variant, quantity=1,
                                    price_stat=variant.price)
        order = Order.objects.create(user=self.user, cart=cart, phone=self.user.phone,
                                     address='Amir Temur 1', total_price=1,
                                     status='paid')

        def add_lines():
            for product, variant in made[2:]:
                CartItem.objects.create(cart=cart, variant=variant, quantity=1,
                                        price_stat=variant.price)

        self.assertFlat(at('uz', 'order_detail', order.pk), add_lines)

    def test_a_product_page_does_not_grow_a_query_per_review(self):
        product, variant = make_product('Sharhli', stock=9)
        with_photo(product, 600, 750)

        def review(n):
            user = make_user('sharh%d' % n, '+99890142%04d' % n)
            order = make_order(user, variant)
            written = services.create_review(user, order, product, 5, text='Yaxshi')
            from product.models import Review
            services.moderate(Review.objects.filter(pk=written.pk),
                              Review.Status.APPROVED)

        review(1)
        url = at('uz', 'item', slug=product.slug)
        self.assertFlat(url, lambda: [review(n) for n in range(2, 5)])

    def test_the_panel_s_lists_do_not_grow_a_query_per_row(self):
        self.client.force_login(make_staff('panelchi', '+998901410009'))
        self.stock(2)
        self.assertFlat(at('uz', 'panel_products'), lambda: self.stock(6, 'Yana'))


class IndexTests(TestCase):
    """Everything filtered or ordered has an index behind it (item 8)."""

    def test_the_columns_a_listing_orders_by_are_indexed(self):
        from payment.models import Order
        self.assertTrue(Product._meta.get_field('created_at').db_index)
        self.assertTrue(Product._meta.get_field('likes_count').db_index)
        self.assertTrue(Product._meta.get_field('rating_avg').db_index)
        self.assertTrue(Order._meta.get_field('created_at').db_index)
        self.assertTrue(Order._meta.get_field('status').db_index)
        self.assertTrue(Order._meta.get_field('postal_index').db_index)

    def test_the_product_page_s_review_query_has_an_index(self):
        from product.models import Review
        wanted = ['product', 'status', '-created_at']
        self.assertTrue(any(index.fields == wanted for index in Review._meta.indexes),
                        'the approved-reviews-for-a-product query has no index')

    def test_a_test_run_does_not_use_the_hashed_static_storage(self):
        """The manifest is written by collectstatic; without one, every page 500s.

        The runner turns DEBUG off, so this setting is the only thing standing
        between a test run and a production one here.
        """
        self.assertTrue(settings.TESTING)
        self.assertEqual(settings.STORAGES['staticfiles']['BACKEND'],
                         'django.contrib.staticfiles.storage.StaticFilesStorage')


# ================================================================== 3. SEO

class CanonicalTests(TestCase):
    """One address per page, and one set of alternates (§9 Phase 9 item 12)."""

    def setUp(self):
        self.product, _ = tagged('Kanonik', stock=2)

    def canonical(self, html):
        found = re.search(r'<link rel="canonical" href="([^"]+)">', html)
        return found and found.group(1)

    def test_every_public_page_names_itself(self):
        for lang, name in (('uz', 'home'), ('ru', 'shop'), ('en', 'about')):
            with self.subTest(lang=lang, page=name):
                html = self.client.get(at(lang, name)).content.decode()
                self.assertEqual(self.canonical(html),
                                 settings.SITE_URL.rstrip('/') + at(lang, name))

    def test_a_filtered_catalogue_is_the_catalogue(self):
        """Forty ways to sort one shop are not forty pages."""
        html = self.client.get(at('uz', 'shop'), {'sort': 'popular'}).content.decode()
        self.assertEqual(self.canonical(html),
                         settings.SITE_URL.rstrip('/') + at('uz', 'shop'))

    def test_page_two_is_a_page_of_its_own(self):
        html = self.client.get(at('uz', 'shop'), {'page': '2'}).content.decode()
        self.assertTrue(self.canonical(html).endswith('/shop/?page=2'))

    def test_the_alternates_carry_the_path_and_not_the_query(self):
        html = self.client.get(at('ru', 'shop'), {'sort': 'popular'}).content.decode()
        for code in ('uz', 'ru', 'en'):
            with self.subTest(code=code):
                self.assertIn('hreflang="%s" href="%s%s"'
                              % (code, settings.SITE_URL.rstrip('/'), at(code, 'shop')),
                              html)
        self.assertNotIn('sort=popular', html.split('</head>')[0])

    def test_x_default_is_this_page_in_uzbek_not_the_front_door(self):
        html = self.client.get(at('en', 'about')).content.decode()
        self.assertIn('hreflang="x-default" href="%s%s"'
                      % (settings.SITE_URL.rstrip('/'), at('uz', 'about')), html)

    def test_the_share_card_points_at_the_canonical_address(self):
        html = self.client.get(at('uz', 'item', slug=self.product.slug)).content.decode()
        self.assertIn('<meta property="og:url" content="%s%s">'
                      % (settings.SITE_URL.rstrip('/'),
                         at('uz', 'item', slug=self.product.slug)), html)

    def test_the_error_pages_render_without_a_canonical_rather_than_break(self):
        """500.html is rendered with no context at all (§17 #66)."""
        from django.template.loader import render_to_string
        html = render_to_string('500.html')
        self.assertNotIn('<link rel="canonical"', html)
        self.assertIn('noindex', html)


class RobotsRuleTests(TestCase):
    """What may be indexed, and what may not (§9 Phase 9 item 12)."""

    def setUp(self):
        self.product, self.variant = tagged('Indeks', stock=3)
        self.user = make_user('robot', '+998901420001')

    def noindexed(self, url):
        html = self.client.get(url, follow=True).content.decode()
        return 'name="robots" content="noindex' in html

    def test_the_pages_worth_finding_are_indexable(self):
        for name in ('home', 'shop', 'about', 'contact', 'delivery', 'terms', 'privacy'):
            with self.subTest(page=name):
                self.assertFalse(self.noindexed(at('uz', name)))
        self.assertFalse(self.noindexed(at('uz', 'item', slug=self.product.slug)))

    def test_a_search_result_is_not_a_page_of_the_site(self):
        self.assertTrue(self.noindexed(at('uz', 'search') + '?q=indeks'))

    def test_the_private_half_of_the_site_says_noindex(self):
        self.client.force_login(self.user)
        self.client.post(at('uz', 'cart_add', self.product.pk),
                         {'size': self.variant.size_id, 'quantity': 1})
        for url in (at('uz', 'cart'), at('uz', 'checkout'), at('uz', 'account'),
                    at('uz', 'account_orders'), at('uz', 'liked')):
            with self.subTest(url=url):
                self.assertTrue(self.noindexed(url))

    def test_the_pages_a_signed_out_visitor_sees_say_noindex(self):
        for name in ('login', 'signup', 'password_reset_request'):
            with self.subTest(page=name):
                self.assertTrue(self.noindexed(at('uz', name)))

    def test_robots_txt_keeps_crawlers_out_of_the_same_places(self):
        body = self.client.get('/robots.txt').content.decode()
        for code in ('uz', 'ru', 'en'):
            for area in ('boshqaruv', 'saqlanganlar', 'qidiruv', 'login', 'signup'):
                with self.subTest(code=code, area=area):
                    self.assertIn('Disallow: /%s/%s/' % (code, area), body)


class StructuredDataTests(TempMedia, TestCase):
    """One `@graph` per page, and everything Google asks of it (item 11)."""

    def setUp(self):
        self.category = Category.objects.create(name='Futbolkalar', slug='futbolkalar')
        self.product, self.variant = tagged('Tuzilma', stock=4)
        self.product.category = self.category
        self.product.description = 'Qalin trikotaj, DTF bosma.'
        self.product.save()
        with_photo(self.product, 800, 1000)

    def graph(self, url):
        html = self.client.get(url).content.decode()
        self.assertEqual(html.count('application/ld+json'), 1,
                         'two blocks is the same thing said twice')
        found = re.search(
            # `[^>]*` because the block carries a CSP nonce since Phase 10.
            # Pinning the opening tag exactly read a perfectly good page as
            # having no structured data at all (§17 #269).
            r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.S)
        self.assertIsNotNone(found, 'no structured data on %s' % url)
        return json.loads(found.group(1))['@graph']

    def node(self, url, kind):
        for node in self.graph(url):
            if node.get('@type') == kind:
                return node
        self.fail('no %s node on %s' % (kind, url))

    def test_the_product_carries_an_offer(self):
        """§18 #22: without one, Search Console warns on every product page."""
        offer = self.node(at('uz', 'item', slug=self.product.slug), 'Product')['offers']
        self.assertEqual(offer['@type'], 'Offer')
        self.assertEqual(offer['price'], '150000')
        self.assertEqual(offer['priceCurrency'], 'UZS')
        self.assertEqual(offer['availability'], 'https://schema.org/InStock')

    def test_several_prices_are_a_range_and_not_a_guess(self):
        Variant.objects.create(product=self.product,
                               size=Size.objects.create(size='XL-%d' % self.product.pk),
                               colour=self.variant.colour, price=190000,
                               available=True, stock=2)
        offer = self.node(at('uz', 'item', slug=self.product.slug), 'Product')['offers']
        self.assertEqual(offer['@type'], 'AggregateOffer')
        self.assertEqual((offer['lowPrice'], offer['highPrice']), ('150000', '190000'))

    def test_a_sold_out_design_says_so(self):
        """Markup that disagrees with the page is what earns a manual action."""
        Variant.objects.filter(product=self.product).update(stock=0)
        offer = self.node(at('uz', 'item', slug=self.product.slug), 'Product')['offers']
        self.assertEqual(offer['availability'], 'https://schema.org/OutOfStock')

    def test_the_product_node_names_the_brand_and_shows_the_photograph(self):
        node = self.node(at('uz', 'item', slug=self.product.slug), 'Product')
        self.assertEqual(node['brand']['name'], 'GRAPHIX')
        self.assertEqual(node['sku'], self.product.slug)
        self.assertTrue(node['image'])
        for url in node['image']:
            self.assertTrue(url.startswith('http'), url)

    def test_the_trail_to_the_product_is_described(self):
        trail = self.node(at('uz', 'item', slug=self.product.slug), 'BreadcrumbList')
        names = [row['name'] for row in trail['itemListElement']]
        self.assertEqual(names[0], 'Bosh sahifa')
        self.assertIn('Futbolkalar', names)
        self.assertEqual(names[-1], self.product.name)
        # The page itself is the last crumb and links nowhere.
        self.assertNotIn('item', trail['itemListElement'][-1])

    def test_the_home_page_describes_the_shop_and_its_search(self):
        graph = {node['@type']: node for node in self.graph(at('uz', 'home'))}
        self.assertEqual(graph['Organization']['name'], 'GRAPHIX')
        self.assertIn('t.me', graph['Organization']['sameAs'][0])
        action = graph['WebSite']['potentialAction']
        self.assertIn('{search_term_string}', action['target']['urlTemplate'])

    def test_the_shop_carries_its_own_trail_and_no_product_node(self):
        graph = self.graph(at('uz', 'shop'))
        kinds = {node['@type'] for node in graph}
        self.assertEqual(kinds, {'BreadcrumbList'})

    def test_a_search_page_says_nothing_to_a_search_engine(self):
        html = self.client.get(at('uz', 'search') + '?q=tuzilma').content.decode()
        self.assertNotIn('application/ld+json', html)


class MetaCopyTests(TestCase):
    """Every page describes itself, in its own language (item 9)."""

    def description(self, url):
        html = self.client.get(url).content.decode()
        return re.search(r'<meta name="description" content="([^"]*)"', html).group(1)

    def test_the_pages_do_not_share_one_description(self):
        seen = {name: self.description(at('uz', name))
                for name in ('home', 'shop', 'about', 'contact', 'terms', 'privacy')}
        self.assertEqual(len(set(seen.values())), len(seen), seen)

    def test_a_product_describes_itself_with_its_own_copy(self):
        product, _ = tagged('Tavsifli', stock=1)
        product.description = 'Bu dizayn haqida bir-ikki gap.'
        product.save()
        self.assertIn('Bu dizayn haqida',
                      self.description(at('uz', 'item', slug=product.slug)))

    def test_a_product_with_no_copy_still_says_something(self):
        product, _ = tagged('Tavsifsiz', stock=1)
        self.assertIn('GRAPHIX', self.description(at('uz', 'item', slug=product.slug)))

    def test_page_two_says_so_in_its_title(self):
        """Twenty-one designs, because an out-of-range page is page one."""
        for n in range(21):
            tagged('Sahifa %d' % n, stock=1)
        html = self.client.get(at('uz', 'shop'), {'page': '2'}).content.decode()
        title = re.search(r'<title>(.*?)</title>', html, re.S).group(1)
        self.assertIn('2', title)


class SitemapTests(TestCase):
    """What the sitemap advertises has to exist (item 12)."""

    def test_the_size_guide_is_listed_when_charts_alone_exist(self):
        """The page renders on charts; the sitemap asked only about the image."""
        from core import sitemaps
        from core.context_processors import has_size_guide
        SizeChart.objects.create(name='Oversize')
        self.assertTrue(has_size_guide())
        self.assertIn('size_guide', sitemaps.StaticViewSitemap().items())

    def test_the_old_item_url_still_leads_to_the_product(self):
        """Item 13: links to /item/<pk>/ predate the slug URLs."""
        product, _ = tagged('Eski havola', stock=1)
        # Prefixed: every URL carries its language since §17 #121, and the
        # unprefixed one answers with a redirect into the prefixed tree first.
        response = self.client.get('/uz/item/%d/' % product.pk)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], at('uz', 'item', slug=product.slug))


# ====================================================== 4. accessibility

class ControlBorderTests(TestCase):
    """A control's boundary is 3:1 against the page, because often it is the
    only thing saying the control is there (§17 #188, §19 Q22)."""

    TOKENS = (STATIC / 'css' / 'tokens.css').read_text(encoding='utf-8')
    COMPONENTS = (STATIC / 'css' / 'components.css').read_text(encoding='utf-8')

    def test_the_token_exists_and_is_the_agreed_colour(self):
        self.assertIn('--c-line-control:  #756853;', self.TOKENS)

    def test_every_control_uses_it(self):
        for rule in ('.input, .textarea, .select', '.check input', '.stepper',
                     '.otp input', '.sizes__btn', '.chips button'):
            with self.subTest(rule=rule):
                block = self.COMPONENTS.split(rule, 1)[1].split('}', 1)[0]
                self.assertIn('--c-line-control', block,
                              '%s still draws itself with a decorative line' % rule)

    def test_the_contrast_of_the_two_line_colours_is_what_was_decided(self):
        """3:1 for a control, and the old value kept for panel edges."""
        def luminance(hex_colour):
            def channel(value):
                v = int(value, 16) / 255
                return v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4
            r, g, b = (hex_colour[i:i + 2] for i in (1, 3, 5))
            return .2126 * channel(r) + .7152 * channel(g) + .0722 * channel(b)

        def ratio(one, two):
            a, b = sorted((luminance(one), luminance(two)), reverse=True)
            return (a + .05) / (b + .05)

        self.assertGreaterEqual(ratio('#756853', '#100E0C'), 3.0)
        self.assertLess(ratio('#453D31', '#100E0C'), 3.0)


class ZoomableImageTests(TempMedia, TestCase):
    """A photograph that opens full screen is a control (§18 #24)."""

    VIEWER = (TEMPLATES / 'partials' / '_viewer.html').read_text(encoding='utf-8')
    SCRIPT = (STATIC / 'js' / 'viewer.js').read_text(encoding='utf-8')

    def test_the_names_it_gives_are_translated_copy(self):
        """A sentence typed into a .js file cannot be translated (§17 #80)."""
        self.assertIn('data-zoom-label="{% trans', self.VIEWER)
        self.assertIn('data-zoom-suffix="{% trans', self.VIEWER)
        self.assertIn("getAttribute('data-zoom-label')", self.SCRIPT)

    def test_it_takes_the_keyboard_and_says_what_it_is(self):
        self.assertIn("setAttribute('role', 'button')", self.SCRIPT)
        self.assertIn("setAttribute('tabindex', '0')", self.SCRIPT)
        self.assertIn("aria-label", self.SCRIPT)
        self.assertIn("e.key !== 'Enter'", self.SCRIPT)

    def test_the_cursor_is_a_design_value_in_the_stylesheet(self):
        """It was written as an inline style by the script (§4)."""
        self.assertNotIn("style.cursor", self.SCRIPT)
        self.assertIn('.zoomable { cursor: zoom-in; }',
                      (STATIC / 'css' / 'components.css').read_text(encoding='utf-8'))

    def test_a_review_photograph_carries_what_the_viewer_needs(self):
        product, variant = tagged('Sharhli rasm', stock=3)
        user = make_user('zoom', '+998901430001')
        order = make_order(user, variant)
        upload = SimpleUploadedFile('review.jpg', shot(600, 750).read(),
                                    content_type='image/jpeg')
        from product.models import Review
        with self.captureOnCommitCallbacks(execute=True):
            review = services.create_review(user, order, product, 5, text='Ajoyib',
                                            photos=[upload])
        services.moderate(Review.objects.filter(pk=review.pk), Review.Status.APPROVED)
        html = self.client.get(at('uz', 'item', slug=product.slug)).content.decode()
        self.assertIn('data-zoom', html)
        self.assertIn('data-zoom-src=', html)


class AnnouncementTests(TestCase):
    """What the page does on its own has to reach a screen reader (item 18)."""

    BASE = (TEMPLATES / 'base.html').read_text(encoding='utf-8')
    SCRIPT = (STATIC / 'js' / 'main.js').read_text(encoding='utf-8')

    def test_the_shell_renders_a_polite_live_region(self):
        self.assertIn('data-announce', self.BASE)
        self.assertIn('aria-live="polite"', self.BASE)

    def test_the_heart_says_what_it_did(self):
        self.assertIn('announce(data.liked', self.SCRIPT)
        product, _ = tagged('Yurak', stock=1)
        html = self.client.get(at('uz', 'item', slug=product.slug)).content.decode()
        self.assertIn('data-announce-on=', html)
        self.assertIn('data-announce-off=', html)

    def test_the_cart_count_is_read_out_rather_than_hidden_by_a_label(self):
        """An aria-label replaces everything inside the link, the number too."""
        user = make_user('sanoqchi', '+998901440001')
        product, variant = tagged('Sanoq', stock=3)
        self.client.force_login(user)
        self.client.post(at('uz', 'cart_add', product.pk),
                         {'size': variant.size_id, 'quantity': 2})
        html = self.client.get(at('uz', 'shop')).content.decode()
        self.assertIn('aria-label="Savat (2)"', html)


class MeasuredFindingsTests(TestCase):
    """The two defects the production-shaped run found, as tests.

    Both were invisible to a reader and to every earlier sweep: a menu that is
    off the screen is still in the tab order, and a button whose name leaves
    out the number printed inside it reads as a button with no number.
    """

    DRAWER = (TEMPLATES / 'partials' / '_drawer.html').read_text(encoding='utf-8')
    SCRIPT = (STATIC / 'js' / 'main.js').read_text(encoding='utf-8')

    def test_a_closed_drawer_is_out_of_the_tab_order(self):
        self.assertIn('inert', self.DRAWER)
        self.assertIn("toggleAttribute('inert', !open)", self.SCRIPT)

    def test_the_heart_says_how_many(self):
        product, _ = tagged('Yurakli', stock=2)
        Product.objects.filter(pk=product.pk).update(likes_count=3)
        html = self.client.get(at('uz', 'item', slug=product.slug)).content.decode()
        self.assertIn('aria-label="Saqlash (3)"', html)
        html = self.client.get(at('uz', 'shop')).content.decode()
        self.assertIn('aria-label="Saqlash (3)"', html)

    def test_a_design_nobody_has_saved_says_nothing_about_a_count(self):
        product, _ = tagged('Yurakssiz', stock=2)
        html = self.client.get(at('uz', 'item', slug=product.slug)).content.decode()
        self.assertIn('aria-label="Saqlash"', html)

    def test_the_script_keeps_the_number_in_the_name(self):
        self.assertIn("label(pressed, countEl", self.SCRIPT)


class PanelRefusalTests(TestCase):
    """The panel says a refusal on the page, never in an alert (§18 #27)."""

    SCRIPT = (STATIC / 'js' / 'panel.js').read_text(encoding='utf-8')

    def test_nothing_is_said_with_window_alert(self):
        self.assertNotIn('window.alert(', self.SCRIPT)

    def test_it_is_said_in_a_live_region_the_shell_renders(self):
        self.assertIn('TELL(', self.SCRIPT)
        shell = (TEMPLATES / 'boshqaruv' / 'base.html').read_text(encoding='utf-8')
        self.assertIn('data-toasts', shell)
        self.assertIn('aria-live="polite"', shell)

    def test_the_sentence_still_comes_from_gettext(self):
        """`SAY` reads the strings the shell renders through {% trans %}."""
        self.assertIn("TELL(data.error || SAY('failed'))", self.SCRIPT)


# ================================================== 5. the map, loaded late

class LazyMapTests(TestCase):
    """Google is not told about a customer who never opens a map (§18 #34)."""

    def setUp(self):
        self.user = make_user('xarita', '+998901450001')
        product, variant = tagged('Xaritali', stock=3)
        self.client.force_login(self.user)
        self.client.post(at('uz', 'cart_add', product.pk),
                         {'size': variant.size_id, 'quantity': 1})

    def checkout(self, key='test-key'):
        with self.settings(GOOGLE_MAPS_API_KEY=key):
            return self.client.get(at('uz', 'checkout')).content.decode()

    def test_the_page_carries_the_address_but_loads_nothing(self):
        html = self.checkout()
        self.assertIn('data-map-src="https://maps.googleapis.com', html)
        self.assertNotIn('<script defer\n    src="https://maps.googleapis.com', html)
        self.assertNotIn('<script src="https://maps.googleapis.com', html)

    def test_the_address_still_carries_the_language_and_the_region(self):
        html = self.checkout()
        self.assertIn('language=uz', html)
        self.assertIn('region=UZ', html)
        self.assertIn('callback=GXMapReady', html)

    def test_without_a_key_there_is_no_map_and_no_address(self):
        html = self.checkout(key='')
        self.assertNotIn('maps.googleapis.com', html)
        self.assertNotIn('data-map-canvas', html)

    def test_the_toggle_is_offered_from_the_page_rather_than_after_a_fetch(self):
        script = (STATIC / 'js' / 'checkout.js').read_text(encoding='utf-8')
        self.assertIn('mapBlock.dataset.mapSrc', script)
        self.assertIn('GX.map.load(', script)
        self.assertIn('data-map-error', script)

    def test_the_provider_is_fetched_once_and_gives_up_out_loud(self):
        script = (STATIC / 'js' / 'map.js').read_text(encoding='utf-8')
        self.assertIn('load: function (src, done)', script)
        self.assertIn('giveUp', script)

    def test_the_policy_describes_the_narrower_transfer(self):
        """The privacy policy said the script loads with the page. It does not."""
        for lang, phrase in (('uz', 'Xaritadan'), ('ru', 'С карты'),
                             ('en', 'From the map')):
            with self.subTest(lang=lang):
                html = self.client.get(at(lang, 'privacy')).content.decode()
                self.assertIn(phrase, html)


# ============================== 6. Settled questions: Q35, #31 and Q34

class TagRequiredTests(TestCase):
    """A product needs at least one tag (§19 Q35, §17 #228).

    Tags are what the shop's filters and the Phase 13 recommender read, and a
    product with none is invisible to both — so the form refuses rather than
    saving something nothing can find.
    """

    def setUp(self):
        self.staff = make_staff('teglovchi', '+998901460001')
        self.client.force_login(self.staff)
        # A slug of its own: the catalogue is seeded with eight tags and
        # `anime` is one of them (§17 #71).
        self.tag = Tag.objects.create(slug='p9-anime', name='Anime')
        self.size = Size.objects.first() or Size.objects.create(size='M')

    def body(self, **extra):
        body = {'name': 'Yangi dizayn', 'is_active': 'on',
                'price_%s' % self.size.pk: '150000'}
        body.update(extra)
        return body

    def test_a_product_with_no_tag_is_refused(self):
        response = self.client.post(reverse('panel_product_new'), self.body())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(name='Yangi dizayn').exists())

    def test_the_refusal_says_what_is_missing(self):
        response = self.client.post(reverse('panel_product_new'), self.body())
        self.assertContains(response, 'teg')

    def test_nothing_at_all_is_written(self):
        """The tags are read before the row is saved, not after."""
        before = Product.objects.count()
        self.client.post(reverse('panel_product_new'), self.body())
        self.assertEqual(Product.objects.count(), before)

    def test_one_tag_is_enough(self):
        response = self.client.post(reverse('panel_product_new'),
                                    self.body(tags=[self.tag.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Product.objects.get(name='Yangi dizayn').tags.count(), 1)

    def test_what_was_typed_comes_back_with_the_refusal(self):
        """§17 #133: a refusal must not empty a form somebody just filled."""
        response = self.client.post(reverse('panel_product_new'),
                                    self.body(name_ru='Новый дизайн'))
        self.assertContains(response, 'Новый дизайн')

    def test_the_form_says_so_before_it_is_submitted(self):
        page = self.client.get(reverse('panel_product_new')).content.decode()
        self.assertIn('Kamida bittasini tanlang', page)

    def test_the_admin_asks_for_one_too(self):
        self.assertFalse(Product._meta.get_field('tags').blank)


class DuplicateNameTests(TestCase):
    """Two rows in one list may not share a name (§18 #31, §17 #229)."""

    def setUp(self):
        self.staff = superuser('nomlar', '+998901470001')
        self.client.force_login(self.staff)
        self.kind = TagKind.objects.create(slug='p9-uslub', name='Uslub')
        self.other = TagKind.objects.create(slug='p9-mavzu', name='Mavzu')
        self.tag = Tag.objects.create(slug='p9-anime', name='Anime', kind=self.kind)

    def post_tag(self, name, kind=None):
        return self.client.post(reverse('panel_tag_new'),
                                {'name': name, 'kind': (kind or self.kind).pk},
                                follow=True)

    def test_the_same_name_in_the_same_list_is_refused(self):
        response = self.post_tag('Anime')
        self.assertEqual(Tag.objects.filter(kind=self.kind).count(), 1)
        self.assertContains(response, 'allaqachon bor')

    def test_case_does_not_make_it_a_different_name(self):
        """"anime" and "Anime" are the same chip to a shopper."""
        self.post_tag('anime')
        self.assertEqual(Tag.objects.filter(kind=self.kind).count(), 1)

    def test_the_same_name_under_another_axis_is_fine(self):
        """A colour called Qora and a collection called Qora are two things."""
        # Counted inside the two axes this test made: the catalogue is seeded
        # with eight tags of its own, and one of them is called Anime.
        self.post_tag('Anime', kind=self.other)
        self.assertEqual(
            Tag.objects.filter(name__iexact='Anime',
                               kind__in=[self.kind, self.other]).count(), 2)

    def test_a_rename_cannot_make_a_twin(self):
        second = Tag.objects.create(slug='p9-vintage', name='Vintage', kind=self.kind)
        with self.assertRaises(Exception):
            reference.set_field('tag', second.pk, 'name', 'Anime')
        second.refresh_from_db()
        self.assertEqual(second.name, 'Vintage')

    def test_a_row_may_keep_its_own_name(self):
        """Editing another field must not trip over the row's own name."""
        reference.set_field('tag', self.tag.pk, 'name', 'Anime')
        self.tag.refresh_from_db()
        self.assertEqual(self.tag.name, 'Anime')

    def test_moving_a_tag_to_an_axis_that_has_the_name_is_refused(self):
        twin = Tag.objects.create(slug='p9-anime-2', name='Anime', kind=self.other)
        with self.assertRaises(Exception):
            reference.set_field('tag', twin.pk, 'kind', self.kind.pk)

    def test_the_other_lists_are_guarded_too(self):
        # A name the seed does not already use: DTF and the rest are rows the
        # catalogue ships with.
        PrintMethod.objects.create(slug='p9-usul', name='Sinov usuli')
        response = self.client.post(reverse('panel_lookup_new', kwargs={'kind': 'method'}),
                                    {'name': 'sinov usuli'}, follow=True)
        self.assertEqual(
            PrintMethod.objects.filter(name__iexact='sinov usuli').count(), 1)
        self.assertContains(response, 'allaqachon bor')


class StaffVerificationTests(TestCase):
    """The owner's own account is verified from the Django admin (§19 Q34).

    `createsuperuser` leaves `phone_verified` false, and the phone wall sends
    an unverified account to the OTP screen — but it exempts `/admin/`, and the
    admin can edit the flag. So the answer to Q34 is a deploy step rather than
    a code change: sign in at /admin/, tick the box, open the panel. This is
    that path, as a test, so a later change to either half cannot break it
    quietly.
    """

    def setUp(self):
        self.owner = superuser('egasi', '+998901480001')
        self.owner.phone_verified = False
        self.owner.save(update_fields=['phone_verified'])
        self.client.force_login(self.owner)

    def test_the_admin_is_reachable_while_the_phone_is_unverified(self):
        self.assertEqual(self.client.get('/admin/').status_code, 200)

    def test_the_storefront_is_not(self):
        response = self.client.get(at('uz', 'shop'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('verify-phone', response['Location'])

    def test_the_panel_is_not_either(self):
        response = self.client.get(at('uz', 'panel_orders'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('verify-phone', response['Location'])

    def test_the_admin_offers_the_box_that_fixes_it(self):
        page = self.client.get('/admin/user/user/%d/change/' % self.owner.pk)
        self.assertEqual(page.status_code, 200)
        form = page.context['adminform'].form
        self.assertIn('phone_verified', form.fields)
        self.assertFalse(form.fields['phone_verified'].disabled)

    def test_ticking_it_opens_the_panel(self):
        self.owner.phone_verified = True
        self.owner.save(update_fields=['phone_verified'])
        self.assertEqual(self.client.get(at('uz', 'panel_orders')).status_code, 200)


class SellerAddressTests(TestCase):
    """The postal address is printed in one place only (§17 #226).

    The contact card carries the name, the phone, the
    Telegram handle and the email, and nothing else. The address stays in the
    terms because the E-commerce Law wants a postal address in a public offer
    (art. 16), and the privacy policy points there rather than repeating it.
    """

    def address(self):
        from core import legal
        return legal.SELLER['address']

    def test_the_contact_page_does_not_print_it(self):
        for lang in ('uz', 'ru', 'en'):
            with self.subTest(lang=lang):
                html = self.client.get(at(lang, 'contact')).content.decode()
                self.assertNotIn(self.address(), html)

    def test_the_contact_page_still_names_the_seller_and_how_to_reach_him(self):
        from core import legal
        html = self.client.get(at('uz', 'contact')).content.decode()
        self.assertIn(legal.SELLER['registered_name'], html)
        self.assertIn(legal.SELLER['phone'], html)
        self.assertIn(legal.SELLER['email'], html)
        self.assertIn(legal.SELLER['telegram'], html)

    def test_the_offer_still_carries_the_address(self):
        for lang in ('uz', 'ru', 'en'):
            with self.subTest(lang=lang):
                html = self.client.get(at(lang, 'terms')).content.decode()
                self.assertIn(self.address(), html)

    def test_the_privacy_policy_points_at_the_offer(self):
        for lang in ('uz', 'ru', 'en'):
            with self.subTest(lang=lang):
                html = self.client.get(at(lang, 'privacy')).content.decode()
                self.assertNotIn(self.address(), html)
                self.assertIn('%s#seller' % at(lang, 'terms'), html)
