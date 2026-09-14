"""Phase 4 guards: slugs, order numbers, the legacy 301, stock, and the seeds.

These are the Definition of Done for Phase 4 written as assertions, so a later
phase can't quietly undo them. Several of them protect money or inventory: that
a sold-out size cannot be over-ordered, and that a paid order moves stock
exactly once.

The pickup-point tests that used to live here are gone with the table they
guarded (§17 #84). Their replacements — the region, district and postal-index
rules, which are what actually decides where a parcel goes — are in
``test_phase6.py``, with the phase that owns them.
"""
from decimal import Decimal

from click_up.models import ClickTransaction
from django.test import TestCase
from django.urls import reverse

from cart import services as cart_services
from cart.models import Cart, CartItem
from payment import services as payment_services
from payment.models import DeliveryOption, Order
from product.models import Category, Colour, Product, Size, Variant
from user.models import User


def make_product(name, *, stock=5, available=True, price='150000', **kwargs):
    """Create a product with one purchasable variant. Returns (product, variant)."""
    product = Product.objects.create(name=name, **kwargs)
    variant = Variant.objects.create(
        product=product,
        size=Size.objects.create(size=f"S-{product.pk}"),
        colour=Colour.objects.create(colour=f"C-{product.pk}"),
        price=Decimal(price),
        available=available,
        stock=stock,
    )
    return product, variant


class SlugTests(TestCase):
    """Every product and category gets a unique, ASCII, name-derived slug."""

    def test_slug_is_generated_from_the_uzbek_name(self):
        product, _ = make_product('Oʻzbek koʻylak')
        # The modifier letters are non-ASCII, so slugify drops them.
        self.assertEqual(product.slug, 'ozbek-koylak')

    def test_colliding_names_get_distinct_slugs(self):
        first, _ = make_product('Bir xil nom')
        second, _ = make_product('Bir xil nom')
        self.assertNotEqual(first.slug, second.slug)
        self.assertEqual(second.slug, 'bir-xil-nom-2')

    def test_unsluggable_name_falls_back_to_the_model_name(self):
        product, _ = make_product('...')
        self.assertEqual(product.slug, 'product')

    def test_an_explicit_slug_is_respected(self):
        product = Product.objects.create(name='Nom', slug='qolda-yozilgan')
        self.assertEqual(product.slug, 'qolda-yozilgan')

    def test_renaming_does_not_move_the_url(self):
        """The slug is the permanent URL: renaming must not break existing links."""
        product, _ = make_product('Asl nom')
        product.name = 'Yangi nom'
        product.save()
        self.assertEqual(product.slug, 'asl-nom')

    def test_category_slug_is_generated_too(self):
        category = Category.objects.create(name='Futbolkalar')
        self.assertEqual(category.slug, 'futbolkalar')


class LegacyUrlTests(TestCase):
    """The pre-Phase-4 /item/<pk>/ URL keeps working, with a 301.

    Since §17 #121 it takes two hops from the unprefixed form: the language
    prefix is negotiated first (302, because the destination depends on who is
    asking), and the move from id to slug is still permanent (301).
    """

    def test_old_integer_url_permanently_redirects_to_the_slug_url(self):
        product, _ = make_product('Eski havola')
        response = self.client.get(f"/uz/item/{product.pk}/")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], reverse('item', kwargs={'slug': product.slug}))

    def test_the_unprefixed_legacy_url_still_reaches_the_product(self):
        """The oldest links in the wild have neither a language nor a slug."""
        product, _ = make_product('Juda eski havola')
        response = self.client.get(f"/item/{product.pk}/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1][0],
                         reverse('item', kwargs={'slug': product.slug}))

    def test_the_slug_url_renders(self):
        product, _ = make_product('Yangi havola')
        self.assertEqual(self.client.get(reverse('item', kwargs={'slug': product.slug})).status_code, 200)

    def test_an_inactive_product_is_404(self):
        product, _ = make_product('Yashirin', is_active=False)
        self.assertEqual(
            self.client.get(reverse('item', kwargs={'slug': product.slug})).status_code, 404
        )


