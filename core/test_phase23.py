"""Phase 23: the owner's fourth round.

Part H: there is no payment page. The checkout's order button pays. A
gateway's order goes straight to the gateway's own page, which comes back to
the order's details; a Telegram order goes to its details page, which opens
the chat with the shop's admin at once. Back from Telegram or a gateway's
page is the checkout, which sends the customer to the order just placed
rather than to an empty basket (§17 #409). The payment page's address leads
to the order's page, and a gateway that cannot make a link leaves the
customer there, told why, with the button to try again (§17 #405, §9 Phase 23
items 35–39).

Part F: "Siz uchun" on the home page is a shelf that scrolls sideways, twelve
of the most liked designs where there were four (§17 #403, §9 Phase 23 item
29).

Each class is one of those, written as what a customer sees.
"""
import re
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from django.utils import translation
from django.utils.translation import gettext as _

from payment import services, views
from payment.models import Order
from product.models import Product

from .test_phase6 import make_user
from .test_backlog import TempMedia
from .test_phase4 import make_product
from .test_phase9 import with_photo
from .test_phase16 import CheckoutCase, order_of, sent_to_click
from .test_phase20 import ADMIN, link_in

MAIN_JS = Path(settings.BASE_DIR) / 'static' / 'js' / 'main.js'
COMPONENTS_CSS = Path(settings.BASE_DIR) / 'static' / 'css' / 'components.css'
CHECKOUT_JS = Path(settings.BASE_DIR) / 'static' / 'js' / 'checkout.js'


def said(response):
    """Every message the page came back with, as text."""
    return [str(message) for message in response.context['messages']]


class GatewayCheckoutTests(CheckoutCase):
    """A gateway's order: the order button goes on to the gateway."""

    def place(self):
        """Press the order button, and follow wherever the shop sends the customer."""
        return self.client.post(reverse('checkout'), self.form(), follow=True)

    def test_the_order_button_goes_straight_to_click(self):
        response = self.post()
        sent_to_click(self, response, Order.objects.get())

    def test_nothing_waits_on_the_order_page_for_the_customer_back_from_paying(self):
        """"Pay now" said on the order page after paying would be wrong."""
        self.post()
        order = Order.objects.get()
        response = self.client.get(reverse('order_detail', args=[order.pk]))
        self.assertEqual(said(response), [])

    def test_a_gateway_that_does_not_answer_leaves_the_customer_on_the_order(self):
        with mock.patch.object(services, 'generate_paylink',
                               side_effect=services.PaymentGatewayError('down')):
            response = self.place()
        order = Order.objects.get()
        self.assertEqual(order.status, Order.Status.PAYING)
        self.assertEqual(response.redirect_chain,
                         [(reverse('order_detail', args=[order.pk]), 302)])
        self.assertEqual(said(response), ['Toʻlov tizimi hozir javob bermayapti. '
                                          'Iltimos, birozdan soʻng qayta urinib koʻring.'])
        # And the button is there to try again.
        self.assertContains(response, 'action="%s"' % reverse('payment_start', args=[order.pk]))

    def test_a_gateway_with_no_online_payment_says_so_on_the_order(self):
        with mock.patch.object(services, 'generate_paylink',
                               side_effect=services.PaymentMethodUnavailable('click')):
            response = self.place()
        order = Order.objects.get()
        self.assertEqual(response.redirect_chain,
                         [(reverse('order_detail', args=[order.pk]), 302)])
        self.assertEqual(said(response), ['Bu toʻlov usuli uchun onlayn toʻlov yoʻq.'])

    def test_a_basket_ordered_already_leads_to_its_order(self):
        order = order_of(self.user, (self.shirt_m, 1))
        with mock.patch.object(services, 'create_order_from_cart',
                               side_effect=services.CartAlreadyCheckedOut(order)):
            response = self.place()
        self.assertEqual(response.redirect_chain,
                         [(reverse('order_detail', args=[order.pk]), 302)])
        self.assertEqual(said(response), ['Buyurtma allaqachon rasmiylashtirilgan.'])


