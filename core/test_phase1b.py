"""Phase 1b: the things a deployment gets wrong quietly.

Not tests of the server - a test suite cannot reach it - but of the two
settings whose being wrong produces no error at all, only a site that is
slowly harmed:

* the production security settings, which exist only when ``DEBUG`` is off and
  which nothing has ever asserted. ``check --deploy`` is clean today; a later
  edit could make it dirty and no test would notice.
* ``SITE_INDEXABLE``, which decides whether Google may index the site. Wrong in
  one direction it indexes an empty shop; wrong in the other it hides a real
  one, and that failure is invisible - there is no error, only an absence of
  visitors.
"""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse


class DeploymentSettingsTests(SimpleTestCase):
    """What `manage.py check --deploy` checks, asserted so it cannot regress.

    Read from the FILE, not from ``settings``. Every one of these lives inside
    ``if not DEBUG:``, which settings.py evaluates while it is being imported -
    when DEBUG is still whatever ``.env`` says. Django sets DEBUG False for the
    test run long afterwards, so ``settings.SECURE_SSL_REDIRECT`` in a test
    reads the development value and would fail however correct the file is.

    Asserting the source is therefore not a shortcut, it is the only honest
    reading: what this guards against is a line being deleted, and a deleted
    line is exactly what it sees.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        source = (Path(settings.BASE_DIR) / 'config' / 'settings.py').read_text(
            encoding='utf-8')
        # Everything after the guard, so a setting moved OUT of it - which
        # would break local development in a confusing way - fails too.
        _, _, cls.guarded = source.partition('if not DEBUG:')

    def test_the_production_security_settings_are_all_set(self):
        for line in ('SECURE_SSL_REDIRECT = True',
                     'SESSION_COOKIE_SECURE = True',
                     'CSRF_COOKIE_SECURE = True',
                     'SECURE_CONTENT_TYPE_NOSNIFF = True',
                     'SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")'):
            with self.subTest(setting=line.split(' =')[0]):
                self.assertIn(line, self.guarded)

    def test_hsts_is_a_year_and_covers_the_subdomains(self):
        # A shorter max-age is worth little, and www must be covered or the
        # redirect to the apex happens over http the first time.
        self.assertIn('SECURE_HSTS_SECONDS = 31536000', self.guarded)
        self.assertIn('SECURE_HSTS_INCLUDE_SUBDOMAINS = True', self.guarded)
        self.assertIn('SECURE_HSTS_PRELOAD = True', self.guarded)

    def test_the_cache_is_shared_when_a_redis_url_is_given(self):
        """The rate limiter counts per worker unless the cache is shared.

        This is the branch that shipped broken: `settings.py` selected Django's
        Redis backend the moment REDIS_URL was set, and the package it imports
        was not installed, so the first cache read in production would have
        raised (§17 #240). The import is what this asserts - CI proves it reads
        and writes against a real Redis.
        """
        from django.core.cache.backends.redis import RedisCache  # noqa: F401


class IndexabilityTests(TestCase):
    """SITE_INDEXABLE has to reach both halves of the answer, or neither works.

    `Disallow:` stops a crawler fetching a page; it does not stop the address
    appearing in results because something else links to it. Only `noindex`
    does that, and only if the crawler is allowed to read the page to see it -
    which is why the two are set together and tested together (§19 Q37).
    """

    def robots_txt(self):
        return self.client.get('/robots.txt').content.decode()

    def home(self):
        return self.client.get(reverse('home')).content.decode()

    def test_by_default_the_site_is_indexable(self):
        # The permissive default is deliberate: a noindex left on after launch
        # is invisible and costs months.
        self.assertIs(settings.SITE_INDEXABLE, True)
        body = self.robots_txt()
        self.assertIn('Allow: /', body)
        self.assertNotIn('Disallow: /\n', body)
        self.assertIn('Sitemap:', body)
        self.assertNotIn('name="robots" content="noindex', self.home())

    @override_settings(SITE_INDEXABLE=False)
    def test_switched_off_robots_txt_closes_the_whole_site(self):
        body = self.robots_txt()
        self.assertIn('Disallow: /', body)
        self.assertNotIn('Allow: /', body)
        # Advertising a sitemap while refusing every URL in it is a mixed
        # message, and the one a crawler resolves in the wrong direction.
        self.assertNotIn('Sitemap:', body)

    @override_settings(SITE_INDEXABLE=False)
    def test_switched_off_every_public_page_says_noindex(self):
        for name in ('home', 'shop', 'about', 'contact'):
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertIn('name="robots" content="noindex', html)

    @override_settings(SITE_INDEXABLE=False)
    def test_switched_off_the_private_pages_are_still_noindex(self):
        """A page that overrides the block must not become indexable by it.

        The flag's noindex is the *default* of the `robots` block, so a page
        that fills the block replaces it. Every page that does so is already
        saying noindex, and this is the test that keeps that true.
        """
        html = self.client.get(reverse('cart')).content.decode()
        self.assertIn('name="robots" content="noindex', html)
