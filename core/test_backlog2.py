"""What the walk through every page after Phase 24 found (§18 #78, #89, #90, #91).

The home page's heading ran under the dealt cards between 860 and 1280 px; the
bar of five's Russian words met at 360 px; the checkout's sheets closed with a
36 px button; and nothing told a customer that an unpaid order is cancelled.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import translation

from cart.models import Cart, CartItem
from payment import services
from payment.models import Order

from .test_phase4 import make_product
from .test_phase6 import make_user

CSS = Path(settings.BASE_DIR) / 'static' / 'css'


def sheet(name):
    """A stylesheet with its comments taken out, so prose cannot match."""
    return re.sub(r'/\*.*?\*/', '', (CSS / name).read_text(encoding='utf-8'), flags=re.S)


class HeroWidthTests(SimpleTestCase):
    """The heading's longest word fits its column at every width (§18 #90)."""

    def test_the_columns_share_the_width_until_1280(self):
        css = sheet('pages.css')
        shared = '.hero__grid { grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);'
        fixed = '.hero__grid { grid-template-columns: minmax(0, 1fr) var(--hero-side); }'
        self.assertIn(shared, css)
        self.assertEqual(css.count('var(--hero-side)'), 1)
        self.assertRegex(css.split(fixed, 1)[0], r'@media \(min-width: 1280px\) \{\s*$')

    def test_the_heading_follows_the_window_beside_the_cards(self):
        self.assertIn('.hero__title { font-size: clamp(var(--fs-4xl), 8.2vw, var(--fs-7xl)); }',
                      sheet('pages.css'))

    def test_the_cards_keep_their_shape_in_a_narrower_column(self):
        self.assertIn('.hero__deck { display: block; position: relative; aspect-ratio: var(--ar-deck); }',
                      sheet('pages.css'))
        self.assertIn('--ar-deck:', sheet('tokens.css'))


class TabBarWordsTests(TestCase):
    """Five words share 360 px, so none of them may be long (§18 #91)."""

    def test_no_word_is_longer_than_eleven_letters(self):
        for language in ('uz', 'ru', 'en'):
            with translation.override(language):
                html = self.client.get(reverse('home')).content.decode()
            bar = html.split('class="tabbar"', 1)[1].split('</nav>', 1)[0]
            words = [w for w in re.findall(r'<span>([^<]+)</span>', bar)]
            self.assertEqual(len(words), 5)
            for word in words:
                with self.subTest(language=language, word=word):
                    self.assertLessEqual(len(word), 11)


class SheetCloseTests(SimpleTestCase):
    """The checkout's sheets close with a button a thumb can hit (§18 #89)."""

    def test_the_close_button_is_a_tap_target(self):
        rule = sheet('components.css').split('.picker-drawer__close {', 1)[1].split('}', 1)[0]
        self.assertIn('min-width: var(--tap)', rule)
        self.assertIn('min-height: var(--tap)', rule)


class UnpaidNoticeTests(TestCase):
    """An unpaid order's page says how long it is kept (§18 #78, §17 #373)."""

    def setUp(self):
        self.user = make_user()
        _product, variant = make_product('Kutayotgan')
        cart = Cart.objects.create(user=self.user, status=False)
        CartItem.objects.create(cart=cart, variant=variant, quantity=1, price_stat=variant.price)
        self.order = Order.objects.create(
            user=self.user, cart=cart, phone=self.user.phone, address='Amir Temur 1',
            total_price=variant.price, status=Order.Status.PAYING,
            payment_method=Order.PaymentMethod.TELEGRAM)
        self.client.force_login(self.user)

    def page(self, language='uz'):
        with translation.override(language):
            return self.client.get(reverse('order_detail', args=[self.order.pk])).content.decode()

    def test_it_says_the_days_the_nightly_run_goes_by(self):
        days = services.UNPAID_ORDER_DAYS
        said = {'uz': 'Toʻlanmagan buyurtma %d kundan keyin oʻz-oʻzidan bekor qilinadi.' % days,
                'ru': 'Неоплаченный заказ автоматически отменяется через %d дня.' % days,
                'en': 'An unpaid order is cancelled automatically after %d days.' % days}
        for language, line in said.items():
            with self.subTest(language=language):
                self.assertIn(line, self.page(language))

    def test_a_paid_order_does_not_say_it(self):
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.PAID)
        self.assertNotIn('oʻz-oʻzidan bekor qilinadi', self.page())
