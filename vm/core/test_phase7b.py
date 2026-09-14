"""Phase 7b — the products screen, which is the one the plan calls the phase's most important.

The Definition of Done says a complete product with four images, tags, specs
and a full size/stock grid can be created from a phone in one sitting. That is
the shape of this file: the pieces first, then that sentence as a test.
"""
import io

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from panel import catalogue
from product.models import (Category, ImageP, Product, Size, Tag, Variant,
                            default_colour)

from .test_phase4 import make_product
from .test_phase6 import make_user
from .test_phase7 import make_staff


def photo(size=(1200, 1500), fmt='JPEG', name='shot.jpg'):
    buf = io.BytesIO()
    Image.new('RGB', size, (90, 70, 60)).save(buf, format=fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


class GridTests(TestCase):
    """The size × price × stock grid, which is what makes a product buyable."""

    def setUp(self):
        self.product, self.variant = make_product('Panjara', stock=3)
        self.sizes = list(Size.objects.all())

    def post(self, **values):
        return catalogue.save_grid(self.product, values)

    def test_a_size_with_a_price_becomes_a_variant(self):
        size = self.sizes[0]
        self.post(**{'price_%s' % size.pk: '150000',
                     'stock_%s' % size.pk: '7',
                     'available_%s' % size.pk: 'on'})
        variant = Variant.objects.get(product=self.product, size=size)
        self.assertEqual(variant.price, Decimal('150000'))
        self.assertEqual(variant.stock, 7)
        self.assertTrue(variant.available)

    def test_the_colour_is_applied_without_being_asked_for(self):
        """The storefront renders no colour picker, so neither does the panel."""
        size = self.sizes[0]
        self.post(**{'price_%s' % size.pk: '100000'})
        variant = Variant.objects.get(product=self.product, size=size)
        self.assertEqual(variant.colour, default_colour())

    def test_a_size_with_no_price_is_not_a_size_this_product_comes_in(self):
        """Clearing a price should make the size disappear from the page."""
        first, second = self.sizes[0], self.sizes[1]
        self.post(**{'price_%s' % first.pk: '100000',
                     'price_%s' % second.pk: '100000'})
        self.assertEqual(self.product.variants.count(), 2)
        self.post(**{'price_%s' % first.pk: '100000'})
        self.assertEqual([v.size_id for v in self.product.variants.all()], [first.pk])

    def test_a_variant_somebody_has_ordered_is_switched_off_rather_than_deleted(self):
        """Losing what a customer bought to tidy a form is not a trade worth making."""
        from cart.models import Cart, CartItem
        cart = Cart.objects.create(status=False)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1,
                                price_stat=self.variant.price)
        other = self.sizes[1] if self.sizes[1] != self.variant.size else self.sizes[0]
        self.post(**{'price_%s' % other.pk: '120000'})

        self.variant.refresh_from_db()
        self.assertFalse(self.variant.available)
        self.assertEqual(self.variant.stock, 0)
        self.assertTrue(Variant.objects.filter(pk=self.variant.pk).exists())

    def test_a_grid_with_no_prices_at_all_is_refused(self):
        with self.assertRaises(ValidationError):
            self.post()

    def test_a_price_typed_with_spaces_is_understood(self):
        """"150 000" is how a price is written in Uzbek, and how it will be typed."""
        size = self.sizes[0]
        self.post(**{'price_%s' % size.pk: '150 000'})
        self.assertEqual(Variant.objects.get(product=self.product, size=size).price,
                         Decimal('150000'))

    def test_a_negative_price_is_refused(self):
        with self.assertRaises(ValidationError):
            self.post(**{'price_%s' % self.sizes[0].pk: '-5'})


