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

Part C: the size guide is drawn by the site from the charts' rows: a drawing
of the shirt with the measures numbered on it and no words in it, one table,
then the table for choosing a size, every word in the page's language. No
picture; a chart with no rows shows nowhere; the panel fills rows in
(§17 #400, §9 Phase 23 items 14-18).

Parts A and B: the owner's returns policy is a document of its own at
`/qaytarish/`, and the old rules are rewritten to it everywhere; a customer
asks to return or exchange part of a delivered order on the site, staff
answer in the panel, the customer reads the answer under the order, and the
shop hears of it on Telegram (§17 #398, #399, §9 Phase 23 items 1-13).

Each class is one of those, written as what a customer, or the owner, sees.
"""
import re
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from django.utils import timezone, translation
from django.utils.translation import gettext as _

from cart.models import Cart, CartItem
from core import legal, telegram
from payment import returns, services, views
from payment.management.commands.prune_return_requests import cutoff
from payment.models import Order, ReturnImage, ReturnLine, ReturnRequest
from panel import reference
from product import size_charts
from product.models import Colour, Product, Size, SizeChart, SizeChartRow, Variant

from .test_phase6 import make_user
from .test_backlog import TempMedia
from .test_phase4 import make_product
from .test_phase7 import make_staff
from .test_phase9 import with_photo
from .test_phase12 import photo
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


# ------------------------------------------------------- part C: the size guide

def guide_of(html):
    """The page's article: the guide and the words around it, without the chrome."""
    return html.split('<article', 1)[1].split('</article>', 1)[0]


class DrawnGuideTests(TestCase):
    """`/olcham-jadvali/` drawn from the rows: one drawing, one table, said once."""

    def setUp(self):
        self.chart = SizeChart.objects.get(name=size_charts.NAME)

    def page(self, language='uz'):
        return self.client.get('/%s/olcham-jadvali/' % language)

    def test_there_is_no_picture_only_the_drawing(self):
        guide = guide_of(self.page().content.decode())
        self.assertNotIn('<img', guide)
        self.assertEqual(guide.count('<svg class="tee"'), 1)
        self.assertIsNone(finders.find('img/size_guide.png'))
        self.assertFalse((Path(settings.BASE_DIR) / 'docs' / 'brand' / 'size-guide.html').exists())

    def test_the_drawing_numbers_the_four_measures_and_has_no_words(self):
        drawing = guide_of(self.page().content.decode()).split('<svg class="tee"', 1)[1]
        drawing = drawing.split('</svg>', 1)[0]
        self.assertEqual(re.findall(r'<text[^>]*>([^<]*)</text>', drawing), ['1', '2', '3', '4'])
        self.assertIn('aria-hidden="true"', drawing.split('>', 1)[0])

    def test_each_heading_carries_the_number_it_has_on_the_drawing(self):
        guide = guide_of(self.page().content.decode())
        head = guide.split('<thead>', 1)[1].split('</thead>', 1)[0]
        marks = re.findall(r'<span class="sizeguide__mark" aria-hidden="true">(\d)</span>([^<]*)</th>', head)
        self.assertEqual(marks, [('1', 'Koʻkrak aylanasi, sm'), ('2', 'Yelka, sm'),
                                 ('3', 'Yeng, sm'), ('4', 'Uzunlik, sm')])

    def test_each_figure_is_said_once(self):
        guide = guide_of(self.page().content.decode())
        for size, (chest, length, shoulder, sleeve) in size_charts.MEASURES.items():
            with self.subTest(size=size):
                row = re.search(r'<th scope="row">%s</th>(.*?)</tr>' % size, guide, re.S).group(1)
                self.assertEqual(re.findall(r'>([\d.]+)</td>', row),
                                 [str(int(float(v))) for v in (chest, shoulder, sleeve, length)])
        # The chest of the largest size, which no other table on the page has.
        self.assertEqual(guide.count('>126<'), 1)

    def test_a_russian_or_english_page_shows_no_uzbek(self):
        self.chart.name_ru, self.chart.name_en = 'Футболка', 'T-shirt'
        self.chart.save()
        for language in ('ru', 'en'):
            with self.subTest(language=language):
                guide = guide_of(self.page(language).content.decode())
                # The letter every Uzbek word here carries, and Latin Uzbek that has none.
                self.assertNotIn('\u02bb', guide)
                for word in ('Kiyim', 'Oʻlcham', 'Koʻkrak', 'Uzunlik', 'santimetrda'):
                    self.assertNotIn(word, guide)

    def test_a_chart_with_no_rows_is_not_shown(self):
        SizeChart.objects.create(name='Longsliv', name_ru='Лонгслив')
        guide = guide_of(self.page().content.decode())
        self.assertNotIn('Longsliv', guide)
        # One chart shown, so no chart's own name is a heading.
        self.assertIn('Kiyim oʻlchamlari', guide)

    def test_with_no_rows_anywhere_there_is_no_guide_and_no_link_to_one(self):
        SizeChartRow.objects.all().delete()
        self.assertEqual(self.page().status_code, 404)
        home = self.client.get(reverse('home')).content.decode()
        self.assertNotIn(reverse('size_guide'), home)


class ProductGuideTests(TestCase):
    """The product page's size viewer: its own chart, drawn the same way."""

    def setUp(self):
        self.chart = SizeChart.objects.get(name=size_charts.NAME)
        self.empty = SizeChart.objects.create(name='Longsliv')

    def page(self, chart):
        product, _variant = make_product('Kiyim %s' % chart.pk, size_chart=chart)
        return self.client.get(reverse('item', kwargs={'slug': product.slug})).content.decode()

    def test_its_own_chart_drawn_as_the_guide_page_draws_it(self):
        html = self.page(self.chart)
        self.assertIn('data-size-guide', html)
        block = html.split('data-sizeguide-content hidden>', 1)[1].split('{# The anchor', 1)[0]
        self.assertIn('<svg class="tee"', block)
        self.assertEqual(block.count('<table class="table table--keep sizeguide__table sizeguide__measures">'), 1)
        self.assertIn('Oʻlchamni tanlash', block)
        self.assertNotIn('<img', block)

    def test_a_product_whose_chart_has_no_rows_offers_no_guide(self):
        html = self.page(self.empty)
        self.assertNotIn('data-size-guide', html)
        self.assertNotIn('data-sizeguide-content', html)

    def test_a_product_with_no_chart_offers_no_guide(self):
        product, _variant = make_product('Jadvalsiz')
        html = self.client.get(reverse('item', kwargs={'slug': product.slug})).content.decode()
        self.assertNotIn('data-sizeguide-content', html)


class PanelChartTests(TestCase):
    """The owner fills a chart in from its card in "Oʻlcham jadvallari"."""

    def setUp(self):
        self.client.force_login(make_staff('jadval', '+998901230099'))
        self.chart = SizeChart.objects.create(name='Longsliv')
        self.sizes = {size.size: size for size in Size.objects.all()}

    def save(self, **boxes):
        """Post the chart's form with ``boxes``, named as the form names them."""
        data = {}
        for name, value in boxes.items():
            field, label = name.rsplit('_', 1)
            data['%s-%d' % (field, self.sizes[label].pk)] = value
        return self.client.post(reverse('panel_chart_rows', args=[self.chart.pk]), data, follow=True)

    def said(self, response):
        return [str(m) for m in response.context['messages']]

    def rows(self):
        return [(r.size.size, str(r.chest_cm), r.shoulder_cm and str(r.shoulder_cm),
                 r.sleeve_cm and str(r.sleeve_cm), str(r.length_cm))
                for r in self.chart.rows.select_related('size').order_by('order')]

    def test_the_card_has_a_line_for_every_size_and_no_picture(self):
        html = self.client.get(reverse('panel_settings')).content.decode()
        card = html.split('id="jadvallar"', 1)[1].split('id="olchamlar"', 1)[0]
        self.assertNotIn('type="file"', card)
        self.assertNotIn('<img', card)
        self.assertIn('Qatorlari yoʻq: saytda koʻrinmaydi.', card)
        for label, size in self.sizes.items():
            self.assertIn('name="chest-%d"' % size.pk, card)
        # The shop's chart shows its own figures in its boxes.
        shop = SizeChart.objects.get(name=size_charts.NAME)
        self.assertIn('name="chest-%d" value="110"' % self.sizes['XS'].pk, card)
        self.assertIn('action="%s"' % reverse('panel_chart_rows', args=[shop.pk]), card)

    def test_rows_are_saved_and_shown_on_the_guide(self):
        response = self.save(chest_M='130', shoulder_M='64,5', sleeve_M='60', length_M='72',
                             chest_L='134', length_L='74')
        self.assertEqual(self.said(response), ['Jadval saqlandi.'])
        self.assertEqual(self.rows(), [('M', '130.0', '64.5', '60.0', '72.0'),
                                       ('L', '134.0', None, None, '74.0')])
        html = self.client.get(reverse('size_guide')).content.decode()
        self.assertIn('>Longsliv</h2>', html)
        # A half in the page's own way of writing one.
        self.assertIn('>64,5</td>', html)

    def test_emptying_a_line_removes_its_row(self):
        self.save(chest_M='130', length_M='72', chest_L='134', length_L='74')
        self.save(chest_L='134', length_L='74')
        self.assertEqual([row[0] for row in self.rows()], ['L'])

    def test_a_line_without_its_chest_or_length_saves_nothing(self):
        self.save(chest_M='130', length_M='72')
        response = self.save(chest_M='131', length_M='72', chest_L='134')
        self.assertEqual(self.said(response), ['L: koʻkrak aylanasi va uzunlik kerak.'])
        # Nothing at all: not even the line that was right.
        self.assertEqual(self.rows(), [('M', '130.0', None, None, '72.0')])

    def test_what_is_not_a_measure_is_refused(self):
        for typed in ('abc', '0', '1000', '-5', 'NaN', 'Infinity'):
            with self.subTest(typed=typed):
                response = self.save(chest_M=typed, length_M='72')
                self.assertEqual(self.said(response),
                                 ['M: oʻlchovni santimetrda, 1 dan 999,9 gacha son bilan yozing.'])
                self.assertEqual(self.rows(), [])

    def test_the_names_in_three_languages_are_edited_on_the_card(self):
        reference.set_field('chart', self.chart.pk, 'name_ru', 'Лонгслив')
        reference.set_field('chart', self.chart.pk, 'name_en', 'Longsleeve')
        self.chart.refresh_from_db()
        self.assertEqual((self.chart.name_ru, self.chart.name_en), ('Лонгслив', 'Longsleeve'))

    def test_a_chart_is_made_from_a_name(self):
        self.client.post(reverse('panel_chart_new'), {'name': 'Xudi'})
        self.assertTrue(SizeChart.objects.filter(name='Xudi', image='').exists()
                        or SizeChart.objects.filter(name='Xudi', image__isnull=True).exists())

    def test_a_customer_cannot_save_a_chart(self):
        self.client.force_login(make_user('mijoz', '+998901230098'))
        response = self.client.post(reverse('panel_chart_rows', args=[self.chart.pk]),
                                    {'chest-%d' % self.sizes['M'].pk: '130'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.rows(), [])


# ------------------------------------------------- part A: the returns policy

class ReturnsPolicyTests(TestCase):
    """`/qaytarish/`: the owner's document, in three languages (§17 #398)."""

    def page(self, language='uz'):
        return self.client.get('/%s/qaytarish/' % language).content.decode()

    def test_it_is_a_fourth_legal_document_in_every_language(self):
        for language, title in (('uz', 'Qaytarish va almashtirish siyosati'),
                                ('ru', 'Политика возврата и обмена'),
                                ('en', 'Returns and exchange policy')):
            with self.subTest(language=language):
                response = self.client.get('/%s/qaytarish/' % language)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'legal/returns.%s.html' % language)
                self.assertIn('<h1 class="h1">%s</h1>' % title, response.content.decode())
                self.assertIn('data-version="1.0"', response.content.decode())

    def test_there_is_no_balance_in_any_language(self):
        """The document's "GRAPHIX balansi" was a mistake: the owner refunds (§17 #398)."""
        for language, word in (('uz', 'balans'), ('ru', 'баланс'), ('en', 'balance')):
            with self.subTest(language=language):
                self.assertNotIn(word, self.page(language).lower())

    def test_the_ten_days_are_read_from_core_legal(self):
        with mock.patch.object(legal, 'EXCHANGE_DAYS', 12):
            html = self.page()
        self.assertIn('<strong>12 kun ichida</strong>', html)
        self.assertIn('12 kunlik oddiy almashtirish muddati', html)

    def test_the_owners_typography_is_put_right(self):
        body = (Path(settings.BASE_DIR) / 'templates' / 'legal' /
                'returns.uz.html').read_text(encoding='utf-8')
        self.assertNotIn('‘', body)
        self.assertIn('isteʼmolchi', body)
        self.assertIn('maʼlumot', body)

    def test_the_two_ways_to_apply_are_links(self):
        html = self.page()
        apply = html.split('id="apply"', 1)[1].split('</section>', 1)[0]
        self.assertIn('href="%s"' % reverse('return_request'), apply)
        self.assertIn('href="https://t.me/%s"' % legal.SELLER['telegram'], apply)

    def test_it_is_linked_from_the_footer_the_delivery_page_and_the_terms(self):
        policy = reverse('returns')
        self.assertIn('href="%s"' % policy, self.client.get(reverse('home')).content.decode())
        for name in ('delivery', 'terms'):
            with self.subTest(page=name):
                self.assertIn('href="%s"' % policy, self.client.get(reverse(name)).content.decode())

    def test_it_is_in_the_sitemap(self):
        from core import sitemaps
        self.assertIn('returns', sitemaps.StaticViewSitemap().items())


class OldRulesRewrittenTests(TestCase):
    """The terms and the delivery page say what the policy says (§9 Phase 23 item 4)."""

    KEPT = {'uz': 'ushlab qolinadi', 'ru': 'удерж', 'en': 'is kept from'}

    def test_nothing_is_kept_from_a_parcel_that_comes_back(self):
        for language, kept in self.KEPT.items():
            for path in ('terms', 'yetkazib-berish'):
                with self.subTest(language=language, page=path):
                    html = self.client.get('/%s/%s/' % (language, path)).content.decode()
                    self.assertNotIn(kept, html)

    def test_the_exchange_is_free_and_the_new_size_is_sent_by_the_shop(self):
        terms = self.client.get('/uz/terms/').content.decode()
        returns_section = terms.split('id="returns"', 1)[1].split('</section>', 1)[0]
        self.assertIn('bepul almashtiriladi', returns_section)
        self.assertIn('yangi mahsulotni yetkazib berish xarajatini Sotuvchi qoplaydi',
                      returns_section)
        self.assertIn('href="%s"' % reverse('return_request'), returns_section)
        delivery = self.client.get('/uz/yetkazib-berish/').content.decode()
        self.assertIn('bepul almashtiramiz', delivery)


# ---------------------------------------- part B: asking to return or exchange

def shirt_in_sizes(name='Qaytariladigan'):
    """A product made in S, M and L; the three variants, by label."""
    product = Product.objects.create(name=name)
    colour = Colour.objects.create(colour='Qora %s' % name)
    variants = {}
    for label in ('S', 'M', 'L'):
        size = Size.objects.filter(size=label).first() or Size.objects.create(size=label)
        variants[label] = Variant.objects.create(product=product, size=size, colour=colour,
                                                 price=149000, available=True, stock=5)
    return product, variants


def delivered(user, *lines, status=Order.Status.DONE):
    """An order of ``lines``, each ``(variant, quantity)``, in ``status``."""
    cart = Cart.objects.create(user=user, status=False)
    for variant, quantity in lines:
        CartItem.objects.create(cart=cart, variant=variant, quantity=quantity,
                                price_stat=variant.price)
    return Order.objects.create(user=user, cart=cart, phone=user.phone, address='Amir Temur 1',
                                total_price=149000, status=status)


class ReturnCase(TempMedia, TestCase):
    """A customer with one delivered order: two shirts in S."""

    def setUp(self):
        super().setUp()
        # The hourly limit is counted by user id, and SQLite gives a rolled-back
        # id out again: without this, one test's sends count in the next.
        cache.clear()
        self.user = make_user('qaytaruvchi', '+998901230055')
        self.client.force_login(self.user)
        self.product, self.v = shirt_in_sizes()
        self.order = delivered(self.user, (self.v['S'], 2))
        self.line = self.order.cart.cart_items.get()

    def form(self, **over):
        data = {'order': self.order.pk, 'kind': 'exchange', 'reason': 'size',
                'explanation': 'S kichik keldi.', 'phone': '+998 90 123 00 55',
                'qty-%d' % self.line.pk: '1', 'size-%d' % self.line.pk: str(self.v['M'].size_id)}
        data.update(over)
        return {k: v for k, v in data.items() if v is not None}

    def send(self, photos=(), **over):
        data = self.form(**over)
        if photos:
            data['photos'] = list(photos)
        return self.client.post(reverse('return_request'), data)

    def said(self, response):
        return [str(m) for m in response.context['messages']]


class ReturnRequestPageTests(ReturnCase):
    """The page a customer asks on, and what it refuses."""

    def test_signed_out_it_asks_to_sign_in(self):
        self.client.logout()
        response = self.client.get(reverse('return_request'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_with_one_delivered_order_the_form_is_for_it(self):
        html = self.client.get(reverse('return_request')).content.decode()
        self.assertIn('name="order" value="%d"' % self.order.pk, html)
        self.assertIn('name="qty-%d"' % self.line.pk, html)
        sizes = html.split('name="size-%d"' % self.line.pk, 1)[1].split('</select>', 1)[0]
        self.assertEqual(re.findall(r'>(\w+)</option>', sizes), ['S', 'M', 'L'])
        self.assertIn('value="90 123 00 55"', html)
        # The kind and the reason are radios that work without a script.
        self.assertEqual(html.count('name="kind"'), 2)
        self.assertEqual(html.count('name="reason"'), 5)

    def test_with_several_the_customer_picks_one_first(self):
        other = delivered(self.user, (self.v['L'], 1))
        delivered(self.user, (self.v['M'], 1), status=Order.Status.PAYING)
        html = self.client.get(reverse('return_request')).content.decode()
        self.assertNotIn('name="order"', html)
        self.assertEqual(re.findall(r'href="\?order=(\d+)"', html),
                         [str(other.pk), str(self.order.pk)])
        self.assertIn('name="order" value="%d"' % other.pk,
                      self.client.get(reverse('return_request'), {'order': other.pk}).content.decode())

    def test_an_order_not_delivered_or_not_theirs_is_not_there(self):
        paying = delivered(self.user, (self.v['M'], 1), status=Order.Status.PAYING)
        theirs = delivered(make_user('boshqa', '+998901230056'), (self.v['M'], 1))
        for order in (paying, theirs):
            with self.subTest(order=order.pk):
                response = self.client.get(reverse('return_request'), {'order': order.pk})
                self.assertEqual(response.status_code, 404)

    def test_with_no_delivered_order_it_says_so(self):
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.ON_THE_WAY)
        html = self.client.get(reverse('return_request')).content.decode()
        self.assertIn('Sizda hozircha bunday buyurtma yoʻq.', html)
        self.assertNotIn('name="kind"', html)

    def test_an_exchange_is_sent(self):
        with mock.patch.object(telegram, 'deliver') as sent, \
                self.captureOnCommitCallbacks(execute=True):
            response = self.send()
        self.assertRedirects(response, reverse('order_detail', args=[self.order.pk]) + '#qaytarish',
                             fetch_redirect_response=False)
        request = ReturnRequest.objects.get()
        self.assertEqual((request.kind, request.reason, request.status, request.phone),
                         ('exchange', 'size', 'new', '+998 90 123 00 55'))
        line = request.lines.get()
        self.assertEqual((line.item, line.quantity, line.size_wanted_id),
                         (self.line, 1, self.v['M'].size_id))
        # A request moves no stock.
        self.v['S'].refresh_from_db()
        self.assertEqual(self.v['S'].stock, 5)
        self.assertEqual(sent.call_count, 1)
        self.assertEqual(sent.call_args.args[0], 'return.new')

    def test_a_return_needs_no_size_and_ignores_one(self):
        self.send(kind='return', **{'size-%d' % self.line.pk: ''})
        self.assertIsNone(ReturnLine.objects.get().size_wanted)

    def test_an_exchange_needs_a_size_the_product_is_made_in(self):
        stranger = Size.objects.create(size='XXXL')
        for size in ('', str(stranger.pk)):
            with self.subTest(size=size):
                response = self.send(**{'size-%d' % self.line.pk: size})
                self.assertEqual(self.said(response)[-1],
                                 '«Qaytariladigan»: almashtirish uchun oʻlchamni tanlang.')
        self.assertFalse(ReturnRequest.objects.exists())

    def test_no_more_than_the_order_holds(self):
        response = self.send(**{'qty-%d' % self.line.pk: '3'})
        self.assertEqual(self.said(response), ['«Qaytariladigan»: buyurtmada 2 dona bor.'])
        response = self.send(**{'qty-%d' % self.line.pk: '0'})
        self.assertEqual(self.said(response), ['Qaysi mahsulot va nechta ekanini tanlang.'])
        self.assertFalse(ReturnRequest.objects.exists())

    def test_a_fault_needs_a_photograph_and_the_form_comes_back_as_typed(self):
        response = self.send(reason='fault', explanation='Chok soʻkilgan.')
        self.assertEqual(self.said(response), ['Bu sabab uchun mahsulot rasmini yuboring.'])
        html = response.content.decode()
        self.assertIn('Chok soʻkilgan.</textarea>', html)
        self.assertRegex(html, r'name="reason" value="fault" required\s+checked')
        self.assertIn('value="1" selected', html)
        self.assertFalse(ReturnRequest.objects.exists())

    def test_a_photograph_is_cleaned_and_named_so_nobody_can_guess_it(self):
        self.send(photos=[photo(size=(400, 300))], reason='fault', kind='return')
        image = ReturnImage.objects.get()
        self.assertRegex(image.picture.name, r'^returns/[A-Za-z0-9_-]{24}\.jpg$')
        self.assertTrue(image.picture.storage.exists(image.picture.name))

    def test_no_more_than_four_photographs(self):
        response = self.send(photos=[photo() for _ in range(5)], reason='fault')
        self.assertEqual(self.said(response), ['Koʻpi bilan 4 ta rasm yuborish mumkin.'])
        self.assertFalse(ReturnRequest.objects.exists())

    def test_a_line_in_an_open_request_is_held(self):
        self.send()
        html = self.client.get(reverse('return_request')).content.decode()
        self.assertNotIn('name="qty-%d"' % self.line.pk, html)
        self.assertIn('Bu mahsulot boʻyicha soʻrov koʻrib chiqilmoqda.', html)
        response = self.send()
        self.assertEqual(self.said(response),
                         ['«Qaytariladigan» boʻyicha soʻrov allaqachon koʻrib chiqilmoqda.'])
        # Closed, the line may be asked about again.
        ReturnRequest.objects.update(status=ReturnRequest.Status.REJECTED)
        self.send()
        self.assertEqual(ReturnRequest.objects.count(), 2)

    def test_the_phone_field_has_998_in_it(self):
        """The field is the shared one; its nine digits are a whole number."""
        html = self.client.get(reverse('return_request'), {'order': self.order.pk}).content.decode()
        self.assertIn('<span class="tel__code">+998</span>', html)
        self.assertIn('value="90 123 00 55"', html)
        self.send(phone='90 777 66 55')
        self.assertEqual(ReturnRequest.objects.get().phone, '+998 90 777 66 55')

    def test_past_ten_days_the_form_warns_and_the_request_still_goes(self):
        """Counted from the purchase, as the policy says (§17 #406)."""
        warning = 'kundan koʻp vaqt oʻtdi'
        html = self.client.get(reverse('return_request')).content.decode()
        self.assertNotIn(warning, html)
        Order.objects.filter(pk=self.order.pk).update(
            created_at=timezone.now() - timedelta(days=legal.EXCHANGE_DAYS + 1))
        html = self.client.get(reverse('return_request')).content.decode()
        self.assertIn('Xariddan beri %d %s' % (legal.EXCHANGE_DAYS, warning), html)
        self.assertEqual(self.send().status_code, 302)
        self.assertEqual(ReturnRequest.objects.count(), 1)

    def test_a_refused_form_says_its_photographs_must_be_chosen_again(self):
        lost = 'Tanlangan rasmlar saqlanmadi'
        response = self.send(photos=[photo()], reason='fault', explanation='')
        self.assertIn(lost, response.content.decode())
        response = self.send(reason='fault', explanation='')
        self.assertNotIn(lost, response.content.decode())

    def test_five_a_day(self):
        lines = [delivered(self.user, (self.v['L'], 1)) for _ in range(6)]
        for order in lines[:returns.DAILY]:
            item = order.cart.cart_items.get()
            self.client.post(reverse('return_request'), {
                'order': order.pk, 'kind': 'return', 'reason': 'size', 'explanation': 'x',
                'phone': '+998901230055', 'qty-%d' % item.pk: '1'})
        self.assertEqual(ReturnRequest.objects.count(), returns.DAILY)
        item = lines[-1].cart.cart_items.get()
        response = self.client.post(reverse('return_request'), {
            'order': lines[-1].pk, 'kind': 'return', 'reason': 'size', 'explanation': 'x',
            'phone': '+998901230055', 'qty-%d' % item.pk: '1'})
        self.assertIn('Bir kunda koʻpi bilan 5 ta soʻrov', self.said(response)[-1])
        self.assertEqual(ReturnRequest.objects.count(), returns.DAILY)


class ReturnOnTheOrderPageTests(ReturnCase):
    """The customer's side after sending: the button, the request and the answer."""

    def page(self, order=None):
        return self.client.get(reverse('order_detail', args=[(order or self.order).pk])).content.decode()

    def test_a_delivered_order_offers_the_request_and_every_order_the_policy(self):
        html = self.page()
        self.assertIn('href="%s?order=%d"' % (reverse('return_request'), self.order.pk), html)
        paying = delivered(self.user, (self.v['M'], 1), status=Order.Status.PAYING)
        html = self.page(paying)
        self.assertNotIn(reverse('return_request'), html)
        self.assertIn('href="%s"' % reverse('returns'), html)

    def test_the_request_and_staffs_answer_are_under_the_order(self):
        self.send(photos=[photo()])
        request = ReturnRequest.objects.get()
        returns.answer(request, status='accepted', text='L oʻlchamni yuboramiz.', by=None)
        html = self.page()
        section = html.split('id="qaytarish"', 1)[1].split('</section>', 1)[0]
        self.assertIn('Almashtirish', section)
        self.assertIn('Qabul qilindi', section)
        self.assertIn('S kichik keldi.', section)
        self.assertIn('L oʻlchamni yuboramiz.', section)
        self.assertIn(ReturnImage.objects.get().picture.url, section)

    def test_another_customer_sees_none_of_it(self):
        self.send()
        self.client.force_login(make_user('begona', '+998901230057'))
        self.assertEqual(self.client.get(reverse('order_detail', args=[self.order.pk])).status_code, 404)


class PanelReturnTests(ReturnCase):
    """Staff read and answer a request in "Qaytarishlar"."""

    def setUp(self):
        super().setUp()
        self.send()
        self.request = ReturnRequest.objects.get()
        self.staff = make_staff('qaytarish', '+998901230058')
        self.client.force_login(self.staff)

    def test_the_dashboard_counts_the_new_ones(self):
        response = self.client.get(reverse('panel_dashboard'))
        self.assertEqual(response.context['new_returns'], 1)
        self.assertContains(response, 'href="%s?status=new"' % reverse('panel_returns'))

    def test_the_list_links_each_request(self):
        html = self.client.get(reverse('panel_returns')).content.decode()
        self.assertIn('href="%s"' % reverse('panel_return', args=[self.request.pk]), html)
        self.assertIn(self.order.order_no, html)

    def test_opening_a_new_one_marks_it_as_being_looked_at(self):
        response = self.client.get(reverse('panel_return', args=[self.request.pk]))
        self.assertContains(response, 'S kichik keldi.')
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, ReturnRequest.Status.REVIEWING)

    def test_the_answer_is_saved_with_who_and_when_and_closing_starts_the_year(self):
        url = reverse('panel_return', args=[self.request.pk])
        self.client.post(url, {'status': 'done', 'answer': 'Almashtirildi.'})
        self.request.refresh_from_db()
        self.assertEqual((self.request.status, self.request.answer, self.request.answered_by),
                         ('done', 'Almashtirildi.', self.staff))
        self.assertIsNotNone(self.request.closed_at)
        self.client.post(url, {'status': 'reviewing', 'answer': 'Almashtirildi.'})
        self.request.refresh_from_db()
        self.assertIsNone(self.request.closed_at)

    def test_a_request_moves_no_money_and_no_order(self):
        self.client.post(reverse('panel_return', args=[self.request.pk]),
                         {'status': 'accepted', 'answer': 'Ha.'})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DONE)

    def test_a_request_sent_past_ten_days_is_marked(self):
        request = self.request
        url = reverse('panel_return', args=[request.pk])
        self.assertNotIn('Muddatdan keyin', self.client.get(url).content.decode())
        Order.objects.filter(pk=self.order.pk).update(
            created_at=request.created_at - timedelta(days=legal.EXCHANGE_DAYS + 1))
        self.assertIn('Muddatdan keyin', self.client.get(url).content.decode())

    def test_a_customer_cannot_answer(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('panel_return', args=[self.request.pk]),
                                    {'status': 'done', 'answer': 'Men'})
        self.assertEqual(response.status_code, 403)


class ReturnNotificationTests(ReturnCase):
    """What the shop reads on Telegram (§9 Phase 23 item 11)."""

    def test_it_says_what_why_and_who_with_a_link_to_the_request(self):
        with mock.patch.object(telegram, 'deliver') as sent, \
                self.captureOnCommitCallbacks(execute=True):
            self.send(photos=[photo()], reason='fault', explanation='Chok <b>soʻkilgan</b>.')
        event, text, data = sent.call_args.args[:3]
        request = ReturnRequest.objects.get()
        self.assertEqual(event, 'return.new')
        self.assertIn(self.order.order_no, text)
        self.assertIn('Mahsulotda nuqson bor', text)
        self.assertIn('Qaytariladigan', text)
        self.assertIn('→ M', text)
        self.assertIn('Chok &lt;b&gt;soʻkilgan&lt;/b&gt;.', text)
        self.assertIn('📷 Rasm: 1 ta', text)
        self.assertTrue(data['return']['admin_url'].endswith(
            reverse('panel_return', args=[request.pk])))
        self.assertEqual(data['return']['kind'], 'exchange')

    def test_it_is_in_uzbek_whatever_language_the_customer_wrote_in(self):
        with translation.override('ru'):
            url = reverse('return_request')
        with mock.patch.object(telegram, 'deliver') as sent, \
                self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, self.form(), HTTP_ACCEPT_LANGUAGE='ru')
        text = sent.call_args.args[1]
        self.assertIn('Oʻlcham mos kelmadi', text)
        self.assertIn('almashtirish', text)
        self.assertNotIn('размер', text)

    def test_the_bot_contract_names_the_event(self):
        doc = (Path(settings.BASE_DIR) / 'docs' / 'integrations' /
               'telegram-bot.md').read_text(encoding='utf-8')
        self.assertIn('### `return.new`', doc)