class OrderNumberTests(TestCase):
    """Orders get a GX-YYMMDD-NNNN number, sequential within the day."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='ordernouser', password='order-no-pass-123',
            phone='+998 90 111 22 33', phone_verified=True,
        )

    def _order(self):
        cart = Cart.objects.create(user=self.user, status=False)
        return Order.objects.create(
            user=self.user, cart=cart, phone='+998 90 111 22 33',
            address='Toshkent', total_price=Decimal('1000'),
        )

    def test_order_no_is_assigned_and_well_formed(self):
        order = self._order()
        self.assertRegex(order.order_no, r'^GX-\d{6}-\d{4,}$')

    def test_numbers_are_sequential_within_the_day(self):
        first, second = self._order(), self._order()
        self.assertEqual(int(second.order_no.rsplit('-', 1)[1]),
                         int(first.order_no.rsplit('-', 1)[1]) + 1)

    def test_every_order_has_one(self):
        self._order()
        self._order()
        self.assertFalse(Order.objects.filter(order_no='').exists())
        self.assertEqual(Order.objects.values('order_no').distinct().count(),
                         Order.objects.count())


class StockTests(TestCase):
    """Stock is what decides purchasability, and a cart cannot exceed it."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='stockuser', password='stock-pass-123',
            phone='+998 90 222 33 44', phone_verified=True,
        )

    def test_is_purchasable_needs_both_flags(self):
        _, in_stock = make_product('Bor', stock=3, available=True)
        _, sold_out = make_product('Tugagan', stock=0, available=True)
        _, withdrawn = make_product('Sotuvda yoʻq', stock=3, available=False)
        self.assertTrue(in_stock.is_purchasable)
        self.assertFalse(sold_out.is_purchasable)
        self.assertFalse(withdrawn.is_purchasable)

    def test_resolve_variant_rejects_a_sold_out_size(self):
        product, variant = make_product('Tugagan oʻlcham', stock=0)
        with self.assertRaises(cart_services.CartError):
            cart_services.resolve_variant(product, variant.colour_id, variant.size_id)

    def test_add_variant_caps_the_line_at_available_stock(self):
        _, variant = make_product('Uchta bor', stock=3)
        cart = Cart.objects.create(user=self.user)
        item = cart_services.add_variant(cart, variant, 10)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)

    def test_repeated_adds_cannot_walk_past_stock(self):
        _, variant = make_product('Ikkita bor', stock=2)
        cart = Cart.objects.create(user=self.user)
        for _ in range(5):
            cart_services.add_variant(cart, variant, 1)
        self.assertEqual(CartItem.objects.get(cart=cart, variant=variant).quantity, 2)

    def test_the_99_ceiling_still_applies_when_stock_is_plentiful(self):
        _, variant = make_product('Koʻp bor', stock=500)
        cart = Cart.objects.create(user=self.user)
        item = cart_services.add_variant(cart, variant, 150)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 99)

    def test_set_item_quantity_clamps_to_stock(self):
        _, variant = make_product('Toʻrtta bor', stock=4)
        cart = Cart.objects.create(user=self.user)
        item = cart_services.add_variant(cart, variant, 1)
        cart_services.set_item_quantity(item, 40)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 4)


