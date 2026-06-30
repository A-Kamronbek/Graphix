"""Sitemaps for search engines: static pages and purchasable products."""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from product.models import Product


class StaticViewSitemap(Sitemap):
    """Top-level public pages."""
    priority = 0.6
    changefreq = 'weekly'

    def items(self):
        return ['home', 'shop', 'about', 'contact', 'terms']

    def location(self, name):
        return reverse(name)


class ProductSitemap(Sitemap):
    """Detail pages for products that have at least one available variant."""
    changefreq = 'weekly'
    priority = 0.8

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
