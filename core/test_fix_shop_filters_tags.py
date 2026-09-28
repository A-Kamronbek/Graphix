"""The shop offers one filter, size; tags are not shown to shoppers anywhere.

The owner's calls (§17 #303, #304). The shop sidebar carried the tag axes
(Uslub, Mavzu) and the category chips above the sizes; it carries the sizes
alone now. The product page's tag chips are gone too. Tags stay what the owner
sorts the catalogue with, what search matches, and what the Phase 13
recommender will read - so the search test here is the one that matters most:
hiding the chips must not have unplugged the tags.

A category or tag already in the address still narrows the list: the home page
and the footer link to categories, and an old tag link should land on
something rather than on an error.
"""
from django.test import TestCase
from django.urls import reverse

from product.models import Tag

from .test_phase4 import make_product


class ShopFilterTests(TestCase):
    """What the shop's filter form offers."""

    def setUp(self):
        self.product, self.variant = make_product('Filtrlanadi', stock=3)
        self.tag = Tag.objects.get(slug='anime')
        self.product.tags.add(self.tag)

    def page(self, **params):
        return self.client.get(reverse('shop'), params).content.decode()

    def test_size_is_the_one_filter_offered(self):
        html = self.page()
        self.assertIn('name="size" value="%d"' % self.variant.size_id, html)
        self.assertNotIn('<button type="submit" name="tag"', html)
        self.assertNotIn('<button type="submit" name="category"', html)

    def test_no_tag_name_is_shown(self):
        """Seeded tags exist and one is on a product; none of them is on the page."""
        html = self.page()
        for name in Tag.objects.values_list('name', flat=True):
            self.assertNotIn('>%s<' % name, html)

    def test_an_old_tag_link_still_narrows_the_list(self):
        other, _variant = make_product('Boshqasi', stock=3)
        html = self.page(tag='anime')
        self.assertIn(self.product.name, html)
        self.assertNotIn(other.name, html)
        self.assertIn('Filtrlarni tozalash', html)

    def test_search_still_reads_the_tags(self):
        """Typing a tag's name still finds the designs that carry it."""
        other, _variant = make_product('Boshqasi', stock=3)
        response = self.client.get(reverse('search'), {'q': self.tag.name})
        names = [p.name for p in response.context['products']]
        self.assertIn(self.product.name, names)
        self.assertNotIn(other.name, names)


class ProductPageTagTests(TestCase):
    """The product page no longer lists a design's tags."""

    def test_the_tags_are_not_on_the_page(self):
        product, _variant = make_product('Teglangan', stock=3)
        tag = Tag.objects.get(slug='anime')
        product.tags.add(tag)
        html = self.client.get(reverse('item', args=[product.slug])).content.decode()
        self.assertNotIn('?tag=', html)
        self.assertNotIn('>%s<' % tag.name, html)
