"""Phase 7a — the panel's frame, its dashboard and its orders screens.

Three things are worth asserting here and the rest is rendering:

* **who gets in.** The Definition of Done says non-staff get 403, and a guard
  is the one piece of a staff panel where being almost right is worthless.
* **that every status change is recorded.** The audit log exists so that "who
  cancelled this order" has an answer; a log written by whichever call site
  remembers to write is a log with holes in it, so both call sites are tested.
* **that the dashboard's numbers are the numbers.** A dashboard is read at a
  glance and believed — a wrong figure there is worse than no figure.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cart.models import Cart, CartItem
from core.models import Msg
from panel.models import OrderStatusChange
from panel.services import UnknownStatus, set_status
from payment.models import Order
from product.models import Review

from .test_phase4 import make_product
from .test_phase6 import make_user
from .test_phase12 import make_order


def make_staff(username='xodim', phone='+998901220001'):
    user = make_user(username, phone)
    user.is_staff = True
    user.save(update_fields=['is_staff'])
    return user


class GuardTests(TestCase):
    """Who may open the panel. Every screen, not just the first one."""

    def setUp(self):
        self.staff = make_staff()
        self.customer = make_user('mijoz', '+998901220002')
        product, variant = make_product('Panel', stock=3)
        self.order = make_order(self.customer, variant, status='paid')

    def urls(self):
        return [
            reverse('panel_dashboard'),
            reverse('panel_orders'),
            reverse('panel_order', kwargs={'order_no': self.order.order_no}),
        ]

    def test_a_signed_in_customer_gets_403_not_a_login_form(self):
        """Django's own staff_member_required would show them a second login.

        A customer who is already signed in has not mistyped a password; they
        are somewhere they should not be, and the answer is no.
        """
        self.client.force_login(self.customer)
        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_an_anonymous_visitor_is_sent_to_the_login_form(self):
        """The person this actually happens to is the owner, session expired."""
        for url in self.urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('login'), response.url)
                self.assertIn('next=', response.url)

    def test_staff_get_in(self):
        self.client.force_login(self.staff)
        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_the_status_endpoint_is_guarded_too(self):
        """The screens being guarded says nothing about the endpoint behind them."""
        url = reverse('panel_order_status', kwargs={'order_no': self.order.order_no})
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(url, {'status': 'cancelled'}).status_code, 403)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')

    def test_the_panel_is_not_indexable(self):
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse('panel_dashboard')),
                            'noindex')


class AuditTests(TestCase):
    """Every path that moves a status writes a row. Both of them."""

    def setUp(self):
        self.staff = make_staff()
        self.customer = make_user('xaridor', '+998901220003')
        product, self.variant = make_product('Tarix', stock=4)
        self.order = make_order(self.customer, self.variant, status='paid')

    def test_the_service_records_who_and_when(self):
        change = set_status(self.order, Order.Status.PROCESSING, by=self.staff)
        self.assertEqual((change.from_status, change.to_status), ('paid', 'processing'))
        self.assertEqual(change.changed_by, self.staff)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'processing')

    def test_setting_the_status_it_already_has_records_nothing(self):
        """Re-tapping the current status should not fill the history with noise."""
        self.assertIsNone(set_status(self.order, Order.Status.PAID, by=self.staff))
        self.assertEqual(OrderStatusChange.objects.count(), 0)

    def test_an_unknown_status_is_refused(self):
        with self.assertRaises(UnknownStatus):
            set_status(self.order, 'teleported', by=self.staff)

    def test_the_panel_records_it(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse('panel_order_status', kwargs={'order_no': self.order.order_no}),
            {'status': 'on_the_way'})
        change = OrderStatusChange.objects.get()
        self.assertEqual(change.to_status, 'on_the_way')
        self.assertEqual(change.changed_by, self.staff)

    def test_the_django_admin_records_it_too(self):
        """The admin can change a status from its list, and used to do it silently."""
        self.staff.is_superuser = True
        self.staff.save(update_fields=['is_superuser'])
        self.client.force_login(self.staff)
        self.client.post(
            reverse('admin:payment_order_change', args=[self.order.pk]),
            {'status': 'cancelled'})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'cancelled')
        change = OrderStatusChange.objects.get()
        self.assertEqual((change.from_status, change.to_status), ('paid', 'cancelled'))
        self.assertEqual(change.changed_by, self.staff)

    def test_the_panel_will_not_set_a_status_it_does_not_offer(self):
        """`paying` is not a state a person may push an order back into."""
        self.client.force_login(self.staff)
        self.client.post(
            reverse('panel_order_status', kwargs={'order_no': self.order.order_no}),
            {'status': 'paying'})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')
        self.assertEqual(OrderStatusChange.objects.count(), 0)

    def test_a_deleted_staff_account_does_not_take_the_history_with_it(self):
        set_status(self.order, Order.Status.DONE, by=self.staff)
        self.staff.delete()
        change = OrderStatusChange.objects.get()
        self.assertIsNone(change.changed_by)
        self.assertEqual(change.to_status, 'done')

    def test_the_fetch_path_answers_json(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('panel_order_status', kwargs={'order_no': self.order.order_no}),
            {'status': 'done'}, headers={'x-requested-with': 'fetch'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertEqual(body['status'], 'done')
        self.assertTrue(body['label'])


class DashboardTests(TestCase):
    """The numbers, each against a database built to make it wrong if it lies."""

    def setUp(self):
        self.staff = make_staff('boshqaruvchi', '+998901220004')
        self.customer = make_user('sotib', '+998901220005')
        self.product, self.variant = make_product('Hisob', stock=20)
        self.client.force_login(self.staff)

    def _order(self, status, total, days_ago=0):
        cart = Cart.objects.create(user=self.customer, status=False)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1,
                                price_stat=self.variant.price)
        order = Order.objects.create(user=self.customer, cart=cart,
                                     phone=self.customer.phone, address='Test',
                                     total_price=Decimal(total), status=status)
        if days_ago:
            when = timezone.now() - timedelta(days=days_ago)
            Order.objects.filter(pk=order.pk).update(created_at=when)
        return order

    def context(self):
        return self.client.get(reverse('panel_dashboard')).context

    def test_an_unpaid_order_is_not_a_sale(self):
        """`paying` counted as revenue would make every figure flattering."""
        self._order('paying', 500000)
        self._order('paid', 100000)
        ctx = self.context()
        self.assertEqual(ctx['orders_today'], 1)
        self.assertEqual(ctx['revenue_today'], Decimal('100000'))
        self.assertEqual(ctx['awaiting'], 1)

    def test_yesterdays_order_is_not_todays(self):
        self._order('paid', 70000, days_ago=1)
        self.assertEqual(self.context()['orders_today'], 0)

    def test_to_pack_is_paid_and_processing_together(self):
        """Both mean the same thing to somebody holding a roll of tape."""
        self._order('paid', 10)
        self._order('processing', 10)
        self._order('on_the_way', 10)
        ctx = self.context()
        self.assertEqual(ctx['to_pack'], 2)
        self.assertEqual(ctx['on_the_way'], 1)

    def test_low_stock_counts_only_what_is_actually_for_sale(self):
        from product.models import Variant
        Variant.objects.filter(pk=self.variant.pk).update(stock=2)
        hidden, hidden_variant = make_product('Yashirin', stock=1)
        hidden.is_active = False
        hidden.save(update_fields=['is_active'])
        self.assertEqual(self.context()['low_stock_count'], 1)

    def test_unread_messages_are_counted_and_read_ones_are_not(self):
        Msg.objects.create(user=self.customer, phone_num='+998901220005',
                           topic='Savol', msg_text='?')
        Msg.objects.create(user=self.customer, phone_num='+998901220005',
                           topic='Javob berilgan', msg_text='?', is_read=True)
        self.assertEqual(self.context()['unread'], 1)

    def test_reviews_awaiting_moderation_are_counted(self):
        from product import services as product_services
        order = make_order(self.customer, self.variant)
        product_services.create_review(self.customer, order, self.product, 5)
        self.assertEqual(self.context()['pending_reviews'], 1)

    def test_every_work_tile_is_a_link_to_the_screen_that_does_it(self):
        """A number with nowhere to go is read once and then ignored."""
        response = self.client.get(reverse('panel_dashboard'))
        self.assertContains(response, reverse('panel_orders') + '?status=paid')
        self.assertContains(response, reverse('panel_orders') + '?status=on_the_way')


class OrderListTests(TestCase):
    """Filters and search, which is how the list stops being forty rows."""

    def setUp(self):
        self.staff = make_staff('roʻyxat', '+998901220006')
        self.one = make_user('birinchi', '+998901220007')
        self.two = make_user('ikkinchi', '+998901220008')
        product, self.variant = make_product('Filtr', stock=9)
        self.paid = make_order(self.one, self.variant, status='paid')
        self.done = make_order(self.two, self.variant, status='done')
        self.client.force_login(self.staff)

    def numbers(self, **params):
        response = self.client.get(reverse('panel_orders'), params)
        return [o.order_no for o in response.context['orders']]

    def test_no_filter_shows_everything_newest_first(self):
        self.assertEqual(set(self.numbers()), {self.paid.order_no, self.done.order_no})

    def test_filtering_by_status(self):
        self.assertEqual(self.numbers(status='paid'), [self.paid.order_no])

    def test_an_invented_status_is_ignored_rather_than_erroring(self):
        """A hand-edited query string must not be able to 500 the screen."""
        self.assertEqual(set(self.numbers(status='nonsense')),
                         {self.paid.order_no, self.done.order_no})

    def test_searching_by_order_number(self):
        self.assertEqual(self.numbers(q=self.paid.order_no), [self.paid.order_no])

    def test_searching_by_customer_name(self):
        self.assertEqual(self.numbers(q='ikkinchi'), [self.done.order_no])

    def test_searching_by_phone(self):
        self.assertEqual(self.numbers(q='1220007'), [self.paid.order_no])

    def test_a_filtered_list_is_a_url(self):
        """So "everything to pack" can be a bookmark, and a search can be sent."""
        response = self.client.get(reverse('panel_orders'), {'status': 'paid'})
        self.assertEqual(response.context['filters']['status'], 'paid')
        self.assertEqual(response.context['total'], 1)


class OrderDetailTests(TestCase):
    """One order: what it must show, and what it must not."""

    def setUp(self):
        self.staff = make_staff('tafsilot', '+998901220009')
        self.customer = make_user('egasi', '+998901220010')
        self.product, self.variant = make_product('Tafsilot', stock=6)
        self.order = make_order(self.customer, self.variant, status='paid')
        self.client.force_login(self.staff)

    def page(self):
        return self.client.get(reverse('panel_order',
                                       kwargs={'order_no': self.order.order_no}))

    def test_it_is_reached_by_order_number_not_by_id(self):
        """The id is deliberately never shown: it leaks how many orders exist."""
        self.assertEqual(self.page().status_code, 200)
        self.assertEqual(self.client.get('/uz/boshqaruv/buyurtmalar/%d/'
                                         % self.order.pk).status_code, 404)

    def test_the_phone_number_is_tappable(self):
        """The first job of this page is to let somebody ring the customer.

        The href carries the number with no spaces in it — numbers are stored
        grouped, "+998 90 122 00 07", and a ``tel:`` URI with spaces is one
        some Android dialers will not open — while the text on screen stays
        grouped, because that is the form a person reads out loud.
        """
        response = self.page()
        self.assertContains(response, 'tel:%s' % self.order.phone.replace(' ', ''))
        self.assertContains(response, self.order.phone)

    def test_it_lists_what_was_actually_bought(self):
        self.assertContains(self.page(), 'Tafsilot')

    def test_the_history_is_on_the_page_once_there_is_any(self):
        set_status(self.order, Order.Status.ON_THE_WAY, by=self.staff)
        response = self.page()
        self.assertContains(response, self.staff.username)

    def test_an_untouched_order_says_so_rather_than_showing_an_empty_box(self):
        self.assertContains(self.page(), 'oʻzgartirilmagan')

    def test_an_unknown_order_number_is_a_404(self):
        self.assertEqual(self.client.get(
            reverse('panel_order', kwargs={'order_no': 'GX-000000-0000'})).status_code, 404)


class SharedRowTests(TestCase):
    """The order row is included by two screens, so both have to feed it.

    The dashboard rendered it without `settable` and the status control came
    out as a box with an arrow and no options in it — on a page that still
    returned 200, which is why only a screenshot caught it. A shared partial
    with a required context variable needs the same assertion on every screen
    that includes it.
    """

    def setUp(self):
        self.staff = make_staff('umumiy', '+998901220011')
        customer = make_user('mijozim', '+998901220012')
        product, variant = make_product('Qator', stock=4)
        self.order = make_order(customer, variant, status='paid')
        self.client.force_login(self.staff)

    def test_every_screen_that_shows_the_row_offers_the_full_status_list(self):
        from panel.services import PANEL_CHOICES
        for url in (reverse('panel_dashboard'), reverse('panel_orders')):
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                self.assertIn(self.order.order_no, html)
                for value, label in PANEL_CHOICES:
                    self.assertIn('value="%s"' % value, html)

    def test_the_skip_link_is_styled_on_the_panel_too(self):
        """`.skip` lived in pages.css, which the panel does not load."""
        from pathlib import Path
        from django.conf import settings
        components = (Path(settings.BASE_DIR) / 'static' / 'css' / 'components.css'
                      ).read_text(encoding='utf-8')
        self.assertIn('.skip {', components)
        pages = (Path(settings.BASE_DIR) / 'static' / 'css' / 'pages.css'
                 ).read_text(encoding='utf-8')
        self.assertNotIn('.skip {', pages)

    def test_a_coordinate_is_not_written_with_commas(self):
        """Uzbek number formatting turns 41.315050 into "41,315050"."""
        from decimal import Decimal
        Order.objects.filter(pk=self.order.pk).update(
            latitude=Decimal('41.315050'), longitude=Decimal('69.247428'))
        html = self.client.get(reverse(
            'panel_order', kwargs={'order_no': self.order.order_no})).content.decode()
        self.assertIn('41.315050', html)
        self.assertNotIn('41,315050', html)


class StatusLabelTests(TestCase):
    """The order statuses a customer reads, in the language they are reading in.

    These were plain Uzbek strings with ASCII apostrophes on a TextChoices that
    predates §4 — so "To'lanmoqda" appeared in the middle of a Russian page,
    and the apostrophe was the wrong character in Uzbek as well.
    """

    def test_each_status_is_translated(self):
        from django.utils import translation
        expected = {'ru': {'paid': 'Оплачен', 'cancelled': 'Отменён'},
                    'en': {'paid': 'Paid', 'cancelled': 'Cancelled'}}
        for lang, by_status in expected.items():
            for value, want in by_status.items():
                with self.subTest(lang=lang, status=value), translation.override(lang):
                    self.assertEqual(str(Order.Status(value).label), want)

    def test_no_status_label_uses_an_ascii_apostrophe(self):
        """Uzbek Latin uses U+02BB; the straight quote is not a letter."""
        from django.utils import translation
        with translation.override('uz'):
            for value, label in Order.Status.choices:
                with self.subTest(status=value):
                    self.assertNotIn("'", str(label))


class StatusControlTests(TestCase):
    """What the control says an order's status is, beside a badge saying the same.

    `paying` is not a status the panel will set, so nothing in the select
    matched it and the browser showed the first option instead: a row whose
    badge read "Toʻlanmoqda" next to a dropdown reading "Toʻlangan". Two
    different answers to the same question, side by side, on the screen
    somebody packs parcels from.
    """

    def setUp(self):
        self.staff = make_staff('nazorat', '+998901220013')
        self.customer = make_user('kutayotgan', '+998901220014')
        product, self.variant = make_product('Nazorat', stock=4)
        self.client.force_login(self.staff)

    def html_for(self, status):
        order = make_order(self.customer, self.variant, status=status)
        return self.client.get(reverse('panel_order',
                                       kwargs={'order_no': order.order_no})
                               ).content.decode(), order

    def test_a_status_the_panel_will_not_set_is_still_what_the_control_shows(self):
        html, order = self.html_for('paying')
        self.assertIn('<option value="" selected disabled>', html)
        self.assertIn(str(Order.Status.PAYING.label), html)

    def test_that_placeholder_cannot_be_submitted(self):
        """Disabled and valueless, so choosing it is not a way to blank a status."""
        html, order = self.html_for('paying')
        self.client.post(
            reverse('panel_order_status', kwargs={'order_no': order.order_no}),
            {'status': ''})
        order.refresh_from_db()
        self.assertEqual(order.status, 'paying')

    def test_a_settable_status_needs_no_placeholder(self):
        html, order = self.html_for('paid')
        self.assertNotIn('<option value="" selected disabled>', html)
