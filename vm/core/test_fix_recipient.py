"""The name typed at checkout is the name on the parcel.

The checkout has asked for a name since before the rebuild, required it, and
then dropped it: ``create_order_from_cart`` had no argument to receive it, so
the panel, the admin and the Telegram message all fell back to the account's
own name. For a gift - or a parent ordering for a child - that is the wrong
person, and a post office hands a parcel to the name written on it.

These tests hold the fix: the name is kept, it is limited by the column with a
sentence rather than a 500, and every screen that names the customer names the
recipient first.
"""
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from cart.models import Cart, CartItem
from payment import services
from payment.models import RECIPIENT_NAME_MAX, Order

from .test_phase4 import make_product
from .test_phase6 import make_regions, make_user
from .test_phase7 import make_staff
from .test_phase12 import make_order


class CheckoutKeepsTheNameTests(TestCase):
    """What the customer types is what the order keeps."""

    def setUp(self):
        self.geo = make_regions()
        self.user = make_user('hadyachi', '+998901290001')
        self.user.first_name = 'Hisob egasi'
        self.user.save(update_fields=['first_name'])
        _, variant = make_product('Sovgʻa', stock=5)
        self.client.force_login(self.user)
        self.cart = Cart.objects.create(user=self.user, status=True)
        CartItem.objects.create(cart=self.cart, variant=variant, quantity=1,
                                price_stat=variant.price)

    def _checkout(self, name='Dilnoza Karimova'):
        return self.client.post(reverse('checkout'), {
            'name': name, 'phone': '+998 90 129 00 01',
            'delivery_option': 'uzpost_office',
            'region': self.geo['tashkent'].pk,
            'district': self.geo['chilonzor'].pk,
            'postal_index': '100011',
            'payment_method': 'click', 'notes': '',
        })

    def test_the_typed_name_is_kept_rather_than_the_accounts(self):
        self._checkout()
        order = Order.objects.get(cart=self.cart)
        self.assertEqual(order.recipient_name, 'Dilnoza Karimova')
        self.assertNotEqual(order.recipient_name, self.user.first_name)

    def test_a_name_at_the_limit_is_accepted(self):
        self._checkout(name='A' * RECIPIENT_NAME_MAX)
        self.assertEqual(Order.objects.get(cart=self.cart).recipient_name,
                         'A' * RECIPIENT_NAME_MAX)

    def test_a_longer_name_is_refused_and_nothing_typed_is_lost(self):
        """A sentence, not a 500 and not a name cut short on the parcel."""
        response = self._checkout(name='A' * (RECIPIENT_NAME_MAX + 1))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.filter(cart=self.cart).exists())
        # The form comes back as it was sent (§17 #118, #133).
        self.assertContains(response, 'value="100011"')
        self.assertContains(response, 'A' * (RECIPIENT_NAME_MAX + 1))

    def test_the_field_carries_the_same_limit_as_the_column(self):
        page = self.client.get(reverse('checkout')).content.decode()
        self.assertIn('maxlength="%d"' % RECIPIENT_NAME_MAX, page)
        self.assertEqual(Order._meta.get_field('recipient_name').max_length,
                         RECIPIENT_NAME_MAX)

    def test_the_service_still_works_for_a_caller_that_passes_no_name(self):
        """Added to, not restructured: the old keyword set is still enough."""
        order = services.create_order_from_cart(
            self.user, self.cart, phone='+998 90 129 00 01', address='Amir Temur 1',
            notes='', payment_method='click')
        self.assertEqual(order.recipient_name, '')

    def test_the_notification_names_the_recipient(self):
        with mock.patch('core.telegram.send', return_value=True) as send:
            with self.captureOnCommitCallbacks(execute=True):
                self._checkout()
        body = send.call_args[0][0]
        self.assertIn('Dilnoza Karimova', body)
        self.assertNotIn('Hisob egasi', body)

    def test_the_customer_sees_the_name_on_their_order(self):
        self._checkout()
        order = Order.objects.get(cart=self.cart)
        self.assertContains(self.client.get(reverse('order_detail', args=[order.pk])),
                            'Dilnoza Karimova')


class PanelNamesTheRecipientTests(TestCase):
    """The owner reads the name he has to write on the parcel."""

    def setUp(self):
        self.client.force_login(make_staff('qadoqchi', '+998901290002'))
        self.customer = make_user('buyurtmachi', '+998901290003')
        self.customer.first_name = 'Hisob egasi'
        self.customer.save(update_fields=['first_name'])
        _, variant = make_product('Qadoq', stock=5)
        self.order = make_order(self.customer, variant, status='paid')
        Order.objects.filter(pk=self.order.pk).update(recipient_name='Jasur Toshmatov')
        self.order.refresh_from_db()

    def test_the_order_page_names_the_recipient_and_the_account(self):
        page = self.client.get(reverse('panel_order',
                                       kwargs={'order_no': self.order.order_no}))
        self.assertContains(page, 'Jasur Toshmatov')
        self.assertContains(page, 'buyurtmachi')

    def test_the_list_names_the_recipient(self):
        self.assertContains(self.client.get(reverse('panel_orders')), 'Jasur Toshmatov')

    def test_the_search_finds_an_order_by_its_recipient(self):
        page = self.client.get(reverse('panel_orders'), {'q': 'Toshmatov'})
        self.assertEqual([o.pk for o in page.context['orders'].object_list],
                         [self.order.pk])

    def test_an_order_from_before_falls_back_to_the_account(self):
        Order.objects.filter(pk=self.order.pk).update(recipient_name='')
        page = self.client.get(reverse('panel_order',
                                       kwargs={'order_no': self.order.order_no}))
        self.assertContains(page, 'Hisob egasi')