class ImageTests(TestCase):
    """Photographs: the same pipeline as a customer's, and an order the owner sets."""

    def setUp(self):
        self.product, _ = make_product('Rasmli', stock=2)

    def test_an_uploaded_photograph_loses_its_metadata(self):
        """The owner's phone writes GPS into a photograph just as a customer's does."""
        from product import images as pipeline
        exif = Image.Exif()
        exif[271] = 'OWNER-CAMERA'
        buf = io.BytesIO()
        Image.new('RGB', (900, 1100), (10, 20, 30)).save(buf, format='JPEG',
                                                         exif=exif.tobytes())
        upload = SimpleUploadedFile('gps.jpg', buf.getvalue(), content_type='image/jpeg')
        catalogue.add_images(self.product, [upload])
        stored = self.product.images.get()
        self.assertFalse(pipeline.has_metadata(stored.picture.path))

    def test_a_product_photograph_is_allowed_to_be_larger_than_a_review_one(self):
        """It is the biggest thing on the product page and meant to be looked at."""
        from product import images as pipeline
        catalogue.add_images(self.product, [photo(size=(3000, 3000))])
        with Image.open(self.product.images.get().picture.path) as out:
            self.assertGreater(max(out.size), pipeline.MAX_EDGE)
            self.assertLessEqual(max(out.size), pipeline.PRODUCT_MAX_EDGE)

    def test_photographs_are_numbered_in_the_order_they_arrive(self):
        catalogue.add_images(self.product, [photo(name='a.jpg'), photo(name='b.jpg')])
        self.assertEqual([i.order for i in self.product.images.all()], [0, 1])

    def test_more_than_the_limit_is_refused(self):
        with self.assertRaises(ValidationError):
            catalogue.add_images(self.product,
                                 [photo() for _ in range(catalogue.MAX_IMAGES + 1)])

    def test_dragging_renumbers_them(self):
        catalogue.add_images(self.product, [photo(name='a.jpg'), photo(name='b.jpg'),
                                            photo(name='c.jpg')])
        ids = list(self.product.images.values_list('pk', flat=True))
        catalogue.reorder_images(self.product, [ids[2], ids[0], ids[1]])
        self.assertEqual(list(self.product.images.values_list('pk', flat=True)),
                         [ids[2], ids[0], ids[1]])

    def test_a_stale_drag_does_not_drop_a_photograph(self):
        """An id list that arrives missing one must not delete it."""
        catalogue.add_images(self.product, [photo(name='a.jpg'), photo(name='b.jpg')])
        ids = list(self.product.images.values_list('pk', flat=True))
        catalogue.reorder_images(self.product, [ids[1]])
        self.assertEqual(self.product.images.count(), 2)
        self.assertEqual(list(self.product.images.values_list('pk', flat=True)),
                         [ids[1], ids[0]])


class InlineTests(TestCase):
    """The list's inline edits, which are the two things that change daily."""

    def setUp(self):
        self.staff = make_staff('katalog', '+998901230001')
        self.product, self.variant = make_product('Tezkor', stock=9)
        self.client.force_login(self.staff)

    def url(self):
        return reverse('panel_product_inline', kwargs={'slug': self.product.slug})

    def test_the_switch_hides_a_product_from_the_shop(self):
        self.client.post(self.url(), {'field': 'is_active', 'value': '0'})
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)

    def test_a_price_applies_to_every_size(self):
        """One price per design is how this catalogue works."""
        self.client.post(self.url(), {'field': 'price', 'value': '199000'})
        for variant in self.product.variants.all():
            self.assertEqual(variant.price, Decimal('199000'))

    def test_a_bad_price_is_refused_with_a_sentence(self):
        response = self.client.post(self.url(), {'field': 'price', 'value': 'oltin'})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()['error'])

    def test_stock_is_edited_one_size_at_a_time(self):
        self.client.post(self.url(), {'field': 'stock', 'value': '2',
                                      'size': self.variant.size_id})
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 2)

    def test_the_answer_says_whether_it_is_still_buyable(self):
        """The box turns red as the owner types the zero, not at the next load."""
        body = self.client.post(self.url(), {'field': 'stock', 'value': '0',
                                             'size': self.variant.size_id}).json()
        self.assertFalse(body['purchasable'])

    def test_it_can_change_nothing_else(self):
        """A narrow endpoint: the edit screen is where a product is edited."""
        response = self.client.post(self.url(), {'field': 'name', 'value': 'Boshqa'})
        self.assertEqual(response.status_code, 400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, 'Tezkor')

    def test_a_customer_cannot_reach_it(self):
        self.client.force_login(make_user('oddiy', '+998901230002'))
        self.assertEqual(self.client.post(
            self.url(), {'field': 'is_active', 'value': '0'}).status_code, 403)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)