class StockMovementTests(TestCase):
    """A paid order takes stock exactly once; undoing it gives the stock back."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='movementuser', password='movement-pass-123',
            phone='+998 90 333 44 55', phone_verified=True,
        )

    def _paid_order_setup(self, *, stock=10, qty=3):
        product, variant = make_product('Harakat', stock=stock)
        cart = Cart.objects.create(user=self.user, status=False)
        CartItem.objects.create(cart=cart, variant=variant, quantity=qty,
                                price_stat=variant.price)
        order = Order.objects.create(
            user=self.user, cart=cart, phone='+998 90 333 44 55',
            address='Toshkent', total_price=variant.price * qty,
        )
        txn = ClickTransaction.objects.create(
            transaction_id='click-test-1', account_id=order.id,
            amount=order.total_price, state=ClickTransaction.SUCCESSFULLY,
        )
        return order, variant, txn

    def test_payment_decrements_stock(self):
        order, variant, txn = self._paid_order_setup(stock=10, qty=3)
        payment_services.apply_successful_payment(txn.transaction_id)
        variant.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(variant.stock, 7)
        self.assertEqual(order.status, Order.Status.PAID)

    def test_a_replayed_callback_does_not_decrement_twice(self):
        """Click can deliver the same callback more than once."""
        _, variant, txn = self._paid_order_setup(stock=10, qty=3)
        payment_services.apply_successful_payment(txn.transaction_id)
        payment_services.apply_successful_payment(txn.transaction_id)
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 7)

    def test_stock_never_goes_negative(self):
        """The owner may have lowered stock by hand after the order was placed."""
        _, variant, txn = self._paid_order_setup(stock=1, qty=5)
        payment_services.apply_successful_payment(txn.transaction_id)
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 0)

    def test_cancelling_a_paid_order_restores_stock(self):
        order, variant, txn = self._paid_order_setup(stock=10, qty=3)
        payment_services.apply_successful_payment(txn.transaction_id)
        order.refresh_from_db()

        self.assertTrue(payment_services.cancel_paid_order(order))
        variant.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(variant.stock, 10)
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_cancelling_an_unpaid_order_leaves_stock_alone(self):
        """An order that never reached PAID never took any stock."""
        order, variant, _ = self._paid_order_setup(stock=10, qty=3)
        self.assertTrue(payment_services.cancel_order(order))
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 10)

    def test_cancel_paid_order_refuses_an_unpaid_order(self):
        """Guards the storefront path: a customer must not cancel a paid order here."""
        order, _, _ = self._paid_order_setup()
        self.assertFalse(payment_services.cancel_paid_order(order))


class DeliveryOptionTests(TestCase):
    """The two seeded tiers exist and say what the customer has to supply.

    The branch tier's *validation* moved to Phase 6 with the redesign; what is
    still Phase 4's is that the tiers are rows at all, and that neither has a
    free threshold.
    """

    def test_both_tiers_are_seeded(self):
        codes = set(DeliveryOption.objects.values_list('code', flat=True))
        self.assertEqual({'uzpost_office', 'uzpost_door'}, codes)

    def test_the_office_tier_needs_a_branch_and_the_door_tier_does_not(self):
        office = DeliveryOption.objects.get(code='uzpost_office')
        door = DeliveryOption.objects.get(code='uzpost_door')
        self.assertTrue(office.requires_branch)
        self.assertFalse(door.requires_branch)
        self.assertEqual(office.price, Decimal('15000'))
        # 40 000 since §17 #85; migration 0015 corrected the seeded row.
        self.assertEqual(door.price, Decimal('40000'))

    def test_no_free_delivery_threshold_yet(self):
        for option in DeliveryOption.objects.all():
            self.assertEqual(option.free_from_items, 0)
            self.assertEqual(option.price_for_items(99), option.price)


class TagSeedTests(TestCase):
    """The starting tag taxonomy from plan §7 is seeded."""

    def test_the_plan_tags_exist_with_their_kinds(self):
        from product.models import Tag
        self.assertEqual(
            set(Tag.objects.filter(kind__slug='style').values_list('slug', flat=True)),
            {'oversize', 'boxy'},
        )
        self.assertEqual(
            set(Tag.objects.filter(kind__slug='theme').values_list('slug', flat=True)),
            {'anime', 'streetwear', 'music', 'sport', 'minimal', 'vintage'},
        )


class AdminDefaultColourTests(TestCase):
    """The owner never picks a colour; the admin assigns one (plan §7, §17 #23)."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(
            username='adminuser', password='admin-pass-123',
            phone='+998 90 666 77 88',
        )
        cls.staff.phone_verified = True
        cls.staff.save(update_fields=['phone_verified'])
        cls.size = Size.objects.create(size='L')

    def test_default_colour_is_reused_not_duplicated(self):
        from product.models import default_colour
        self.assertEqual(default_colour().pk, default_colour().pk)
        self.assertEqual(Colour.objects.count(), 1)

    def test_creating_a_product_in_the_admin_fills_the_variant_colour(self):
        self.client.force_login(self.staff)
        response = self.client.post('/admin/product/product/add/', {
            'category': '', 'slug': 'admin-mahsulot', 'is_active': 'on',
            'name': 'Admin mahsulot', 'description': '', 'material': '',
            'name_ru': '', 'description_ru': '', 'material_ru': '',
            'name_en': '', 'description_en': '', 'material_en': '',
            'gsm': '', 'print_method': '', 'fit': '', 'size_chart': '',
            'images-TOTAL_FORMS': '0', 'images-INITIAL_FORMS': '0',
            'images-MIN_NUM_FORMS': '0', 'images-MAX_NUM_FORMS': '1000',
            'variants-TOTAL_FORMS': '1', 'variants-INITIAL_FORMS': '0',
            'variants-MIN_NUM_FORMS': '0', 'variants-MAX_NUM_FORMS': '1000',
            'variants-0-size': str(self.size.pk),
            'variants-0-price': '150000',
            'variants-0-available': 'on',
            'variants-0-stock': '7',
        })
        self.assertEqual(response.status_code, 302, response.content[:2000])

        product = Product.objects.get(slug='admin-mahsulot')
        variant = product.variants.get()
        self.assertIsNotNone(variant.colour_id)
        self.assertEqual(variant.colour.colour, 'Standart')
        self.assertEqual(variant.stock, 7)
        self.assertTrue(variant.is_purchasable)
