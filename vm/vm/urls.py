"""Root URL configuration.

Split deliberately in two:

* **Unprefixed** — everything a machine calls or that must live at one fixed
  path: the Click webhook, admin, the sitemap, robots.txt, the web manifest,
  ``set_language``, and (in development) media and static. A language prefix on
  any of these breaks the caller. The Click webhook is the dangerous one: Click
  POSTs to ``/payment/click/update/`` and a 404 there means payments silently
  fail (§12 risk #2). ``core/tests.py`` asserts it stays unprefixed.

* **Prefixed** — every human-facing page, wrapped in ``i18n_patterns``. **All
  three languages carry a prefix**: Uzbek at ``/uz/``, Russian at ``/ru/``,
  English at ``/en/``. Uzbek was unprefixed until 2026-09-14; Kamronbek's
  decision to prefix it too is §17 #121, and the reason is that an unprefixed
  default is a special case Django keeps having to work around — it forces the
  default language on every unprefixed path, which is what broke the language
  switcher (§17 #115). An old unprefixed URL still works: it 404s inside
  ``i18n_patterns``, and ``LocaleMiddleware`` then redirects it to the prefixed
  path in the visitor's own language.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.views.generic import TemplateView

from core.sitemaps import sitemaps as site_maps
from payment.urls import webhook_urlpatterns

# ---- never language-prefixed ----
urlpatterns = [
    path('admin/', admin.site.urls),

    # SEO
    path('sitemap.xml', sitemap, {'sitemaps': site_maps}, name='sitemap'),
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),
    # Rendered as a template so the icon paths come from {% static %} and keep
    # working once static files are hashed.
    path('site.webmanifest', TemplateView.as_view(template_name='site.webmanifest',
                                                  content_type='application/manifest+json')),

    # Language switching. Django's set_language POSTs here and redirects to the
    # translated version of the page the visitor was on.
    path('i18n/', include('django.conf.urls.i18n')),
]

# The Click callback. Outside i18n_patterns, and it stays that way.
urlpatterns += webhook_urlpatterns

# ---- language-prefixed ----
urlpatterns += i18n_patterns(
    path('', include('core.urls')),
    path('', include('user.urls')),
    path('', include('product.urls')),
    path('cart/', include('cart.urls')),
    path('', include('payment.urls')),
    # Uzbek is prefixed too (§17 #121). Stated explicitly rather than left to
    # the default, because this line is the whole URL shape of the site and the
    # next person should not have to know what Django's default is.
    prefix_default_language=True,
)

# Serve uploaded media and static files via Django only in development;
# in production nginx serves them directly.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / 'static')

handler404 = 'core.views.handler404'
handler500 = 'core.views.handler500'