@override_settings(TELEGRAM_PAY_ADMIN=ADMIN)
class TelegramCheckoutTests(CheckoutCase):
    """A Telegram order: the order's page opens the chat, once."""

    def place(self):
        """Press the order button for Telegram; the order and where it went."""
        response = self.post(payment_method='telegram')
        return Order.objects.get(), response

    def test_the_order_button_lands_on_the_orders_page(self):
        order, response = self.place()
        self.assertRedirects(response, reverse('order_detail', args=[order.pk]),
                             fetch_redirect_response=False)

    def test_the_page_opens_the_chat_once(self):
        order, response = self.place()
        html = self.client.get(response['Location']).content.decode()
        self.assertEqual(html.count('data-open-chat'), 1)
        tag = re.search(r'<a [^>]*data-open-chat[^>]*>', html).group(0)
        self.assertIn('href="https://t.me/%s?text=' % ADMIN, tag)
        # Back from Telegram, or a reload, does not open it again; the button stays.
        html = self.client.get(response['Location']).content.decode()
        self.assertNotIn('data-open-chat', html)
        self.assertIsNotNone(link_in(html))

    def test_the_page_says_the_order_was_taken(self):
        order, response = self.place()
        page = self.client.get(response['Location'])
        self.assertEqual(said(page), ['Buyurtma qabul qilindi. Toʻlovni amalga oshiring.'])

    def test_the_chat_opens_only_for_the_order_just_placed(self):
        order = order_of(self.user, (self.shirt_m, 1))
        Order.objects.filter(pk=order.pk).update(payment_method=Order.PaymentMethod.TELEGRAM)
        session = self.client.session
        session[views.OPEN_CHAT_KEY] = order.pk + 1
        session.save()
        html = self.client.get(reverse('order_detail', args=[order.pk])).content.decode()
        self.assertNotIn('data-open-chat', html)
        self.assertIsNotNone(link_in(html))

    def test_the_status_page_offers_the_chat_and_does_not_open_it(self):
        order = order_of(self.user, (self.shirt_m, 1))
        Order.objects.filter(pk=order.pk).update(payment_method=Order.PaymentMethod.TELEGRAM)
        html = self.client.get(reverse('order_status', args=[order.pk])).content.decode()
        self.assertIsNotNone(link_in(html))
        self.assertNotIn('data-open-chat', html)


@override_settings(TELEGRAM_PAY_ADMIN=ADMIN)
class BackToTheOrderTests(CheckoutCase):
    """Back from Telegram or a gateway is the checkout, which shows the order (§17 #409).

    A browser skips, on Back, a page that went on by itself; the order's page
    does when it opens the chat, and a gateway's redirect never was a page.
    """

    def back(self):
        """The checkout, asked for again with the basket now empty."""
        return self.client.get(reverse('checkout'))

    def test_back_from_either_lands_on_the_order(self):
        for method in ('telegram', 'click'):
            with self.subTest(method=method):
                Order.objects.all().delete()
                self.cart.status = True
                self.cart.save(update_fields=['status'])
                self.post(payment_method=method)
                order = Order.objects.get()
                response = self.back()
                self.assertRedirects(response, reverse('order_detail', args=[order.pk]),
                                     fetch_redirect_response=False)
                # And nothing says the basket is empty.
                self.assertNotIn('Savat boʻsh.', said(self.client.get(response['Location'])))

    def test_once_the_order_is_settled_the_basket_is_simply_empty(self):
        self.post(payment_method='telegram')
        order = Order.objects.get()
        for status in (Order.Status.PAID, Order.Status.CANCELLED):
            with self.subTest(status=status):
                Order.objects.filter(pk=order.pk).update(status=status)
                response = self.back()
                self.assertRedirects(response, reverse('cart'), fetch_redirect_response=False)
        self.assertNotIn(views.PLACED_KEY, self.client.session)

    def test_a_basket_filled_again_is_a_new_checkout(self):
        self.post(payment_method='telegram')
        self.cart = self.cart.__class__.objects.create(user=self.user, status=True)
        self.cart.cart_items.create(variant=self.shirt_m, quantity=1,
                                    price_stat=self.shirt_m.price)
        self.assertEqual(self.back().status_code, 200)

    def test_only_the_customers_own_order_is_followed(self):
        other = make_user('boshqa', '+998901220009')
        theirs = order_of(other, (self.shirt_m, 1))
        self.cart.cart_items.all().delete()
        session = self.client.session
        session[views.PLACED_KEY] = theirs.pk
        session.save()
        self.assertRedirects(self.back(), reverse('cart'), fetch_redirect_response=False)

    def test_the_checkout_restored_from_the_browsers_cache_asks_again(self):
        """Otherwise Back could show the filled form of an order already placed."""
        body = CHECKOUT_JS.read_text(encoding='utf-8')
        self.assertIn("window.addEventListener('pageshow'", body)
        self.assertIn('if (event.persisted && placing) window.location.reload();', body)
        # Only after the order button: Back from any other page keeps what was typed.
        self.assertIn('if (!event.submitter || !event.submitter.name) placing = true;', body)