class DefinitionOfDoneTests(TestCase):
    """The DoD clause, as a test: a complete product, created in one sitting.

    "Complete" is the plan's word and it means all of it — four photographs,
    tags, the spec fields and a full size/stock grid. Driven through the real
    views, because the point of the sentence is that the *screens* can do it,
    not that the services can.
    """

    def setUp(self):
        self.staff = make_staff('egasi', '+998901230003')
        self.client.force_login(self.staff)
        self.category = Category.objects.create(name='Futbolkalar', slug='futbolkalar')
        self.tags = [Tag.objects.create(slug='anime-%d' % n, name='Anime %d' % n)
                     for n in range(2)]
        self.sizes = list(Size.objects.all()) or [
            Size.objects.create(size=name) for name in ('S', 'M', 'L')]

    def test_a_complete_product_can_be_created_in_one_sitting(self):
        # 1. The text, the specs, the tags and the grid go in together.
        body = {
            'name': 'Toʻliq dizayn', 'name_ru': 'Полный дизайн', 'name_en': 'Full design',
            'description': 'Uzbek', 'description_ru': 'Русский', 'description_en': 'English',
            'category': self.category.pk,
            'gsm': '190', 'material': '100% paxta', 'material_ru': '100% хлопок',
            'material_en': '100% cotton',
            'print_method': 'dtf', 'fit': 'oversize',
            'tags': [tag.pk for tag in self.tags],
            'is_active': 'on',
        }
        for size in self.sizes:
            body['price_%s' % size.pk] = '189000'
            body['stock_%s' % size.pk] = '4'
            body['available_%s' % size.pk] = 'on'

        response = self.client.post(reverse('panel_product_new'), body)
        self.assertEqual(response.status_code, 302)

        product = Product.objects.get(name='Toʻliq dizayn')
        self.assertEqual(product.name_ru, 'Полный дизайн')
        self.assertEqual(product.description_en, 'English')
        self.assertEqual(product.category, self.category)
        self.assertEqual(product.gsm, 190)
        self.assertEqual(product.material_ru, '100% хлопок')
        self.assertEqual(product.print_method, 'dtf')
        self.assertEqual(product.fit, 'oversize')
        self.assertEqual(product.tags.count(), 2)
        self.assertEqual(product.variants.count(), len(self.sizes))
        self.assertTrue(product.slug, 'the slug is derived, never typed')

        # 2. Then the photographs, onto the screen it landed on.
        images_url = reverse('panel_product_images', kwargs={'slug': product.slug})
        answer = self.client.post(images_url, {
            'action': 'add',
            'images': [photo(name='%d.jpg' % n) for n in range(4)],
        })
        self.assertTrue(answer.json()['ok'])
        self.assertEqual(product.images.count(), 4)

        # 3. And it is a product the storefront will actually sell.
        product.refresh_from_db()
        self.assertTrue(product.is_active)
        self.assertTrue(any(v.is_purchasable for v in product.variants.all()))
        self.assertEqual(self.client.get(product.get_absolute_url()).status_code, 200)

    def test_the_slug_survives_a_rename(self):
        """It is the product's permanent URL; renaming must not break its links."""
        body = {'name': 'Birinchi nom', 'is_active': 'on'}
        for size in self.sizes[:1]:
            body['price_%s' % size.pk] = '100000'
        self.client.post(reverse('panel_product_new'), body)
        product = Product.objects.get(name='Birinchi nom')
        slug = product.slug

        body['name'] = 'Ikkinchi nom'
        self.client.post(reverse('panel_product', kwargs={'slug': slug}), body)
        product.refresh_from_db()
        self.assertEqual(product.name, 'Ikkinchi nom')
        self.assertEqual(product.slug, slug)

    def test_a_product_with_no_name_is_refused_and_says_why(self):
        response = self.client.post(reverse('panel_product_new'), {'name': '  '})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(name='').exists())

    def test_nothing_is_saved_when_the_grid_is_refused(self):
        """One transaction: a product whose grid failed must not exist half-made."""
        before = Product.objects.count()
        self.client.post(reverse('panel_product_new'),
                         {'name': 'Yarim', 'is_active': 'on'})
        self.assertEqual(Product.objects.count(), before)

    def test_the_form_is_reachable_and_guarded(self):
        self.assertEqual(self.client.get(reverse('panel_product_new')).status_code, 200)
        self.client.force_login(make_user('begona', '+998901230004'))
        self.assertEqual(self.client.get(reverse('panel_product_new')).status_code, 403)
