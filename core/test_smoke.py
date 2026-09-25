"""Phase 10's smoke matrix: every named URL, for everyone who can ask for it.

Phase 10's Definition of Done asks that "every URL in §6 returns 200 (or the
right redirect) for anonymous, logged-in and staff users". Until now that was
four tests written in Phase 0, against a site that has grown to seventy named
URLs — so the matrix asserted the four pages least likely to break.

Three things make this worth more than seventy assertions of 200:

* **The right redirect, not merely a redirect.** A 302 to anywhere is not a
  pass. Every redirect here names where it must land, because "signed out
  visitor is sent to the login page" and "signed out visitor is sent to the
  home page" are both 302 and only one of them is the site working.
* **Ownership is part of the answer.** A customer opening another customer's
  order must get a 404, and that is a security property (§9 Phase 10 item 5),
  not a page rendering. Asserting it per URL rather than once means a new
  order-scoped page cannot quietly skip the check.
* **Coverage is asserted.** `test_every_named_url_is_accounted_for` compares
  this table against the urlconf, so a page added in a later phase fails the
  suite until somebody writes down what it should answer. A matrix nobody
  updates is a matrix that describes last year's site.

`EXPECT` is read as: an integer is a status code; a pair is a status code and
a fragment its `Location` must contain.
"""
from collections import namedtuple

from django.test import TestCase
from django.urls import get_resolver, reverse
from django.utils import translation

from cart.models import Cart, CartItem
from payment.models import Order
from product.models import Category, ImageP, Review

from .test_phase4 import make_product
from .test_phase6 import make_regions, make_user
from .test_phase7 import make_staff
from .test_phase12 import make_order

#: One row of the matrix. ``kwargs`` names fixture tokens, not values.
Page = namedtuple('Page', 'name kwargs anon user staff')

#: Where an unauthenticated visitor is sent by ``login_required``.
LOGIN = (302, '/uz/login/?next=')
#: Where an already-signed-in visitor is sent away from the auth pages.
ACCOUNT = (302, '/uz/account/')

PAGES = (
    # ---------------------------------------------------------- public pages
    Page('home', {}, 200, 200, 200),
    Page('shop', {}, 200, 200, 200),
    Page('search', {}, 200, 200, 200),
    Page('about', {}, 200, 200, 200),
    Page('contact', {}, 200, 200, 200),
    Page('delivery', {}, 200, 200, 200),
    Page('terms', {}, 200, 200, 200),
    Page('privacy', {}, 200, 200, 200),
    Page('size_guide', {}, 200, 200, 200),
    Page('cart', {}, 200, 200, 200),
    Page('item', {'slug': 'slug'}, 200, 200, 200),
    Page('item_legacy', {'pk': 'product_pk'},
         (301, '/mahsulot/'), (301, '/mahsulot/'), (301, '/mahsulot/')),

    # ------------------------------------------------------ the auth journey
    Page('login', {}, 200, ACCOUNT, ACCOUNT),
    Page('signup', {}, 200, ACCOUNT, ACCOUNT),
    Page('verify_phone', {}, LOGIN, ACCOUNT, ACCOUNT),
    Page('password_reset_request', {}, 200, ACCOUNT, ACCOUNT),
    Page('password_reset_verify', {},
         (302, '/uz/parolni-tiklash/'), ACCOUNT, ACCOUNT),
    Page('password_reset_set', {},
         (302, '/uz/parolni-tiklash/'), ACCOUNT, ACCOUNT),

    # ------------------------------------------------- the customer's own
    Page('account', {}, LOGIN, 200, 200),
    Page('account_orders', {}, LOGIN, 200, 200),
    Page('account_settings', {}, LOGIN, 200, 200),
    Page('liked', {}, LOGIN, 200, 200),
    Page('checkout', {}, LOGIN, 200, 200),

    # Order-scoped, and the order belongs to `user`. Staff must get a 404:
    # being staff is not being the customer, and the panel is where staff
    # read an order (§9 Phase 10 item 5).
    Page('order_detail', {'pk': 'order_pk'}, LOGIN, 200, 404),
    Page('order_status', {'pk': 'order_pk'}, LOGIN, 200, 404),
    Page('payment', {'order_id': 'paying_pk'}, LOGIN, 200, 404),
    Page('review_create', {'order_id': 'order_pk'}, LOGIN, 200, 404),
)