class OrderPagesPayButtonTests(CheckoutCase):
    """The order's two pages carry the pay button while, and only while, it waits."""

    def test_both_pages_post_a_gateways_order_to_be_paid(self):
        order = order_of(self.user, (self.shirt_m, 1))
        for name in ('order_detail', 'order_status'):
            with self.subTest(page=name):
                html = self.client.get(reverse(name, args=[order.pk])).content.decode()
                form = html.split('action="%s"' % reverse('payment_start', args=[order.pk]),
                                  1)[1].split('</form>', 1)[0]
                self.assertIn('csrfmiddlewaretoken', form)
                self.assertIn('Toʻlovni yakunlash', form)

    def test_a_paid_order_has_no_button(self):
        order = order_of(self.user, (self.shirt_m, 1), status=Order.Status.PAID)
        for name in ('order_detail', 'order_status'):
            with self.subTest(page=name):
                html = self.client.get(reverse(name, args=[order.pk])).content.decode()
                self.assertNotIn(reverse('payment_start', args=[order.pk]), html)
                self.assertIsNone(link_in(html))

    def test_the_button_goes_straight_to_click(self):
        order = order_of(self.user, (self.shirt_m, 1))
        response = self.client.post(reverse('payment_start', args=[order.pk]))
        sent_to_click(self, response, order)

    def test_an_order_paid_meanwhile_is_not_sent_to_pay_again(self):
        order = order_of(self.user, (self.shirt_m, 1), status=Order.Status.PAID)
        response = self.client.post(reverse('payment_start', args=[order.pk]))
        self.assertRedirects(response, reverse('order_status', args=[order.pk]),
                             fetch_redirect_response=False)


class OldAddressTests(CheckoutCase):
    """`/payment/<id>/` went; its name resolves and leads to the order (§4)."""

    def test_it_leads_to_the_orders_page(self):
        order = order_of(self.user, (self.shirt_m, 1))
        response = self.client.get(reverse('payment', args=[order.pk]), follow=True)
        self.assertEqual(response.redirect_chain,
                         [(reverse('order_detail', args=[order.pk]), 302)])
        self.assertEqual(response.status_code, 200)

    def test_signed_out_it_asks_to_sign_in_and_comes_back_to_the_order(self):
        order = order_of(self.user, (self.shirt_m, 1))
        self.client.logout()
        response = self.client.get(reverse('payment', args=[order.pk]), follow=True)
        last = response.redirect_chain[-1][0]
        self.assertIn('/login/', last)
        self.assertIn('next=%s' % reverse('order_detail', args=[order.pk]), last)

    def test_the_page_itself_is_gone(self):
        with self.assertRaises(TemplateDoesNotExist):
            get_template('payment/payment.html')


class OpenChatScriptTests(SimpleTestCase):
    """The few lines that open the chat, read as text."""

    def test_it_opens_the_marked_link_in_this_tab_first_thing(self):
        body = MAIN_JS.read_text(encoding='utf-8')
        self.assertIn("document.querySelector('a[data-open-chat]')", body)
        self.assertIn('window.location.assign(link.href)', body)
        # In this tab: a new one is what a browser blocks when no tap asked for it.
        self.assertNotIn('window.open(', body)
        ready = body.split("document.addEventListener('DOMContentLoaded'", 1)[1]
        self.assertLess(ready.index('openChat();'), ready.index('sweepBrokenImages();'))


# ------------------------------------------------------------ part F: "Siz uchun"

def shelf_of(html):
    """The "Siz uchun" section of the home page, from its opening tag to its end."""
    return html.split('data-shelf ', 1)[1].split('</section>', 1)[0]