class ReturnRetentionTests(ReturnCase):
    """A closed request is kept a year, then goes with its photographs (§17 #406)."""

    def make(self, status, closed_months_ago=None):
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.DONE)
        request = ReturnRequest.objects.create(
            user=self.user, order=self.order, kind='return', reason='size',
            explanation='x', phone='+998901230055', status=status)
        image = ReturnImage.objects.create(request=request, picture=photo(), order=0)
        if closed_months_ago is not None:
            request.closed_at = timezone.now() - timedelta(days=31 * closed_months_ago)
            request.save(update_fields=['closed_at'])
        return request, image.picture.name

    def test_only_a_request_closed_over_a_year_ago_goes(self):
        old, old_file = self.make('done', 13)
        recent, _ = self.make('rejected', 11)
        open_one, _ = self.make('reviewing')
        ReturnRequest.objects.filter(pk=open_one.pk).update(
            created_at=timezone.now() - timedelta(days=800))
        with self.captureOnCommitCallbacks(execute=True):
            call_command('prune_return_requests', stdout=StringIO())
        self.assertEqual(set(ReturnRequest.objects.values_list('pk', flat=True)),
                         {recent.pk, open_one.pk})
        self.assertFalse(ReturnImage.objects.filter(request=old.pk).exists())
        self.assertFalse(old.images.model.picture.field.storage.exists(old_file))

    def test_a_year_is_counted_in_calendar_months(self):
        now = timezone.now().replace(year=2027, month=3, day=31)
        self.assertEqual((cutoff(now).year, cutoff(now).month, cutoff(now).day), (2026, 3, 31))
        now = now.replace(year=2028, month=2, day=29)
        self.assertEqual((cutoff(now).year, cutoff(now).month, cutoff(now).day), (2027, 2, 28))

    def test_the_privacy_policy_says_so_in_every_language(self):
        for language, words in (('uz', 'soʻrov yopilganidan keyin %d oy'),
                                ('ru', '%d месяцев после закрытия запроса'),
                                ('en', '%d months after the request is closed')):
            with self.subTest(language=language):
                html = self.client.get('/%s/privacy/' % language).content.decode()
                self.assertIn(words % legal.RETURN_KEEP_MONTHS, html)
