"""Phase 10: hardening, and the things it had to move out of the way first.

A Content-Security-Policy that forbids inline script is only worth having if
nothing on the site depends on inline script. Django gives us a nonce for the
one inline `<script>`; it gives us nothing for an inline **event handler**,
because a nonce cannot be attached to an attribute. So `onerror=` and
`onchange=` do not become "allowed with a nonce" under the policy — they stop
running, on every page that has one, with nothing in the interface to say so.

That is why the handlers move first and the policy comes second, and why the
test that matters most here is not about any one handler: it is
`test_no_template_carries_an_inline_event_handler`, which fails on the next
one somebody writes.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.utils import translation
from django.urls import reverse

from core.middleware import PAY_PAGES
from product.templatetags import image_tags

ROOT = Path(settings.BASE_DIR)
TEMPLATES = ROOT / 'templates'
STATIC = ROOT / 'static'

#: Every way HTML can carry executable code in an attribute. Not an exhaustive
#: list of DOM events - a list of the ones a template here would plausibly
#: use, plus the two that were actually found (§17 #239).
HANDLER = re.compile(
    r'\son(?:click|change|error|submit|input|load|focus|blur|keydown|keyup|'
    r'mouseover|mouseout|mouseenter|mouseleave|paste|drop|toggle)\s*=',
    re.IGNORECASE)


class InlineHandlerTests(TestCase):
    """No template and no template tag may carry executable attributes."""

    def test_no_template_carries_an_inline_event_handler(self):
        """The class of mistake, not the two instances that were found.

        §17 #239 named two - `cart.html` and `image_tags.py`. Building the
        matrix found a third in `shop.html` that the decision had missed,
        which is the argument for asserting the rule rather than the list.
        """
        offenders = []
        for path in sorted(TEMPLATES.rglob('*.html')):
            body = path.read_text(encoding='utf-8')
            for match in HANDLER.finditer(body):
                line = body[:match.start()].count('\n') + 1
                offenders.append('%s:%d %s'
                                 % (path.relative_to(ROOT), line,
                                    match.group(0).strip()))
        self.assertEqual(offenders, [], 'inline handlers: %s' % offenders)

    def test_no_python_writes_an_inline_event_handler(self):
        """`photo_attrs` wrote one into every image on the site."""
        offenders = []
        for app in ('core', 'cart', 'panel', 'payment', 'product', 'user'):
            for path in sorted((ROOT / app).rglob('*.py')):
                if 'migrations' in path.parts or path.name.startswith('test_'):
                    continue
                body = path.read_text(encoding='utf-8')
                for match in HANDLER.finditer(body):
                    line = body[:match.start()].count('\n') + 1
                    # A comment explaining the ban is not a violation of it.
                    source = body.split('\n')[line - 1].lstrip()
                    if source.startswith('#'):
                        continue
                    offenders.append('%s:%d' % (path.relative_to(ROOT), line))
        self.assertEqual(offenders, [], 'inline handlers: %s' % offenders)


class PhotoFallbackTests(TestCase):
    """The broken-image fallback survived the move out of the attribute."""

    class FakePhoto:
        """Enough of a `Photograph` for the tag - no database, no files.

        `has_photo` is the gate: without it the tag returns the placeholder on
        its own and never reaches the branch under test, which is how the
        first version of these tests managed to assert nothing.
        """
        has_photo = True
        width = 800
        height = 1000

        def display_url(self):
            return '/media/products/x.jpg'

        def srcset(self):
            return '/media/products/x-400.webp 400w'

    def attrs(self):
        return str(image_tags.photo_attrs(self.FakePhoto()))

    def test_the_tag_emits_a_fallback_address(self):
        self.assertIn('data-fallback="', self.attrs())

    def test_the_tag_emits_no_handler(self):
        self.assertNotIn('onerror', self.attrs())

    def test_the_fallback_is_a_real_placeholder(self):
        """A `data-fallback` pointing nowhere is worse than none: the browser
        would swap one broken image for another and stop trying.
        """
        match = re.search(r'data-fallback="([^"]+)"', self.attrs())
        self.assertIsNotNone(match)
        self.assertTrue(match.group(1).startswith('/'), match.group(1))

    def test_main_js_handles_the_error(self):
        """The behaviour moved somewhere, and this says where."""
        body = (STATIC / 'js' / 'main.js').read_text(encoding='utf-8')
        self.assertIn("data-fallback", body)
        self.assertIn("addEventListener('error'", body)

    def test_the_error_listener_captures(self):
        """`error` does not bubble. A listener without the capture flag never
        fires for an image, and the fallback would be dead code.
        """
        body = (STATIC / 'js' / 'main.js').read_text(encoding='utf-8')
        listener = body[body.index("addEventListener('error'"):]
        self.assertIn('}, true);', listener[:400])

    def test_images_that_failed_before_the_script_ran_are_swept(self):
        """main.js is deferred, so an image can fail before it executes. The
        listener cannot catch those and the sweep is what does.
        """
        body = (STATIC / 'js' / 'main.js').read_text(encoding='utf-8')
        self.assertIn('naturalWidth === 0', body)
        self.assertIn('sweepBrokenImages()', body)


class AutoSubmitTests(TestCase):
    """The two controls that submit their form when they change."""

    def test_the_cart_quantity_field_is_marked(self):
        body = (TEMPLATES / 'cart' / 'cart.html').read_text(encoding='utf-8')
        self.assertIn('data-autosubmit', body)

    def test_the_shop_sort_menu_is_marked(self):
        body = (TEMPLATES / 'product' / 'shop.html').read_text(encoding='utf-8')
        self.assertIn('data-autosubmit', body)

    def test_main_js_submits_them(self):
        body = (STATIC / 'js' / 'main.js').read_text(encoding='utf-8')
        self.assertIn('data-autosubmit', body)
        self.assertIn('el.form.submit()', body)

    def test_the_shop_still_sorts_without_javascript(self):
        """The autosubmit is a convenience. The form is a GET with a submit
        button behind it, and the page has to work when nothing runs.
        """
        with translation.override('uz'):
            url = reverse('shop')
        response = self.client.get(url, {'sort': 'rating'})
        self.assertEqual(response.status_code, 200)


def directives(header):
    """A CSP header string as {directive: [sources]}."""
    out = {}
    for part in header.split(';'):
        bits = part.split()
        if bits:
            out[bits[0]] = bits[1:]
    return out


class PolicyTests(TestCase):
    """The header itself: what it says, and what it refuses to say."""

    def get(self, name='home', **kwargs):
        with translation.override('uz'):
            url = reverse(name, kwargs=kwargs or None)
        return self.client.get(url)

    def policy(self, name='home', **kwargs):
        response = self.get(name, **kwargs)
        self.assertIn('Content-Security-Policy', response.headers,
                      '%s carries no policy' % name)
        return directives(response.headers['Content-Security-Policy'])

    def test_every_html_page_carries_a_policy(self):
        for name in ('home', 'shop', 'cart', 'about', 'contact', 'login'):
            with self.subTest(name=name):
                self.policy(name)

    def test_script_src_has_no_unsafe_inline(self):
        """The whole point. With 'unsafe-inline' an injected <script> runs and
        the nonce is decoration.
        """
        self.assertNotIn("'unsafe-inline'", self.policy()['script-src'])

    def test_an_ordinary_page_has_no_unsafe_eval(self):
        """Google needs it for Maps. Nothing else on the site does, and it is
        confined to the two pages that load the map.
        """
        self.assertNotIn("'unsafe-eval'", self.policy()['script-src'])

    def test_script_src_carries_a_nonce(self):
        sources = self.policy()['script-src']
        self.assertTrue(any(s.startswith("'nonce-") for s in sources), sources)

    def test_the_nonce_changes_every_response(self):
        """A nonce reused across responses is a nonce an attacker can read off
        one page and reuse on the next.
        """
        first = self.policy()['script-src']
        second = self.policy()['script-src']
        self.assertNotEqual(first, second)

    def test_the_page_and_the_header_carry_the_same_nonce(self):
        """Two nonces that disagree means the JSON-LD block silently stops
        rendering for search engines, with nothing visible on the page.
        """
        response = self.get('home')
        header = directives(response.headers['Content-Security-Policy'])
        nonce = [s for s in header['script-src'] if s.startswith("'nonce-")][0]
        value = nonce.strip("'")[len('nonce-'):]
        self.assertIn('nonce="%s"' % value, response.content.decode())

    def test_object_and_frame_ancestors_are_shut(self):
        policy = self.policy()
        self.assertEqual(policy['object-src'], ["'none'"])
        self.assertEqual(policy['frame-ancestors'], ["'none'"])

    def test_form_action_is_self_and_the_pay_pages(self):
        """Every form posts to this origin, and the gateways' pay pages are
        listed too: the pay button's POST is answered with a 302 to the
        gateway, and browsers hold that redirect to form-action as well.
        This test once asserted 'self' alone, on the belief that a redirect
        is not checked, and the pay button did nothing (§17 #298). Pinned
        exactly, so that widening it is a decision rather than an accident.
        """
        self.assertEqual(self.policy()['form-action'], ["'self'", *PAY_PAGES])

    def test_style_src_keeps_unsafe_inline_and_says_why(self):
        """Not an oversight - the rating bar binds its width as a custom
        property and CSS cannot know the number (§17 #239). Asserted so that
        removing it is a decision rather than an accident.
        """
        self.assertIn("'unsafe-inline'", self.policy()['style-src'])


class MapsPolicyTests(TestCase):
    """Maps needs a looser policy, and it gets it in exactly two places."""

    def setUp(self):
        from .test_phase6 import make_user
        self.user = make_user('xarita', '+998901500001')

    def policy_for(self, url):
        response = self.client.get(url)
        return directives(response.headers.get('Content-Security-Policy', ''))

    def checkout_policy(self, lang='uz'):
        self.client.force_login(self.user)
        with translation.override(lang):
            url = reverse('checkout')
        return self.policy_for(url)

    def test_the_checkout_may_run_the_maps_script(self):
        """Google's guidance requires 'unsafe-eval' and blob:. Without them
        the map does not appear and nothing on the page explains why.
        """
        policy = self.checkout_policy()
        self.assertIn("'unsafe-eval'", policy['script-src'])
        self.assertIn('blob:', policy['script-src'])
        self.assertIn('https://maps.googleapis.com', policy['script-src'])

    def test_the_checkout_can_fetch_tiles_and_geocode(self):
        policy = self.checkout_policy()
        self.assertIn('https://*.googleapis.com', policy['connect-src'])
        self.assertIn('https://*.gstatic.com', policy['img-src'])
        self.assertIn('blob:', policy['worker-src'])

    def test_the_admin_may_too(self):
        """`payment/admin.py` draws a dropped pin on the order form."""
        self.assertIn("'unsafe-eval'",
                      self.policy_for('/admin/login/')['script-src'])

    def test_no_other_page_may(self):
        """The loosening is the price of the map; a page with no map pays
        none of it.
        """
        for name in ('home', 'shop', 'cart', 'about', 'terms'):
            with self.subTest(name=name):
                with translation.override('uz'):
                    url = reverse(name)
                policy = self.policy_for(url)
                self.assertNotIn("'unsafe-eval'", policy['script-src'])
                self.assertNotIn('worker-src', policy)

    def test_the_checkout_is_matched_in_every_language(self):
        """Matching on the path would have caught /uz/checkout/ and missed
        /ru/checkout/, leaving Russian customers with a map that never loads.
        """
        for lang in ('uz', 'ru', 'en'):
            with self.subTest(lang=lang):
                self.assertIn("'unsafe-eval'",
                              self.checkout_policy(lang)['script-src'])

    def test_only_the_checkout_includes_the_map_script(self):
        """The guard on that list. If a second template ever loads `map.js`,
        its page gets the strict policy, the map fails silently, and this is
        what says so - `core/middleware.py` needs the new URL name.
        """
        including = sorted(
            p.relative_to(TEMPLATES).as_posix()
            for p in TEMPLATES.rglob('*.html')
            if 'js/map.js' in p.read_text(encoding='utf-8'))
        self.assertEqual(including, ['payment/checkout.html'],
                         'templates loading map.js: %s' % including)


# ---------------------------------------------------------------------------
# Hardening items 4 and 5: authentication, ownership and CSRF on the endpoints
# that change something.
#
# The smoke matrix asks every URL what it answers to a GET. That is the wrong
# question for a write endpoint: a GET is 405 whoever sends it, and 405 says
# nothing about whether an anonymous POST would have gone through. These ask
# with the method the endpoint actually accepts.
#
# The tables come from `test_smoke` on purpose. An endpoint added there is
# covered here the same day, and one that exists in neither fails the smoke
# matrix's own coverage test.
# ---------------------------------------------------------------------------
from .test_smoke import PANEL, WRITE_ONLY  # noqa: E402


class AnonymousWriteTests(TestCase):
    """No write endpoint may act for a visitor who is not signed in."""

    #: The four that anonymous visitors are *supposed* to reach. The cart
    #: belongs to the session before it belongs to an account, and the
    #: password-reset steps run for somebody who by definition cannot sign in.
    PUBLIC = {'cart_add', 'cart_update', 'cart_remove',
              'password_reset_resend', 'password_reset_expire',
              'logout', 'set_language'}

    def setUp(self):
        from .test_phase4 import make_product
        from .test_phase6 import make_user
        from .test_phase12 import make_order
        self.owner = make_user('egasi', '+998901600001')
        self.product, self.variant = make_product('Himoya', stock=4)
        self.order = make_order(self.owner, self.variant, status='paying')

    def tokens(self):
        return {'slug': self.product.slug, 'product_pk': self.product.pk,
                'item_pk': 1, 'order_pk': self.order.pk,
                'paying_pk': self.order.pk, 'order_no': self.order.order_no,
                'review_pk': 1, 'msg_pk': 1, 'tag_pk': 1, 'kind': 'tag'}

    def urls(self, pages):
        toks = self.tokens()
        for page in pages:
            if page.name in self.PUBLIC:
                continue
            kwargs = {k: toks[v] for k, v in page.kwargs.items()}
            with translation.override('uz'):
                yield page.name, reverse(page.name, kwargs=kwargs or None)

    def test_an_anonymous_post_is_refused_everywhere(self):
        """Refused means redirected to the login page or answered 401/403 -
        never 200, and never the 302-to-somewhere-useful that means it worked.
        """
        for name, url in self.urls(WRITE_ONLY + PANEL):
            with self.subTest(name=name):
                response = self.client.post(url, {})
                if response.status_code in (301, 302):
                    self.assertIn(
                        '/login/', response.headers.get('Location', ''),
                        '%s redirected an anonymous POST somewhere other than '
                        'the login page' % name)
                else:
                    self.assertIn(
                        response.status_code, (401, 403, 405),
                        '%s answered an anonymous POST with %s'
                        % (name, response.status_code))


class NonStaffWriteTests(TestCase):
    """A signed-in customer must not reach a panel write endpoint.

    Separate from the anonymous case because the failure is different: the
    anonymous visitor is sent to a login page, and this one has already
    logged in. 403 is the only correct answer, and it is the guard in
    `panel/auth.py` that gives it.
    """

    def setUp(self):
        from .test_phase4 import make_product
        from .test_phase6 import make_user
        from .test_phase12 import make_order
        self.user = make_user('mijoz', '+998901600002')
        self.product, self.variant = make_product('Panel', stock=2)
        self.order = make_order(self.user, self.variant, status='paying')
        self.client.force_login(self.user)

    def test_every_panel_write_answers_403(self):
        toks = {'slug': self.product.slug, 'order_no': self.order.order_no,
                'review_pk': 1, 'msg_pk': 1, 'tag_pk': 1, 'kind': 'tag'}
        for page in PANEL:
            kwargs = {k: toks[v] for k, v in page.kwargs.items()}
            with self.subTest(name=page.name):
                with translation.override('uz'):
                    url = reverse(page.name, kwargs=kwargs or None)
                self.assertEqual(
                    self.client.post(url, {}).status_code, 403,
                    '%s let a signed-in customer POST' % page.name)


class WrongOwnerWriteTests(TestCase):
    """Signed in is not the same as being the customer whose order it is."""

    def setUp(self):
        from .test_phase4 import make_product
        from .test_phase6 import make_user
        from .test_phase12 import make_order
        self.owner = make_user('egasi', '+998901600003')
        self.other = make_user('boshqa', '+998901600004')
        self.product, self.variant = make_product('Egalik', stock=2)
        self.paying = make_order(self.owner, self.variant, status='paying')
        self.done = make_order(self.owner, self.variant, status='done')
        self.client.force_login(self.other)

    def post(self, name, **kwargs):
        with translation.override('uz'):
            url = reverse(name, kwargs=kwargs)
        return self.client.post(url, {})

    def test_another_customers_order_cannot_be_cancelled(self):
        self.assertEqual(self.post('order_cancel', pk=self.paying.pk)
                         .status_code, 404)
        self.paying.refresh_from_db()
        self.assertEqual(self.paying.status, 'paying')

    def test_another_customers_payment_cannot_be_started(self):
        self.assertEqual(self.post('payment_start',
                                   order_id=self.paying.pk).status_code, 404)

    def test_another_customers_order_cannot_be_reviewed(self):
        from product.models import Review
        before = Review.objects.count()
        self.assertEqual(self.post('review_create',
                                   order_id=self.done.pk).status_code, 404)
        self.assertEqual(Review.objects.count(), before)


class CsrfTests(TestCase):
    """CSRF is middleware, so it is easy to assume rather than check.

    Django's test client exempts itself by default, which means the whole
    suite runs with CSRF switched off and nothing would notice a view
    decorated `@csrf_exempt` by mistake. `enforce_csrf_checks` turns it back
    on for these.
    """

    def setUp(self):
        from django.test import Client
        from .test_phase4 import make_product
        from .test_phase6 import make_user
        from .test_phase12 import make_order
        self.user = make_user('mijoz', '+998901600005')
        self.product, self.variant = make_product('Token', stock=2)
        self.order = make_order(self.user, self.variant, status='paying')
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)

    def test_a_post_without_a_token_is_refused(self):
        with translation.override('uz'):
            targets = [
                reverse('order_cancel', kwargs={'pk': self.order.pk}),
                reverse('payment_start', kwargs={'order_id': self.order.pk}),
                reverse('product_like', kwargs={'slug': self.product.slug}),
                reverse('cart_add', kwargs={'product_id': self.product.pk}),
            ]
        for url in targets:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, {}).status_code, 403)

    def test_the_payment_webhooks_are_exempt(self):
        """A gateway has no CSRF token, so the callback must be exempt.

        This failed when it was written. The three views subclassed tolov's
        `...django.webhooks` handlers, which are plain `View`s; the
        `csrf_exempt` versions live in `...django.views` and are what a
        urlconf is meant to mount. Every callback would have been answered
        403 in production, and no order could ever have been marked paid.
        Django's test client disables CSRF by default, which is why every
        earlier webhook test passed (§17 #270).
        """
        for name in ('click_webhook', 'payme_webhook', 'octo_webhook'):
            with self.subTest(name=name):
                response = self.client.post(reverse(name), {})
                self.assertNotEqual(
                    response.status_code, 403,
                    '%s was refused for CSRF; a gateway has no token' % name)

    def test_an_unconfigured_gateway_answers_instead_of_raising(self):
        """A gateway with no credentials must not 500 the callback (§4).

        tolov checks its settings in the view's ``__init__``, which Django
        calls per request, so a switched-off gateway raised on every callback
        and Django answered 500. A gateway reads 500 as "try again" and retries
        for ever. It is also why CI was red for ten runs: CI sets no `OCTO_*`,
        this machine's `.env` does, and nothing else differed.
        """
        from django.test import override_settings

        tolov = {key: dict(value) if isinstance(value, dict) else value
                 for key, value in settings.TOLOV.items()}
        tolov.setdefault('OCTO_BANK', {})['OCTO_SHOP_ID'] = ''

        with override_settings(TOLOV=tolov):
            refused = self.client.post(reverse('octo_webhook'), {})
            # The 405 has to survive the guard. It is what says the route still
            # resolves - asserted by the smoke matrix, watched by the uptime
            # monitor - and a 404 there means the webhook has moved and
            # payments are failing silently (§12 risk #2).
            resolves = self.client.get(reverse('octo_webhook'))

        self.assertEqual(refused.status_code, 503)
        self.assertEqual(resolves.status_code, 405)

    def test_the_views_are_marked_exempt_and_not_merely_tolerated(self):
        """The assertion above passes for the wrong reason if a view starts
        answering 403 of its own accord, so read the flag as well.
        """
        from payment import views
        for name, cls in (('click', views.ClickWebhookAPIView),
                          ('payme', views.PaymeWebhookAPIView),
                          ('octo', views.OctoWebhookAPIView)):
            with self.subTest(name=name):
                self.assertTrue(getattr(cls.as_view(), 'csrf_exempt', False),
                                '%s webhook is not csrf_exempt' % name)


class WebhookSignatureTests(TestCase):
    """Item 6: a callback nobody signed is not a payment.

    The webhooks are CSRF-exempt, so the signature is the only thing standing
    between an unsigned POST and an order marked paid.
    """

    def test_an_unsigned_click_callback_is_refused(self):
        response = self.client.post(reverse('click_webhook'), {
            'click_trans_id': '1', 'merchant_trans_id': '1', 'amount': '1',
            'action': '0', 'sign_string': 'nonsense', 'sign_time': '0',
            'service_id': '1', 'error': '0',
        })
        self.assertIn('error', response.content.decode().lower())
        self.assertNotIn('"error": 0', response.content.decode())

    def test_an_empty_callback_does_not_mark_anything_paid(self):
        from payment.models import Order
        paid_before = Order.objects.filter(status=Order.Status.PAID).count()
        for name in ('click_webhook', 'payme_webhook', 'octo_webhook'):
            self.client.post(reverse(name), {})
        self.assertEqual(
            Order.objects.filter(status=Order.Status.PAID).count(),
            paid_before)


class ErrorPageTests(TestCase):
    """Item 9: what an error page gives away with DEBUG off.

    The suite runs with DEBUG False already, so these read the real pages.
    """

    def test_a_missing_page_gives_nothing_away(self):
        html = self.client.get('/uz/no-such-page/').content.decode()
        for leak in ('Traceback', 'DJANGO_SETTINGS_MODULE', 'SECRET_KEY',
                     'site-packages', 'Request Method', 'BASE_DIR'):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, html)

    def test_the_error_pages_are_the_sites_own(self):
        """Django's default 404 is a white page in English. These are ours,
        which means they are translated and carry the site's navigation.
        """
        response = self.client.get('/uz/no-such-page/')
        self.assertEqual(response.status_code, 404)
        self.assertIn('GRAPHIX', response.content.decode())


class ThrowawayMediaTests(TestCase):
    """Backlog #42: a test run must not write into the developer's media/.

    The fix is one line in the runner rather than a mixin on each test class,
    because a mixin has to be remembered by whoever writes the next test that
    saves a file and forgetting it is invisible.
    """

    def test_the_run_is_not_pointed_at_the_real_media_folder(self):
        from django.conf import settings as live
        self.assertNotEqual(
            Path(live.MEDIA_ROOT).resolve(), (ROOT / 'media').resolve(),
            'the suite is writing into the real media folder')

    def test_the_throwaway_folder_is_a_temporary_one(self):
        from django.conf import settings as live
        self.assertIn('gx-test-media-', str(live.MEDIA_ROOT))

    def test_saving_a_photograph_lands_in_it(self):
        from django.conf import settings as live
        from product.models import ImageP
        from .test_phase4 import make_product
        from .test_backlog import jpeg
        product, _variant = make_product('Vaqtinchalik', stock=1)
        image = ImageP.objects.create(product=product, picture=jpeg(), order=0)
        self.assertTrue(
            Path(image.picture.path).resolve().is_relative_to(
                Path(live.MEDIA_ROOT).resolve()),
            'the file landed outside the throwaway folder: %s'
            % image.picture.path)


class ReplacedPictureTests(TestCase):
    """Backlog #41: replacing a picture on a row that stays deletes the old file.

    The delete receivers fire on a deleted row. A replacement keeps the row,
    so nothing fired and the old file stayed on disk forever. Only the Django
    admin can do this; the panel adds and removes photographs rather than
    swapping one in place.
    """

    def setUp(self):
        from product.models import ImageP
        from .test_phase4 import make_product
        from .test_backlog import jpeg
        self.product, _variant = make_product('Almashtirish', stock=1)
        self.image = ImageP.objects.create(product=self.product,
                                           picture=jpeg(), order=0)
        self.image.refresh_from_db()
        self.old = self.image.picture.path
        self.assertTrue(Path(self.old).exists())

    def test_the_replaced_file_is_removed(self):
        """`forget_file` waits for the commit, so the callbacks have to be run
        for the test to see anything. That is also the behaviour worth having:
        a replacement rolled back must not have deleted the old file.
        """
        from .test_backlog import jpeg
        self.image.picture = jpeg()
        with self.captureOnCommitCallbacks(execute=True):
            self.image.save()
        self.assertFalse(Path(self.old).exists(),
                         'the replaced file is still on disk')

    def test_a_rolled_back_replacement_keeps_the_old_file(self):
        """The delete is queued on commit, so a save that never commits must
        leave the file the row still points at.
        """
        from .test_backlog import jpeg
        self.image.picture = jpeg()
        with self.captureOnCommitCallbacks(execute=False):
            self.image.save()
        self.assertTrue(Path(self.old).exists())

    def test_the_new_file_survives(self):
        """The guard against a fix that deletes the wrong one."""
        from .test_backlog import jpeg
        self.image.picture = jpeg()
        with self.captureOnCommitCallbacks(execute=True):
            self.image.save()
        self.image.refresh_from_db()
        self.assertTrue(Path(self.image.picture.path).exists())

    def test_saving_without_changing_the_picture_keeps_it(self):
        """`build_renditions` re-saves the row on commit. If that counted as a
        replacement, every upload would delete its own photograph.
        """
        self.image.order = 3
        with self.captureOnCommitCallbacks(execute=True):
            self.image.save()
        self.assertTrue(Path(self.old).exists())

    def test_a_file_another_row_still_uses_is_kept(self):
        """`forget_file` checks before deleting, and this is why."""
        from product.models import ImageP
        from .test_backlog import jpeg
        shared = ImageP.objects.create(product=self.product, order=1)
        ImageP.objects.filter(pk=shared.pk).update(
            picture=self.image.picture.name)
        self.image.picture = jpeg()
        with self.captureOnCommitCallbacks(execute=True):
            self.image.save()
        self.assertTrue(Path(self.old).exists(),
                        'a file another row still names was deleted')


# ---------------------------------------------------------------------------
# Backlog #32 - which wording of the documents a customer agreed to.
#
# Both documents were versioned and the consent was already asked for. What
# was missing was the pair, so a dispute about what somebody agreed to could
# be answered only with whatever the site happened to say that week.
# ---------------------------------------------------------------------------
from core import legal  # noqa: E402


class ConsentRecordTests(TestCase):
    """Signup stamps the account, checkout stamps the order, and neither
    stamps a consent that was not actually given.
    """

    def setUp(self):
        from .test_phase4 import make_product
        from .test_phase6 import make_regions, make_user
        self.geo = make_regions()
        self.terms = legal.current_version('terms')
        self.privacy = legal.current_version('privacy')
        self.user = make_user('rozi', '+998901290055')
        _product, self.variant = make_product('Rozilik', stock=5)
        self.cart = self._cart()

    def _cart(self):
        from cart.models import Cart, CartItem
        cart = Cart.objects.create(user=self.user, status=True)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1,
                                price_stat=self.variant.price)
        return cart

    def _signup(self, **extra):
        """Register through the page, with the SMS patched out (§17 #196)."""
        from unittest import mock
        from user.models import User
        data = {'username': 'roziuser', 'first_name': 'Rozi',
                'phone': '+998901119955',
                'password1': 'parol12345', 'password2': 'parol12345'}
        data.update(extra)
        with mock.patch('user.otp.send_sms', return_value=True):
            self.client.post(reverse('signup'), data)
        return User.objects.filter(username=data['username']).first()

    def test_signing_up_records_both_versions(self):
        user = self._signup(agree='on')
        self.assertIsNotNone(user, 'the signup did not go through')
        self.assertEqual(user.terms_version, self.terms)
        self.assertEqual(user.privacy_version, self.privacy)

    #: Without the box. Each POST gets its own number: the signup is rate
    #: limited per phone, and the cache outlives a single test.
    UNTICKED = {'username': 'belgisiz', 'first_name': 'Rozi',
                'password1': 'parol12345', 'password2': 'parol12345'}

    def test_a_signup_without_the_box_is_refused(self):
        """The server refuses what the browser refuses: no account, no code
        sent, and the form comes back with what was typed in it, so ticking
        the box is all that is left to do (§17 #291, closing §18 #47).

        This replaces a test asserting the opposite - that such a request
        still registered, only without a consent on record.
        """
        from unittest import mock
        from user.models import User
        with mock.patch('user.otp.send_sms', return_value=True) as sms:
            response = self.client.post(
                reverse('signup'), dict(self.UNTICKED, phone='+998901119956'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='belgisiz').exists())
        sms.assert_not_called()
        self.assertContains(response, 'maxfiylik siyosatiga rozilik bering')
        self.assertContains(response, 'value="belgisiz"')

    def test_the_refusal_is_written_in_each_language(self):
        """Read off the page rather than the catalogue: a msgid that drifts by
        one character leaves a tidy catalogue and an Uzbek sentence on a
        Russian screen (§17 #255).
        """
        expected = {
            'uz': 'foydalanish shartlari va maxfiylik siyosatiga rozilik bering',
            'ru': 'примите условия использования и политику конфиденциальности',
            'en': 'accept the terms of use and the privacy policy',
        }
        for n, (language, words) in enumerate(expected.items()):
            with self.subTest(language=language), translation.override(language):
                response = self.client.post(
                    reverse('signup'),
                    dict(self.UNTICKED, phone='+99890111996%d' % n))
                self.assertContains(response, words)

    def test_the_box_is_named_so_the_server_can_see_it(self):
        """An unnamed checkbox posts nothing at all, which is how the consent
        went unrecorded for eight phases. The assertion is on the name.
        """
        page = self.client.get(reverse('signup')).content.decode()
        self.assertRegex(page, r'<input type="checkbox" name="agree"[^>]*required')

    def _checkout(self, cart=None):
        from payment.models import Order
        cart = cart or self.cart
        self.client.force_login(self.user)
        self.client.post(reverse('checkout'), {
            'name': 'Dilnoza Karimova', 'phone': '+998 90 129 00 55',
            'delivery_option': 'uzpost_office',
            'region': self.geo['tashkent'].pk,
            'district': self.geo['chilonzor'].pk,
            'postal_index': '100011',
            'payment_method': 'click', 'notes': '',
        })
        return Order.objects.get(cart=cart)

    def test_placing_an_order_records_both_versions(self):
        """The checkout says pressing the button accepts both documents, so
        the order carries both numbers whether or not the account does.
        """
        order = self._checkout()
        self.assertEqual(order.terms_version, self.terms)
        self.assertEqual(order.privacy_version, self.privacy)

    def test_an_amendment_does_not_rewrite_an_order_already_placed(self):
        """The whole point of storing it rather than looking it up later.

        A new order records the new wording; the one placed under the old
        wording keeps the old one, the way `location_snapshot` keeps a
        district that has since been renamed.
        """
        from datetime import date
        from unittest import mock
        from payment import services
        placed = self._checkout()
        amended = dict(legal.VERSIONS)
        amended['terms'] = (legal.Version('2.0', date(2027, 1, 1), 'Amended'),
                            ) + amended['terms']
        with mock.patch.object(legal, 'VERSIONS', amended):
            later = services.create_order_from_cart(
                self.user, self._cart(), phone='+998 90 129 00 55',
                address='Amir Temur 1', notes='', payment_method='click')
        placed.refresh_from_db()
        self.assertEqual(placed.terms_version, self.terms)
        self.assertEqual(later.terms_version, '2.0')
        self.assertEqual(later.privacy_version, self.privacy)

    def test_both_models_carry_a_column_for_every_consent_document(self):
        """`accepted_versions` keys by field name, so a document added to
        `CONSENT_DOCUMENTS` without its two columns fails here rather than at
        somebody's checkout.
        """
        from payment.models import Order
        from user.models import User
        for model in (User, Order):
            names = {field.name for field in model._meta.get_fields()}
            for column in legal.accepted_versions():
                self.assertIn(column, names,
                              '%s has no %s column' % (model.__name__, column))

    def test_the_recorded_number_is_the_one_the_document_page_shows(self):
        """Two readings of the same fact would eventually disagree."""
        page = self.client.get(reverse('terms')).content.decode()
        self.assertIn(self.terms, page)
        self.assertEqual(self.terms, legal.document('terms')['version'].number)


# ---------------------------------------------------------------------------
# The two hardening items that were covered by something adjacent rather than
# by themselves: item 1 (`check --deploy`) and item 6's second half (a replayed
# callback).
# ---------------------------------------------------------------------------
from django.test import SimpleTestCase  # noqa: E402


class DeployCheckTests(SimpleTestCase):
    """Item 1: `manage.py check --deploy` run, rather than approximated.

    `test_phase1b.DeploymentSettingsTests` reads the settings **file**, and has
    to: the production block sits inside `if not DEBUG:`, which settings.py
    evaluates while DEBUG is still whatever `.env` says, so an in-process
    assertion reads the development value however correct the file is. What
    that covers is a line being deleted.

    This runs the real command in a subprocess with `DEBUG=False` in the
    environment — `load_dotenv` does not override a variable that is already
    set — which is the only way to see what the server sees: a setting
    overridden further down the file, a warning nobody has read since Phase 1b,
    or a check a later Django adds.
    """

    def test_the_deploy_check_reports_nothing(self):
        import os
        import subprocess
        import sys
        from pathlib import Path
        run = subprocess.run(
            [sys.executable, 'manage.py', 'check', '--deploy'],
            cwd=str(Path(settings.BASE_DIR)),
            env=dict(os.environ, DEBUG='False', PYTHONIOENCODING='utf-8'),
            capture_output=True, text=True, encoding='utf-8')
        output = (run.stdout or '') + (run.stderr or '')
        self.assertEqual(run.returncode, 0, output)
        # `check` exits 0 for warnings, so the exit code alone says little.
        self.assertIn('no issues', output, output)


class WebhookReplayTests(TestCase):
    """Item 6, the half the signature does not cover: a callback delivered
    twice must do nothing the second time.

    Called at the mixin rather than through a signed POST. tolov owns the
    signature and its own transaction table; what is ours is the hook that
    resolves the order and the service that moves the status, and the hook is
    exactly where a replay arrives in our code. `WebhookSignatureTests` stands
    at the other door.

    `apply_successful_payment` has been asserted idempotent since Phase 4
    (§9 `payment`), but only by calling it directly — which says nothing
    about the notification, and an owner told twice about one order goes
    looking for a parcel that is not there.
    """

    class FakeTransaction:
        """All the mixin reads off tolov's `PaymentTransaction`: the id we gave
        the gateway when the pay link was made.
        """

        def __init__(self, account_id):
            self.account_id = account_id

    def setUp(self):
        from .test_phase4 import make_product
        from .test_phase6 import make_user
        from .test_phase12 import make_order
        self.user = make_user('takror', '+998901600077')
        _product, self.variant = make_product('Takror', stock=10)
        self.order = make_order(self.user, self.variant, status='paying')

    def _deliver(self, times):
        """Deliver the same successful callback ``times`` times."""
        from unittest import mock
        from payment.views import ClickWebhookAPIView
        view = ClickWebhookAPIView()
        callback = self.FakeTransaction(self.order.pk)
        with mock.patch('core.telegram.send', return_value=True) as send:
            with self.captureOnCommitCallbacks(execute=True):
                for _ in range(times):
                    view.successfully_payment({}, callback)
        return send

    def test_one_delivery_pays_the_order_and_tells_the_owner(self):
        """The control: without it, a broken replay test passes for nothing."""
        from payment.models import Order
        send = self._deliver(1)
        self.variant.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.variant.stock, 9)
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(send.call_count, 1)

    def test_a_second_delivery_moves_no_stock_and_sends_no_message(self):
        send = self._deliver(2)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 9, 'stock came down twice')
        self.assertEqual(send.call_count, 1,
                         'the owner was told twice about one order')

    def test_a_callback_naming_an_order_that_is_gone_is_logged_not_raised(self):
        """A gateway retries a 500 forever, so an unknown id is answered."""
        from payment.views import ClickWebhookAPIView
        with self.assertLogs('payment.views', level='ERROR'):
            ClickWebhookAPIView().successfully_payment(
                {}, self.FakeTransaction(9_999_999))


class DemoSlidesTests(TestCase):
    """The home carousel needs slides to exist before it can be measured.

    Phase 9's rule is that CLS is measured rather than asserted (§17 #236),
    and the home carousel's measurement was carried into this phase. It could
    not be taken: `seed_demo_catalogue` created no `Slide` rows, so every
    developer's home page rendered the no-slides branch and there was no
    carousel on screen at all. The cards are drawn by
    `docs/design/slides/build.py` and seeded here (§17 #275).
    """

    def test_every_picture_the_seeder_names_is_in_the_repository(self):
        """`media/` is gitignored, so a card added to the table without its
        artwork committed fails on a fresh clone with a copy error, at the
        moment somebody resets their catalogue. This says so first, and needs
        no database.
        """
        from product.management.commands import seed_demo_catalogue as seeder
        source = Path(settings.BASE_DIR) / 'data' / 'demo-catalogue'
        missing = [name for name in seeder.Command.image_names()
                   if not (source / Path(name).name).exists()]
        self.assertEqual(missing, [], 'not committed: %s' % missing)

    def test_every_slide_links_somewhere_the_site_actually_serves(self):
        """A demo card pointing at a renamed path is a 404 on the busiest page
        of the site.

        Fetched rather than resolved, and that is the whole lesson: every page
        here sits under a language prefix, so a slide's link is stored without
        one and `LocaleMiddleware` sends each visitor to their own language.
        `resolve('/shop/')` therefore raises on a link that is correct, which
        is exactly what this test did when it was first written.
        """
        from product.management.commands.seed_demo_catalogue import SLIDES
        for slug, link, _uz, _ru, _en in SLIDES:
            with self.subTest(slide=slug):
                response = self.client.get(link, follow=True)
                self.assertEqual(
                    response.status_code, 200,
                    '%s points at %s, which answers %s'
                    % (slug, link, response.status_code))
                self.assertTrue(
                    response.redirect_chain,
                    '%s is stored with a language prefix; it must not be'
                    % slug)

    def test_seeding_puts_a_carousel_on_the_home_page(self):
        """The end the fixture exists for: the home page renders slide cards
        rather than the branch it takes when there are none.

        The commit callbacks are run, because the picture's pixel size is
        filled by a signal that waits for the commit - and those stored
        dimensions are exactly what holds the carousel's box before the file
        arrives. A slide with no dimensions measures a CLS that is not the
        site's.
        """
        from django.core.management import call_command
        from product.models import Slide
        with self.captureOnCommitCallbacks(execute=True):
            call_command('seed_demo_catalogue', noinput=True, verbosity=0)

        slides = list(Slide.objects.filter(is_active=True))
        self.assertEqual(len(slides), 3)
        for slide in slides:
            with self.subTest(slide=slide.alt):
                self.assertTrue(slide.alt_ru and slide.alt_en,
                                'a slide with no translated alt')
                self.assertTrue(slide.has_photo)
                self.assertTrue(slide.width and slide.height,
                                'no stored pixel size, so the box cannot be held')

        page = self.client.get(reverse('home')).content.decode()
        self.assertIn('slides__track', page)
        self.assertIn(slides[0].alt, page)


class PruneKeepsWhatTheSiteServesTests(TestCase):
    """`prune_orphan_media` must never delete a file a page asks for.

    It did. `renditions_of` guessed the rendition names from the original's
    name - `<stem>-400.webp` and friends, in the same folder - and both halves
    of that guess are wrong: renditions live in a `w/` subfolder and their
    widths come from the source, which is never upscaled. So the guessed names
    matched nothing, every rendition counted as an orphan, and `--delete`
    removed all 36 on the developer's machine.

    **Nothing broke, which is why it needed measuring to find.** The fallback
    script swaps in the placeholder when an image 404s, so the pages rendered;
    the swap is a layout shift, and the home page's CLS measurement came back
    0.053 against a budget of zero (§17 #276).

    The assertion is the property, not the naming scheme: a file the site
    would serve is not an orphan.
    """

    def setUp(self):
        from product.models import ImageP
        from .test_phase4 import make_product
        from .test_backlog import jpeg
        self.product, _variant = make_product('Saqlanadi', stock=1)
        with self.captureOnCommitCallbacks(execute=True):
            self.image = ImageP.objects.create(product=self.product,
                                               picture=jpeg(), order=0)
        self.image.refresh_from_db()

    @staticmethod
    def keep_set():
        """What the command would spare, without touching a single file.

        The decision rather than the deletion: the whole run shares one
        throwaway `MEDIA_ROOT`, so earlier tests leave their own files in it
        and an orphan *count* says nothing repeatable. What went wrong was the
        set, and the set is what this reads.
        """
        from product.management.commands.prune_orphan_media import Command
        command = Command()
        return command.referenced() | command.derived()

    def test_every_rendition_a_row_serves_is_kept(self):
        served = [name for _width, name in self.image.sources()]
        self.assertTrue(served, 'no renditions were built, so nothing is proved')
        keep = self.keep_set()
        for name in served:
            self.assertIn(name, keep, '%s is what the page asks for' % name)
        self.assertIn(self.image.picture.name.replace('\\', '/'), keep)

    def test_a_name_no_row_records_is_not_kept(self):
        """The guard must not have been bought by sparing everything."""
        self.assertNotIn('products/w/nobody-800.webp', self.keep_set())


class NothingInFlowIsRevealedByScriptTests(TestCase):
    """The carousel's controls take their space at the first paint.

    The home page measured a CLS of 0.053 against a budget of zero, while the
    shop measured 0.000 - so it was not the fonts and not the header, it was
    something the home page alone had. The controls row shipped with `hidden`
    and `slides.js` removed it, which put the dots and the pause button into
    the layout *after* the page had been painted and pushed every band below
    the carousel down (§17 #276).

    The row still must not appear for somebody whose browser will not run the
    script, because it does nothing for them. So the head marks the document
    script-capable before anything is painted and the CSS keys off that. What
    is asserted here is that mechanism, in all three of the places it needs to
    hold, plus the one thing that would silently switch it off: the inline
    script needs a nonce the policy actually names, or the browser refuses it,
    `html.js` is never set, and the row disappears for everyone.
    """

    def head_script(self, html):
        """The nonce on the `html.js` line, or None if it is not there."""
        head = html.split('</head>')[0]
        found = re.search(
            r'<script nonce="([^"]*)">document\.documentElement\.className',
            head)
        return found.group(1) if found else None

    def test_the_head_marks_the_document_before_anything_is_painted(self):
        response = self.client.get(reverse('home'))
        nonce = self.head_script(response.content.decode())
        self.assertIsNotNone(
            nonce, 'nothing in the head sets html.js, so the CSS cannot key off it')
        self.assertTrue(nonce, 'the nonce rendered empty; CSP will refuse the script')

    def test_the_policy_names_the_nonce_it_is_given(self):
        """A nonce the header does not carry is a script that never runs."""
        response = self.client.get(reverse('home'))
        nonce = self.head_script(response.content.decode())
        self.assertIn("'nonce-%s'" % nonce, response['Content-Security-Policy'])

    def test_the_controls_row_is_not_hidden_in_the_markup(self):
        source = (TEMPLATES / 'core' / 'home.html').read_text(encoding='utf-8')
        marker = source[source.index('data-slides-controls'):]
        self.assertNotIn('hidden', marker[:marker.index('>')],
                         'the row is revealed by script again')

    def test_the_stylesheet_reserves_the_row_only_for_a_scripted_document(self):
        css = (STATIC / 'css' / 'pages.css').read_text(encoding='utf-8')
        self.assertIn('.slides__controls { display: none; }', css)
        self.assertIn('html.js .slides__controls', css)

    def test_the_script_no_longer_reveals_the_row(self):
        """Belt and braces: with the CSS doing it, the old line would be a
        second mechanism for the same thing, and the one that shifts.
        """
        script = (STATIC / 'js' / 'slides.js').read_text(encoding='utf-8')
        self.assertNotIn('controls.hidden = false', script)
