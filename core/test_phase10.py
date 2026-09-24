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

    def test_form_action_is_self_only(self):
        """Checked against the templates: every form posts to this origin, and
        the gateways are reached by a redirect rather than a cross-origin POST.
        """
        self.assertEqual(self.policy()['form-action'], ["'self'"])

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

    def test_a_signup_without_the_box_records_nothing(self):
        """The browser refuses the form without the box. A request that gets
        past the browser still registers, exactly as it did before - it must
        simply not leave behind a consent nobody gave (§18 #47).
        """
        user = self._signup()
        self.assertIsNotNone(user, 'the signup itself must behave as before')
        self.assertEqual(user.terms_version, '')
        self.assertEqual(user.privacy_version, '')

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
