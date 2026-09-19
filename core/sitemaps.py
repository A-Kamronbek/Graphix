"""Sitemaps for search engines: static pages and purchasable products.

Both sitemaps set ``i18n``/``alternates``/``x_default``, so Django emits one
``<url>`` per language with ``xhtml:link`` alternates between them. That is what
tells Google the three prefixes are the same page in different languages rather
than duplicate content.
"""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from core.context_processors import has_size_guide
from product.models import Product


class StaticViewSitemap(Sitemap):
    """Top-level public pages, in every language."""
    priority = 0.6
    changefreq = 'weekly'
    i18n = True
    alternates = True
    x_default = True

    def items(self):
        # /saqlanganlar/ is deliberately absent: it needs a login, so it has
        # nothing to show a crawler.
        names = ['home', 'shop', 'about', 'contact', 'delivery', 'terms', 'privacy']
        # The size guide 404s until there is something to show, and a sitemap
        # that advertises a 404 is worse than one that omits the page. The same
        # question the page itself answers: a drawn chart OR structured rows -
        # asking only about the picture left the page out of the sitemap while
        # it was live and rendering its tables (§17 #111).
        if has_size_guide():
            names.append('size_guide')
        return names

    def location(self, name):
        return reverse(name)


class ProductSitemap(Sitemap):
    """Detail pages for products with at least one available variant, per language."""
    changefreq = 'weekly'
    priority = 0.8
    i18n = True
    alternates = True
    x_default = True

    def items(self):
        return Product.objects.filter(is_active=True, variants__available=True).distinct()

    def lastmod(self, obj):
        return obj.created_at

    def location(self, obj):
        return reverse('item', kwargs={'slug': obj.slug})


# Registered in config/urls.py under the sitemap view.
sitemaps = {
    'static': StaticViewSitemap,
    'products': ProductSitemap,
}