class ForYouShelfTests(TempMedia, TestCase):
    """The home page's "Siz uchun": twelve of the most liked, in a row that scrolls."""

    def setUp(self):
        super().setUp()
        # Fourteen liked designs, the most liked made last, and one nobody
        # liked; each with a small photograph, so the cards carry `sizes`.
        self.liked = []
        for n in range(1, 15):
            product, _variant = make_product('Dizayn %02d' % n)
            Product.objects.filter(pk=product.pk).update(likes_count=n)
            with_photo(product, 400, 500)
            self.liked.append(product)
        self.unliked, _variant = make_product('Hech kim')
        with_photo(self.unliked, 400, 500)

    def page(self, language='uz'):
        with translation.override(language):
            return self.client.get(reverse('home')).content.decode()

    def test_twelve_of_the_most_liked_most_liked_first(self):
        shelf = shelf_of(self.page())
        names = re.findall(r'<span class="card__name">([^<]*)</span>', shelf)
        self.assertEqual(names, ['Dizayn %02d' % n for n in range(14, 2, -1)])

    def test_what_fills_it_is_unchanged_a_design_nobody_liked_is_not_on_it(self):
        self.assertNotIn('Hech kim', shelf_of(self.page()))
        Product.objects.filter(pk__in=[p.pk for p in self.liked]).update(likes_count=0)
        self.assertNotIn('data-shelf ', self.page())

    def test_it_is_a_list_that_scrolls_each_card_an_item(self):
        shelf = shelf_of(self.page())
        self.assertIn('<ul class="shelf__track" id="shelf-for-you-track" data-shelf-track>', shelf)
        self.assertEqual(shelf.count('<li class="shelf__item">'), 12)
        self.assertNotIn('grid-products', shelf)
        self.assertIn('aria-labelledby="shelf-for-you"', self.page())
        self.assertIn('<h2 class="h2" id="shelf-for-you">Siz uchun</h2>', shelf)

    def test_its_photographs_ask_for_the_width_the_shelf_draws_them_at(self):
        shelf = shelf_of(self.page())
        sizes = re.findall(r'sizes="([^"]*)"', shelf)
        self.assertEqual(len(sizes), 12)
        self.assertEqual(set(sizes), {'(min-width: 1280px) 260px, (min-width: 860px) 21vw, '
                                      '(min-width: 560px) 37vw, 57vw'})
        # Below the first screen: every one waits to be scrolled to.
        self.assertEqual(shelf.count('loading="lazy"'), 12)

    def test_the_grid_above_it_keeps_the_grids_widths(self):
        html = self.page()
        newest = html.split('Yangi kelganlar', 1)[1].split('</section>', 1)[0]
        self.assertIn('(min-width: 720px) 31vw, 46vw', newest)

    def test_two_arrows_named_in_each_language_that_move_the_track(self):
        for language in ('uz', 'ru', 'en'):
            with self.subTest(language=language):
                shelf = shelf_of(self.page(language))
                with translation.override(language):
                    names = (_('Oldingi dizaynlar'), _('Keyingi dizaynlar'))
                if language != 'uz':
                    self.assertNotIn(names[0], ('', 'Oldingi dizaynlar'))
                for name, mark in zip(names, ('data-shelf-prev', 'data-shelf-next')):
                    button = shelf.split(mark, 1)[1].split('</button>', 1)[0]
                    self.assertIn('<span class="sr-only">%s</span>' % name, button)
                    self.assertIn('aria-controls="shelf-for-you-track"', button)
                # Not hidden by an attribute: CSS shows them, so the heading's
                # height is settled before the first paint.
                self.assertNotRegex(shelf, r'<button[^>]*data-shelf-(prev|next)[^>]*hidden')


class ForYouShelfAssetTests(SimpleTestCase):
    """The stylesheet and the script behind the shelf, read as text."""

    def rule(self, selector):
        css = COMPONENTS_CSS.read_text(encoding='utf-8')
        return css.split(selector + ' {', 1)[1].split('}', 1)[0]

    def test_the_track_scrolls_and_snaps_without_a_script(self):
        track = self.rule('.shelf__track')
        for declaration in ('overflow-x: auto', 'scroll-snap-type: x mandatory',
                            'grid-auto-flow: column', 'grid-auto-columns: 62%'):
            self.assertIn(declaration, track)
        self.assertIn('scroll-snap-align: start', self.rule('.shelf__item'))

    def test_the_arrows_are_for_a_pointer_and_shown_before_the_first_paint(self):
        css = COMPONENTS_CSS.read_text(encoding='utf-8')
        self.assertIn('display: none', self.rule('.shelf__arrows'))
        self.assertIn('@media (hover: hover) and (pointer: fine) {\n'
                      '  html.js .shelf__arrows { display: flex; }', css)
        self.assertIn('.shelf__arrows.is-idle { visibility: hidden; }', css)

    def test_the_script_drives_every_shelf_once_the_page_is_read(self):
        body = MAIN_JS.read_text(encoding='utf-8')
        self.assertIn("$$('[data-shelf]').forEach", body)
        self.assertIn("arrows.classList.toggle('is-idle', end <= 1);", body)
        ready = body.split("document.addEventListener('DOMContentLoaded'", 1)[1]
        self.assertIn('initShelves();', ready)
