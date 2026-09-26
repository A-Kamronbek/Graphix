"""The payment gateways' pay pages are allowed as form targets.

"Toʻlovga oʻtish" posts to our own `payment_start`, which answers with a 302
to the gateway. Browsers hold every redirect after a form submission to
`form-action`, so under `form-action 'self'` the redirect was refused and a
plain click did nothing; ctrl+click worked only because a new tab is not bound
by the page's policy. Nobody could pay from 25 September, when the policy went
live, until this fix (§17 #298).
"""
from urllib.parse import urlsplit

from django.test import TestCase, override_settings
from django.urls import reverse

from core.middleware import PAY_PAGES
from payment import services
from payment.models import Order

from .test_phase4 import make_product
from .test_phase6 import make_user
from .test_phase12 import make_order


def form_action(response):
    """The form-action sources of the policy ``response`` was served with."""
    header = response.headers['Content-Security-Policy']
    for part in header.split(';'):
        name, _sep, sources = part.strip().partition(' ')
        if name == 'form-action':
            return sources.split()
    return []


def allows(sources, url):
    """Whether a form-action source list lets a navigation reach ``url``.

    Only the two shapes this site uses: an exact https origin, and an https
    wildcard for any subdomain. Enough to test our list; not a CSP engine.
    """
    parts = urlsplit(url)
    if parts.scheme != 'https':
        return False
    for source in sources:
        if not source.startswith('https://'):
            continue
        host = source[len('https://'):]
        if host.startswith('*.'):
            if parts.hostname.endswith(host[1:]):
                return True
        elif parts.hostname == host:
            return True
    return False


@override_settings(CLICK_SERVICE_ID='11111', CLICK_MERCHANT_ID='22222',
                   PAYME_ID='payme-test-id', PAYME_KEY='payme-test-key')
class PayFormActionTests(TestCase):
    """The link a customer is redirected to is one the pay page may reach."""

    def setUp(self):
        self.user = make_user('tolovchi', '+998901229501')
        self.product, self.variant = make_product('Tolov', stock=5)
        self.order = make_order(self.user, self.variant, status='paying')
        self.client.force_login(self.user)

    def served(self):
        """The form-action the payment page itself is served with."""
        response = self.client.get(reverse('payment', args=[self.order.id]))
        self.assertEqual(response.status_code, 200)
        return form_action(response)

    def link(self, method):
        """A real pay link for this order, built the way payment_start builds it."""
        return services._build_paylink(self.order, 'https://graphix.uz/uz/', method)

    def test_the_click_pay_page_is_allowed(self):
        """The one that was reported: a plain click on the button did nothing."""
        url = self.link(Order.PaymentMethod.CLICK)
        self.assertTrue(allows(self.served(), url), url)

    def test_the_payme_pay_page_is_allowed(self):
        url = self.link(Order.PaymentMethod.PAYME)
        self.assertTrue(allows(self.served(), url), url)

    def test_octo_is_allowed_by_its_wildcard(self):
        """Octo's link comes from its API; any octo.uz host is its pay page."""
        self.assertTrue(allows(self.served(), 'https://pay2.octo.uz/pay/abc'))

    def test_nothing_else_is_allowed(self):
        """The gateways, and not a site that merely looks like one."""
        sources = self.served()
        self.assertIn("'self'", sources)
        self.assertFalse(allows(sources, 'https://my.click.uz.example.com/pay'))
        self.assertFalse(allows(sources, 'https://octo.uz.example.com/pay'))
        self.assertFalse(allows(sources, 'https://example.com/pay'))
        self.assertFalse(allows(sources, 'http://my.click.uz/services/pay'))

    def test_every_gateway_has_a_pay_page(self):
        """A gateway added to the table without a line in PAY_PAGES fails here."""
        self.assertEqual(set(services.GATEWAY_CREDENTIALS),
                         {Order.PaymentMethod.CLICK, Order.PaymentMethod.PAYME,
                          Order.PaymentMethod.OCTO})
        self.assertEqual(len(PAY_PAGES), len(services.GATEWAY_CREDENTIALS))
