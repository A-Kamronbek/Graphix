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