#: POST-only endpoints. A GET is 405, and that is the assertion: a write
#: endpoint that answers GET is a write endpoint somebody can trigger with a
#: link. Where `login_required` wraps the outside, an anonymous GET is sent to
#: the login page before the method is ever looked at - so the two columns
#: differ, and both are correct.
WRITE_ONLY = (
    Page('logout', {}, 405, 405, 405),
    Page('cart_add', {'product_id': 'product_pk'}, 405, 405, 405),
    Page('cart_update', {'item_id': 'item_pk'}, 405, 405, 405),
    Page('cart_remove', {'item_id': 'item_pk'}, 405, 405, 405),
    Page('product_like', {'slug': 'slug'}, 405, 405, 405),
    Page('order_cancel', {'pk': 'order_pk'}, LOGIN, 405, 405),
    Page('payment_start', {'order_id': 'paying_pk'}, LOGIN, 405, 405),
    Page('account_forgot_password', {}, LOGIN, 405, 405),
    Page('cancel_verification', {}, LOGIN, 405, 405),
    Page('expire_verification', {}, LOGIN, 405, 405),
    Page('resend_otp', {}, LOGIN, 405, 405),
    Page('password_reset_resend', {}, 405, 405, 405),
    Page('password_reset_expire', {}, 405, 405, 405),
)

#: The panel. Its guard is the point: a signed-out visitor is sent to the
#: login page, and a signed-in customer gets 403 rather than a second login
#: form (§17 #141). Screens answer 200; the create and edit endpoints are
#: POST-only and answer 405 to staff.
PANEL = (
    Page('panel_dashboard', {}, LOGIN, 403, 200),
    Page('panel_orders', {}, LOGIN, 403, 200),
    Page('panel_order', {'order_no': 'order_no'}, LOGIN, 403, 200),
    Page('panel_products', {}, LOGIN, 403, 200),
    Page('panel_product_new', {}, LOGIN, 403, 200),
    Page('panel_product', {'slug': 'slug'}, LOGIN, 403, 200),
    Page('panel_messages', {}, LOGIN, 403, 200),
    Page('panel_reviews', {}, LOGIN, 403, 200),
    Page('panel_regions', {}, LOGIN, 403, 200),
    Page('panel_settings', {}, LOGIN, 403, 200),
    Page('panel_slides', {}, LOGIN, 403, 200),
    # The style guide is a panel screen that predates the panel. It answered
    # 302 to /admin/login/ for a signed-in customer until Phase 10 gave it the
    # same guard as its neighbours (§17 #268).
    Page('style_guide', {}, LOGIN, 403, 200),

    Page('panel_order_status', {'order_no': 'order_no'}, LOGIN, 403, 405),
    Page('panel_product_inline', {'slug': 'slug'}, LOGIN, 403, 405),
    Page('panel_product_images', {'slug': 'slug'}, LOGIN, 403, 405),
    Page('panel_review_moderate', {'pk': 'review_pk'}, LOGIN, 403, 405),
    Page('panel_message_read', {'pk': 'msg_pk'}, LOGIN, 403, 405),
    Page('panel_lookup_new', {'kind': 'kind'}, LOGIN, 403, 405),
    Page('panel_chart_new', {}, LOGIN, 403, 405),
    Page('panel_size_new', {}, LOGIN, 403, 405),
    Page('panel_slide_new', {}, LOGIN, 403, 405),
    Page('panel_tag_new', {}, LOGIN, 403, 405),
    Page('panel_reference_inline', {'kind': 'kind', 'pk': 'tag_pk'},
         LOGIN, 403, 405),
    Page('panel_reference_delete', {'kind': 'kind', 'pk': 'tag_pk'},
         LOGIN, 403, 405),
)

#: Served to machines, outside i18n_patterns, and with no language of their
#: own. Kept in the matrix so the coverage test can see them, and so a webhook
#: that starts answering GET is noticed here as well as in the phase that
#: mounted it (§12 risk #2).
MACHINE = (
    Page('click_webhook', {}, 405, 405, 405),
    Page('payme_webhook', {}, 405, 405, 405),
    Page('octo_webhook', {}, 405, 405, 405),
    Page('sitemap', {}, 200, 200, 200),
    Page('favicon', {}, (301, '/static/img/favicon.ico'),
         (301, '/static/img/favicon.ico'), (301, '/static/img/favicon.ico')),
    Page('set_language', {}, (302, '/'), (302, '/'), (302, '/')),
)

ALL_PAGES = PAGES + WRITE_ONLY + PANEL + MACHINE


