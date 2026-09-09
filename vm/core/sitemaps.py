"""Sitemaps for search engines: static pages and purchasable products.

Both sitemaps set ``i18n``/``alternates``/``x_default``, so Django emits one
``<url>`` per language with ``xhtml:link`` alternates between them. That is what
tells Google the three prefixes are the same page in different languages rather
than duplicate content.
"""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from product.models import Product


class StaticViewSitemap(Sitemap):
    """Top-level public pages, in every language."""
    priority = 0.6
    changefreq = 'weekly'
    i18n = True
    alternates = True
    x_default = True

    def items(self):
        return ['home', 'shop', 'about', 'contact', 'terms']

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
        return Product.objects.filter(variants__available=True).distinct()

    def lastmod(self, obj):
        return obj.created_at

    def location(self, obj):
        return reverse('item', kwargs={'pk': obj.pk})


# Registered in vm/urls.py under the sitemap view.
sitemaps = {
    'static': StaticViewSitemap,
    'products': ProductSitemap,
}