class SmokeMatrix(TestCase):
    """Every named URL, asked for by all three kinds of visitor."""

    def setUp(self):
        self.geo = make_regions()
        self.user = make_user('mijoz', '+998901400001')
        self.staff = make_staff('xodim', '+998901400002')
        self.product, self.variant = make_product('Smoke', stock=5)

        # `order` is delivered, so a review can be written against it.
        # `paying` is awaiting payment, which is the only state the payment
        # pages accept - one fixture cannot be both.
        self.order = make_order(self.user, self.variant, status='done')
        self.paying = make_order(self.user, self.variant, status='paying')
        self.review = Review.objects.create(
            product=self.product, user=self.user, order=self.order,
            rating=5, text='Yaxshi')

        # Both signed-in visitors get a cart, so the checkout answers about
        # the checkout rather than about which fixture happens to have one.
        for who in (self.user, self.staff):
            cart = Cart.objects.create(user=who, status=True)
            CartItem.objects.create(cart=cart, variant=self.variant,
                                    quantity=1, price_stat=self.variant.price)
        self.item = CartItem.objects.filter(cart__user=self.user).first()

    def tokens(self):
        """Fixture values the matrix refers to by name."""
        from core.models import Msg
        from product.models import Tag
        msg = Msg.objects.create(user=self.user, phone_num='+998901400003',
                                 topic='Savol', msg_text='Salom')
        return {
            'slug': self.product.slug,
            'product_pk': self.product.pk,
            'item_pk': self.item.pk,
            'order_pk': self.order.pk,
            'paying_pk': self.paying.pk,
            'order_no': self.order.order_no,
            'review_pk': self.review.pk,
            'msg_pk': msg.pk,
            'tag_pk': Tag.objects.first().pk if Tag.objects.exists() else 1,
            'kind': 'tag',
        }

    def url_for(self, page, tokens):
        kwargs = {k: tokens[v] for k, v in page.kwargs.items()}
        with translation.override('uz'):
            return reverse(page.name, kwargs=kwargs or None)

    def check(self, page, who, expected, tokens):
        self.client.logout()
        if who == 'user':
            self.client.force_login(self.user)
        elif who == 'staff':
            self.client.force_login(self.staff)

        url = self.url_for(page, tokens)
        response = self.client.get(url)
        status = expected[0] if isinstance(expected, tuple) else expected
        self.assertEqual(
            response.status_code, status,
            '%s as %s: %s answered %s, expected %s'
            % (page.name, who, url, response.status_code, status))
        if isinstance(expected, tuple):
            self.assertIn(
                expected[1], response.headers.get('Location', ''),
                '%s as %s: redirected to %r, expected it to contain %r'
                % (page.name, who, response.headers.get('Location', ''),
                   expected[1]))

    def test_the_matrix(self):
        """One subTest per cell, so a failure names the page and the caller."""
        tokens = self.tokens()
        for page in ALL_PAGES:
            for who in ('anon', 'user', 'staff'):
                with self.subTest(page=page.name, who=who):
                    self.check(page, who, getattr(page, who), tokens)

    def test_every_named_url_is_accounted_for(self):
        """A page added later fails this until somebody says what it answers.

        The point of the matrix is that it is complete. Nothing keeps it
        complete except this: the urlconf is the truth, and any name in it
        that is missing here is a page nobody has decided the answer for.
        """
        named = {k for k in get_resolver().reverse_dict.keys()
                 if isinstance(k, str)}
        listed = {page.name for page in ALL_PAGES}
        missing = sorted(named - listed)
        self.assertEqual(
            missing, [],
            '%d named URL(s) are not in the smoke matrix: %s'
            % (len(missing), missing))

    def test_the_matrix_names_nothing_that_no_longer_exists(self):
        """The other direction: a row for a URL that has been deleted is a row
        that passes forever without testing anything.
        """
        named = {k for k in get_resolver().reverse_dict.keys()
                 if isinstance(k, str)}
        stale = sorted({page.name for page in ALL_PAGES} - named)
        self.assertEqual(stale, [], 'stale rows: %s' % stale)

    def test_no_page_is_listed_twice(self):
        """Two rows for one page means one of them is not being read."""
        names = [page.name for page in ALL_PAGES]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        self.assertEqual(duplicates, [], 'listed twice: %s' % duplicates)


class OrderOwnershipTests(TestCase):
    """§9 Phase 10 item 5, on its own rather than as a column in a table.

    The matrix asserts that *staff* cannot open another person's order. This
    asserts the case that actually happens: one customer with the id of
    another customer's order. Being signed in is not being the owner, and a
    404 rather than a 403 is deliberate - a 403 confirms the order exists.
    """

    def setUp(self):
        self.owner = make_user('egasi', '+998901410001')
        self.other = make_user('boshqa', '+998901410002')
        _, variant = make_product('Egalik', stock=3)
        self.order = make_order(self.owner, variant, status='done')
        self.client.force_login(self.other)

    def test_another_customers_order_is_not_found(self):
        for name in ('order_detail', 'order_status'):
            with self.subTest(name=name):
                with translation.override('uz'):
                    url = reverse(name, kwargs={'pk': self.order.pk})
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_another_customers_payment_page_is_not_found(self):
        with translation.override('uz'):
            url = reverse('payment', kwargs={'order_id': self.order.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_another_customers_order_cannot_be_reviewed(self):
        with translation.override('uz'):
            url = reverse('review_create', kwargs={'order_id': self.order.pk})
        self.assertEqual(self.client.get(url).status_code, 404)
