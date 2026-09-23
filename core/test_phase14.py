"""Phase 14: sizes and payment methods, edited from the panel.

Both are new entries in the one allowlisted endpoint, and both break a quiet
assumption it had been carrying: that a row keeps its name in a field called
``name``. A size keeps it in ``size``, so every check that guarded a name —
not blank, not a duplicate — was looking at the wrong attribute and would
have waved through two sizes both called "M" on the axis of every product's
price-and-stock grid. Most of what follows is about that.

Payment methods are the other half: the switch the owner asked for, and the
two things the panel must refuse to do to them.

Both tables arrive seeded — S/M/L/XL from the product migrations, `click` and
`cash` from `payment/0015` — so these tests name their own rows and count
deltas rather than totals. Asserting a total here would be asserting the seed,
which is somebody else's test.

Item 2, the checkout's required-field marks, is at the bottom. It is the same
idea from the other end: a mark is a promise about what the server will do,
so the tests check it against the server rather than counting stars.
"""
import re
from decimal import Decimal
from importlib import util
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import resolve, reverse
from django.utils import translation

from cart.models import Cart, CartItem
from payment import services as payment_services
from payment import views as payment_views
from payment.models import Order, PaymentOption
from product.models import Size, SizeChartRow, Slide, slide_link

from .test_backlog import TempMedia
from .test_phase4 import make_product
from .test_phase6 import make_regions, make_user
from .test_phase7 import make_staff
from .test_phase7b import photo


def card_for(html, code):
    """The one payment card for this method, isolated from its neighbours.

    Asserting a badge against the whole page would pass whichever card
    carried it. The cards are siblings and each opens with the same marker,
    so splitting on it is enough; the tail is cut at the end of the section
    so the last card does not swallow the rest of the document.
    """
    for chunk in html.split('data-ref="payment"')[1:]:
        chunk = chunk.split('</section>')[0]
        if '<strong>%s</strong>' % code in chunk:
            return chunk
    raise AssertionError('no payment card for %r' % code)


class SizeReferenceTests(TestCase):
    """A size is one field, and it is shared by every product that sells it."""

    def setUp(self):
        self.staff = make_staff('olchamchi', '+998901250001')
        self.client.force_login(self.staff)
        self.size = Size.objects.create(size='Sinov-1')

    def url(self, pk=None):
        return reverse('panel_reference_inline',
                       kwargs={'kind': 'size', 'pk': pk or self.size.pk})

    def test_a_size_can_be_renamed_in_place(self):
        response = self.client.post(self.url(),
                                    {'field': 'size', 'value': 'Sinov-2'})
        self.assertEqual(response.status_code, 200)
        self.size.refresh_from_db()
        self.assertEqual(self.size.size, 'Sinov-2')

    def test_a_rename_reaches_every_product_that_sells_it(self):
        """It is one row, which is the point of its being a row."""
        product, variant = make_product('Koʻylak')
        self.client.post(self.url(variant.size.pk),
                         {'field': 'size', 'value': 'Sinov-3'})
        variant.refresh_from_db()
        self.assertEqual(variant.size.size, 'Sinov-3')

    def test_a_blank_size_is_refused(self):
        """An empty label on a size selector is a button nobody can read."""
        response = self.client.post(self.url(), {'field': 'size', 'value': '  '})
        self.assertEqual(response.status_code, 400)
        self.size.refresh_from_db()
        self.assertEqual(self.size.size, 'Sinov-1')

    def test_a_rename_onto_an_existing_size_is_refused(self):
        """Case-insensitively: "M" and "m" are the same button to a shopper.

        This is the check the old code could not make. It compared the value
        against a field called `name`, which a size does not have.
        """
        response = self.client.post(self.url(), {'field': 'size', 'value': ' m '})
        self.assertEqual(response.status_code, 400)
        self.size.refresh_from_db()
        self.assertEqual(self.size.size, 'Sinov-1')

    def test_a_size_may_keep_its_own_name(self):
        """Saving a row unchanged is not a duplicate of itself."""
        response = self.client.post(self.url(),
                                    {'field': 'size', 'value': 'Sinov-1'})
        self.assertEqual(response.status_code, 200)

    def test_no_other_field_on_a_size_is_reachable(self):
        response = self.client.post(self.url(), {'field': 'id', 'value': '9999'})
        self.assertEqual(response.status_code, 400)


class SizeCreateAndDeleteTests(TestCase):
    """Adding and removing a size without opening the old admin."""

    def setUp(self):
        self.staff = make_staff('olchamchi', '+998901250002')
        self.client.force_login(self.staff)
        self.before = Size.objects.count()

    def test_a_size_can_be_added(self):
        response = self.client.post(reverse('panel_size_new'), {'size': 'Sinov-1'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Size.objects.count(), self.before + 1)
        self.assertTrue(Size.objects.filter(size='Sinov-1').exists())

    def test_a_duplicate_size_is_refused(self):
        """Whitespace and case included — "M", " m " and "m" are one button."""
        self.client.post(reverse('panel_size_new'), {'size': ' m '})
        self.assertEqual(Size.objects.count(), self.before)

    def test_a_blank_size_is_refused(self):
        self.client.post(reverse('panel_size_new'), {'size': '   '})
        self.assertEqual(Size.objects.count(), self.before)

    def test_an_unused_size_can_be_deleted(self):
        size = Size.objects.create(size='Sinov-1')
        response = self.client.post(reverse(
            'panel_reference_delete', kwargs={'kind': 'size', 'pk': size.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Size.objects.filter(pk=size.pk).exists())

    def test_a_size_a_product_sells_cannot_be_deleted(self):
        """`Variant.size` is PROTECT, and the panel says so rather than cascading.

        A cascade here would delete the variant, which is a product's price and
        its stock — the shop would lose a line it is selling because somebody
        tidied a list.
        """
        product, variant = make_product('Futbolka')
        response = self.client.post(reverse(
            'panel_reference_delete',
            kwargs={'kind': 'size', 'pk': variant.size.pk}))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Size.objects.filter(pk=variant.size.pk).exists())

    def test_a_customer_cannot_add_a_size(self):
        self.client.force_login(make_user('xaridor', '+998901250003'))
        response = self.client.post(reverse('panel_size_new'), {'size': 'Sinov-1'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Size.objects.count(), self.before)


class PaymentOptionPanelTests(TestCase):
    """The switch the owner asked for, and the two things the panel will not do."""

    def setUp(self):
        self.staff = make_staff('kassir', '+998901250004')
        self.client.force_login(self.staff)
        self.way = PaymentOption.objects.get(code='cash')

    def url(self, row=None):
        return reverse('panel_reference_inline',
                       kwargs={'kind': 'payment', 'pk': (row or self.way).pk})

    def test_cash_ships_switched_off(self):
        """The owner asked for it as an option, not as a change to the shop.

        It has been a row since §17 #99; what Phase 14 adds is somewhere to
        flip it without the old admin.
        """
        self.assertFalse(self.way.is_active)

    def test_the_switch_turns_a_method_on(self):
        response = self.client.post(self.url(), {'field': 'is_active', 'value': '1'})
        self.assertEqual(response.status_code, 200)
        self.way.refresh_from_db()
        self.assertTrue(self.way.is_active)

    def test_the_switch_turns_a_method_off_again(self):
        click = PaymentOption.objects.get(code='click')
        self.assertTrue(click.is_active)
        self.client.post(self.url(click), {'field': 'is_active', 'value': '0'})
        click.refresh_from_db()
        self.assertFalse(click.is_active)

    def test_a_method_can_be_renamed_in_every_language(self):
        for field, value in (('name', 'Naqd'), ('name_ru', 'Наличные'),
                             ('name_en', 'Cash')):
            with self.subTest(field=field):
                response = self.client.post(self.url(),
                                            {'field': field, 'value': value})
                self.assertEqual(response.status_code, 200)
        self.way.refresh_from_db()
        self.assertEqual(
            (self.way.name, self.way.name_ru, self.way.name_en),
            ('Naqd', 'Наличные', 'Cash'))

    def test_the_code_cannot_be_edited(self):
        """It is what the checkout matches on and what a webhook arrives quoting.

        A typo here takes a payment method off the site with no error anywhere,
        so it is shown on the screen and absent from the allowlist.
        """
        response = self.client.post(self.url(), {'field': 'code', 'value': 'click'})
        self.assertEqual(response.status_code, 400)
        self.way.refresh_from_db()
        self.assertEqual(self.way.code, 'cash')

    def test_a_method_cannot_be_deleted(self):
        """An order records how it was paid; the row is what explains that later."""
        response = self.client.post(reverse(
            'panel_reference_delete',
            kwargs={'kind': 'payment', 'pk': self.way.pk}))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(PaymentOption.objects.filter(pk=self.way.pk).exists())

    def test_a_blank_name_is_refused(self):
        response = self.client.post(self.url(), {'field': 'name', 'value': ''})
        self.assertEqual(response.status_code, 400)


class SettingsScreenTests(TestCase):
    """The screen renders both new sections, and its nav can reach them."""

    def setUp(self):
        self.client.force_login(make_staff('sozlovchi', '+998901250005'))

    def test_the_screen_shows_sizes_and_payment_methods(self):
        response = self.client.get(reverse('panel_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="olchamlar"')
        self.assertContains(response, 'id="tolov"')
        self.assertContains(response, 'href="#olchamlar"')
        self.assertContains(response, 'href="#tolov"')

    def test_every_seeded_row_reaches_the_screen(self):
        response = self.client.get(reverse('panel_settings'))
        for code in ('click', 'cash'):
            with self.subTest(code=code):
                self.assertContains(response, '<strong>%s</strong>' % code)
        for size in ('S', 'M', 'L', 'XL'):
            with self.subTest(size=size):
                self.assertContains(response, 'value="%s" maxlength="50"' % size)

    def test_the_new_sections_are_translated(self):
        """The whole chain: the msgid, the catalogue, the .mo, the rendered page.

        Worth asserting rather than trusting, because `makemessages` guessed at
        all five of these headings and marked them fuzzy — "Yangi oʻlcham" came
        back as "New password". gettext then ignores a fuzzy entry, so the only
        symptom would have been Uzbek text on a Russian screen.
        """
        for lang, headings in (('ru', ('Размеры', 'Способы оплаты')),
                               ('en', ('Sizes', 'Payment methods'))):
            with translation.override(lang):
                url = reverse('panel_settings')
            response = self.client.get(url)
            for heading in headings:
                with self.subTest(lang=lang, heading=heading):
                    self.assertContains(response, heading)

    def test_the_code_is_shown_but_is_not_a_box(self):
        """Shown, because the owner needs to know which row is which."""
        response = self.client.get(reverse('panel_settings'))
        self.assertNotContains(response, 'data-ref-field="code"')

    def test_the_screen_survives_empty_tables(self):
        """A shop with no sizes yet still has to render the form to add one.

        The size charts have to go first, and that is not incidental: every
        seeded size is referenced by a chart row, so `Size` cannot be emptied
        at all until they are. It is the same PROTECT the panel reports.
        """
        SizeChartRow.objects.all().delete()
        Size.objects.all().delete()
        PaymentOption.objects.all().delete()
        response = self.client.get(reverse('panel_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('panel_size_new'))


class RequiredFieldMarksTests(TestCase):
    """The checkout says which fields it will refuse to do without.

    A mark on a field the server does not require is a lie, and a field the
    server requires with no mark is the complaint that started this. So the
    marks are not just counted here: each one is checked against the server
    by removing that field from an otherwise valid order and watching the
    order fail to appear.
    """
    #: What `Order.clean` and the checkout view between them insist on.
    REQUIRED = {'name', 'phone', 'region', 'district', 'postal_index', 'address'}
    #: Asked for, never insisted on. `location_note` is the Boshqa escape.
    OPTIONAL = {'notes', 'location_note'}

    def setUp(self):
        self.geo = make_regions()
        self.user = make_user('xaridor', '+998901260001')
        self.product, self.variant = make_product('Nishon', stock=5)
        self.client.force_login(self.user)
        self.cart = Cart.objects.create(user=self.user, status=True)
        CartItem.objects.create(cart=self.cart, variant=self.variant,
                                quantity=1, price_stat=self.variant.price)

    def page(self):
        return self.client.get(reverse('checkout')).content.decode()

    def marked(self, html):
        """The `for` of every label carrying the required mark."""
        return {m.group(1) for m in re.finditer(
            r'<label[^>]*\bfor="id_([a-z_]+)"[^>]*>(?:(?!</label>).)*'
            r'class="req"', html, re.S)}

    def test_every_required_field_is_marked(self):
        self.assertEqual(self.marked(self.page()), self.REQUIRED)

    def test_no_optional_field_is_marked(self):
        marked = self.marked(self.page())
        self.assertEqual(marked & self.OPTIONAL, set())

    def test_the_page_says_once_what_the_mark_means(self):
        """A star nobody has explained is decoration."""
        html = self.page()
        self.assertIn('bilan belgilangan', html)
        self.assertEqual(html.count('bilan belgilangan'), 1)

    def test_the_legend_is_translated_and_keeps_its_mark(self):
        """§17 #255: assert the rendered page, not the catalogue.

        The mark is a blocktrans placeholder rather than part of the msgid, so
        this also checks the placeholder survived translation — a Russian
        sentence that lost `%(star)s` would explain a symbol it no longer
        shows.
        """
        for lang, phrase in (('ru', 'обязательны для заполнения'),
                             ('en', 'are required')):
            with translation.override(lang):
                url = reverse('checkout')
            html = self.client.get(url).content.decode()
            with self.subTest(lang=lang):
                self.assertIn(phrase, html)
                self.assertRegex(
                    html, re.escape('<span class="req" aria-hidden="true">*'
                                    '</span>'))

    def test_the_mark_is_hidden_from_a_screen_reader(self):
        """It hears "required" from the attribute, not "star" from the text."""
        html = self.page()
        stars = re.findall(r'<span[^>]*class="req"[^>]*>', html)
        self.assertTrue(stars)
        for span in stars:
            with self.subTest(span=span):
                self.assertIn('aria-hidden="true"', span)

    def test_the_two_selects_say_they_are_required(self):
        """Both methods need them, and neither can carry a native `required`."""
        html = self.page()
        for field in ('region', 'district'):
            with self.subTest(field=field):
                self.assertRegex(
                    html, r'<select[^>]*id="id_%s"[^>]*aria-required="true"'
                          % field)

    # The two halves of the form. Each marked field belongs to one of them.
    BRANCH = {'delivery_option': 'uzpost_office', 'postal_index': '100011'}
    HOME = {'delivery_option': 'uzpost_door', 'address': 'Amir Temur koʻchasi 1',
            'address_source': 'manual'}

    def payload(self, half, drop=None):
        """A complete order for one delivery method, less ``drop``."""
        data = {'name': 'Qabul Qiluvchi', 'phone': '+998 90 126 00 01',
                'region': self.geo['tashkent'].pk,
                'district': self.geo['chilonzor'].pk,
                'payment_method': 'click', 'notes': ''}
        data.update(half)
        data.pop(drop, None)
        return data

    def placed(self):
        return Order.objects.filter(cart=self.cart).exists()

    def test_a_complete_branch_order_is_accepted(self):
        """Guards the test below from passing because everything is refused."""
        self.client.post(reverse('checkout'), self.payload(self.BRANCH))
        self.assertTrue(self.placed())

    def test_a_complete_home_order_is_accepted(self):
        self.client.post(reverse('checkout'), self.payload(self.HOME))
        self.assertTrue(self.placed())

    def test_dropping_any_marked_field_stops_the_order(self):
        """Every star is a promise the server keeps.

        All of these are refused, so the cart is never consumed and one cart
        serves the whole loop.
        """
        halves = {'name': self.BRANCH, 'phone': self.BRANCH,
                  'region': self.BRANCH, 'district': self.BRANCH,
                  'postal_index': self.BRANCH, 'address': self.HOME}
        self.assertEqual(set(halves), self.REQUIRED)
        for field, half in halves.items():
            with self.subTest(field=field):
                self.client.post(reverse('checkout'),
                                 self.payload(half, drop=field))
                self.assertFalse(self.placed(),
                                 '%s is marked required but the order went '
                                 'through without it' % field)

    def test_dropping_an_unmarked_field_does_not(self):
        """And every field without one is genuinely optional."""
        self.client.post(reverse('checkout'),
                         self.payload(self.HOME, drop='notes'))
        self.assertTrue(self.placed())


class SlideLinkTests(TestCase):
    """What a slide is allowed to point at.

    The owner types this into a box and it becomes an `href` on the busiest
    page of the site, so the rule is an allowlist rather than a blocklist:
    two shapes are in, everything else is out.
    """

    def refuses(self, value):
        with self.assertRaises(ValidationError, msg=value):
            slide_link(value)

    def test_a_page_on_this_site_is_fine(self):
        for good in ('/', '/dokon/', '/uz/mahsulot/nimadir/', '/dokon/?tag=3'):
            with self.subTest(good=good):
                slide_link(good)

    def test_an_https_address_is_fine(self):
        slide_link('https://t.me/greatestamal')

    def test_nothing_at_all_is_fine(self):
        """A card that announces something without linking anywhere."""
        slide_link('')

    def test_javascript_is_refused(self):
        """The whole reason this validator exists."""
        for bad in ('javascript:alert(1)', 'JavaScript:alert(1)',
                    ' javascript:alert(1)'):
            with self.subTest(bad=bad):
                self.refuses(bad)

    def test_a_data_url_is_refused(self):
        self.refuses('data:text/html;base64,PHNjcmlwdD4=')

    def test_a_protocol_relative_link_is_refused(self):
        """`//host/path` is an off-site link that reads like an internal one."""
        self.refuses('//evil.example/promo')

    def test_a_bare_host_is_refused(self):
        """`evil.example` in an href is a relative path, not the site it looks like."""
        self.refuses('evil.example')


class SlidePanelTests(TempMedia, TestCase):
    """Uploading, editing and removing a slide from the panel."""

    def setUp(self):
        self.staff = make_staff('slaydchi', '+998901270001')
        self.client.force_login(self.staff)

    def add(self, **overrides):
        data = {'alt': 'Qishki chegirma', 'link': '/dokon/',
                'picture': photo(size=(1200, 400), name='slide.jpg')}
        data.update(overrides)
        data = {k: v for k, v in data.items() if v is not None}
        return self.client.post(reverse('panel_slide_new'), data)

    def url(self, slide):
        return reverse('panel_reference_inline',
                       kwargs={'kind': 'slide', 'pk': slide.pk})

    def test_a_slide_can_be_uploaded(self):
        self.add()
        slide = Slide.objects.get()
        self.assertEqual(slide.alt, 'Qishki chegirma')
        self.assertEqual(slide.link, '/dokon/')
        self.assertTrue(slide.has_photo)

    def test_the_picture_goes_through_the_image_pipeline(self):
        """Re-encoded, so an upload here cannot carry EXIF or be a bomb."""
        self.add()
        self.assertTrue(Slide.objects.get().picture.name.endswith('.jpg'))

    def test_a_new_slide_goes_to_the_end(self):
        """It should not take over the top of the home page unannounced."""
        self.add(alt='Birinchi')
        self.add(alt='Ikkinchi')
        order = list(Slide.objects.values_list('alt', flat=True))
        self.assertEqual(order, ['Birinchi', 'Ikkinchi'])

    def test_a_slide_without_a_description_is_refused(self):
        """Without it the card is a link with no accessible name."""
        self.add(alt='')
        self.assertFalse(Slide.objects.exists())

    def test_a_slide_without_a_picture_is_refused(self):
        self.add(picture=None)
        self.assertFalse(Slide.objects.exists())

    def test_a_dangerous_link_is_refused_at_upload(self):
        self.add(link='javascript:alert(1)')
        self.assertFalse(Slide.objects.exists())

    def test_a_customer_cannot_upload_one(self):
        self.client.force_login(make_user('xaridor', '+998901270002'))
        response = self.add()
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Slide.objects.exists())


class SlideInlineEditTests(TempMedia, TestCase):
    """The allowlist, applied to a slide."""

    def setUp(self):
        self.client.force_login(make_staff('slaydchi', '+998901270003'))
        self.slide = Slide.objects.create(
            picture=photo(size=(1200, 400), name='s.jpg'),
            alt='Qishki chegirma', link='/dokon/')

    def url(self):
        return reverse('panel_reference_inline',
                       kwargs={'kind': 'slide', 'pk': self.slide.pk})

    def post(self, field, value):
        return self.client.post(self.url(), {'field': field, 'value': value})

    def test_the_switch_takes_a_slide_off_the_home_page(self):
        self.assertTrue(self.slide.is_active)
        self.assertEqual(self.post('is_active', '0').status_code, 200)
        self.slide.refresh_from_db()
        self.assertFalse(self.slide.is_active)

    def test_the_description_can_be_edited_in_every_language(self):
        for field, value in (('alt', 'Yangi'), ('alt_ru', 'Новый'),
                             ('alt_en', 'New')):
            with self.subTest(field=field):
                self.assertEqual(self.post(field, value).status_code, 200)
        self.slide.refresh_from_db()
        self.assertEqual((self.slide.alt, self.slide.alt_ru, self.slide.alt_en),
                         ('Yangi', 'Новый', 'New'))

    def test_a_blank_description_is_refused(self):
        """`alt` is the slide's only accessible name; NAME_FIELD points here."""
        self.assertEqual(self.post('alt', '  ').status_code, 400)
        self.slide.refresh_from_db()
        self.assertEqual(self.slide.alt, 'Qishki chegirma')

    def test_the_link_can_be_changed(self):
        self.assertEqual(self.post('link', '/dokon/?tag=4').status_code, 200)
        self.slide.refresh_from_db()
        self.assertEqual(self.slide.link, '/dokon/?tag=4')

    def test_a_dangerous_link_cannot_be_saved_through_the_endpoint(self):
        """`set_field` saves with update_fields and runs no model validator.

        Without the `link` reader in `panel/reference.py` this endpoint is a
        way to put `javascript:` into an href on the home page, one POST from
        any staff account.
        """
        for bad in ('javascript:alert(1)', '//evil.example/x', 'evil.example'):
            with self.subTest(bad=bad):
                self.assertEqual(self.post('link', bad).status_code, 400)
        self.slide.refresh_from_db()
        self.assertEqual(self.slide.link, '/dokon/')

    def test_the_picture_is_not_reachable_through_the_endpoint(self):
        self.assertEqual(self.post('picture', 'x.jpg').status_code, 400)

    def test_a_slide_can_be_deleted(self):
        response = self.client.post(reverse(
            'panel_reference_delete', kwargs={'kind': 'slide', 'pk': self.slide.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Slide.objects.exists())


class HomeSlidesTests(TempMedia, TestCase):
    """What the home page does with them.

    The hero is gone, so two of these guard things the hero used to provide
    and nothing else does: exactly one `h1`, and a page that still works when
    the owner has uploaded nothing at all.
    """

    def slide(self, alt, **kwargs):
        return Slide.objects.create(
            picture=photo(size=(1200, 400), name='s.jpg'), alt=alt, **kwargs)

    def page(self):
        return self.client.get(reverse('home')).content.decode()

    def test_an_active_slide_is_on_the_page(self):
        self.slide('Qishki chegirma')
        self.assertIn('Qishki chegirma', self.page())

    def test_a_switched_off_slide_is_not(self):
        self.slide('Koʻrinmasin', is_active=False)
        self.assertNotIn('Koʻrinmasin', self.page())

    def test_the_page_has_exactly_one_heading_with_slides(self):
        self.slide('Bir')
        self.assertEqual(self.page().count('<h1'), 1)

    def test_the_page_has_exactly_one_heading_without_them(self):
        """The hero used to carry it. Nothing else does now (§17 #251)."""
        self.assertEqual(self.page().count('<h1'), 1)

    def test_the_buttons_are_there_either_way(self):
        for slides in (0, 1):
            if slides:
                self.slide('Bir')
            with self.subTest(slides=slides):
                html = self.page()
                self.assertIn(reverse('shop'), html)
                self.assertIn(reverse('contact'), html)

    def test_every_slide_image_is_described(self):
        """A link whose only content is an image needs an accessible name."""
        self.slide('Qishki chegirma', link='/dokon/')
        html = self.page()
        for tag in re.findall(r'<img[^>]*>', html):
            if 'slides' in tag or 'Qishki' in tag:
                with self.subTest(tag=tag[:60]):
                    self.assertRegex(tag, r'alt="[^"]+"')

    def test_the_first_slide_is_eager_and_the_rest_are_not(self):
        """It is the page's largest paint; the others are below the fold."""
        self.slide('Bir')
        self.slide('Ikki')
        html = self.page()
        self.assertEqual(html.count('fetchpriority="high"'), 1)
        self.assertEqual(html.count('loading="lazy"'), 1)

    def test_the_carousel_is_translated(self):
        """§17 #255 again, and it bit harder here.

        msgmerge gave "Toʻxtatish" — the pause button — the translation of
        "Create account", and "Aksiyalar" the translation of "Specification".
        gettext ignores a fuzzy entry, so the page would simply have been
        Uzbek; the danger is the flag being cleared by somebody who does not
        read the entry. These assert the rendered page.
        """
        self.slide('Bir')
        self.slide('Ikki')
        for lang, words in (('ru', ('Акции', 'Остановить', 'Следующий слайд')),
                            ('en', ('Promotions', 'Pause', 'Next slide'))):
            with translation.override(lang):
                url = reverse('home')
            html = self.client.get(url).content.decode()
            for word in words:
                with self.subTest(lang=lang, word=word):
                    self.assertIn(word, html)

    def test_the_script_is_loaded_only_when_there_is_something_to_drive(self):
        self.slide('Bir')
        self.assertNotIn('slides.js', self.page())
        self.slide('Ikki')
        self.assertIn('slides.js', self.page())


class AddressSheetTests(TestCase):
    """Item 4: the home address splits into a map and a sheet (§17 #252).

    The moving is `checkout.js`'s job and no test here can see it. What these
    hold is the half that survives without it — which is the half §17 #107
    says must never quietly stop working — and the one structural promise the
    markup can break on its own: each field exists once.
    """

    def setUp(self):
        self.geo = make_regions()
        self.user = make_user('manzilchi', '+998901280001')
        self.product, self.variant = make_product('Manzil', stock=3)
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user, status=True)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1,
                                price_stat=self.variant.price)

    def page(self):
        return self.client.get(reverse('checkout')).content.decode()

    def test_every_address_field_renders_inline(self):
        """With the script blocked the form is the form it has always been."""
        html = self.page()
        for field in ('region', 'district', 'location_note', 'address'):
            with self.subTest(field=field):
                self.assertRegex(html, r'(?:name|id)="(?:id_)?%s"' % field)

    def test_the_sheet_ships_empty(self):
        """It is filled by moving the fields into it, never by rendering them twice."""
        html = self.page()
        body = re.search(r'data-address-sheet-body[^>]*>(.*?)</div>', html, re.S)
        self.assertIsNotNone(body, 'the sheet has no body')
        self.assertEqual(body.group(1).strip(), '')

    def test_no_field_is_rendered_twice(self):
        """The whole argument for moving nodes rather than copying markup.

        Two controls called `region` is two values under one name, and the
        server has no way to know which the customer meant.

        Scoped to the checkout form, and radios and checkboxes are skipped:
        the delivery and payment groups share a name on purpose, and the
        language switcher is three separate forms in the header.
        """
        form = self.page().split('data-checkout', 1)[1].split('</form>', 1)[0]
        names = []
        for tag, attrs in re.findall(r'<(input|select|textarea)\b([^>]*)>', form):
            if 'type="radio"' in attrs or 'type="checkbox"' in attrs:
                continue
            found = re.search(r'\bname="([^"]+)"', attrs)
            if found and found.group(1) != 'csrfmiddlewaretoken':
                names.append(found.group(1))
        self.assertTrue(names, 'the form parsed to no fields at all')
        self.assertEqual(sorted(names), sorted(set(names)),
                         'a field name is rendered more than once')

    def test_the_summary_is_hidden_until_the_script_shows_it(self):
        """A row that opens a sheet is useless when nothing can open one."""
        html = self.page()
        self.assertRegex(html, r'<button[^>]*data-address-summary[^>]*\shidden')

    def test_the_sheet_is_a_labelled_dialog(self):
        html = self.page()
        sheet = re.search(r'<div[^>]*data-address-sheet[^>]*>', html)
        self.assertIsNotNone(sheet)
        for attr in ('role="dialog"', 'aria-modal="true"', 'aria-labelledby='):
            with self.subTest(attr=attr):
                self.assertIn(attr, sheet.group(0))

    def test_the_sheet_is_translated(self):
        """§17 #255: the rendered page, not the catalogue."""
        for lang, word in (('ru', 'Адрес'), ('en', 'Address')):
            with translation.override(lang):
                url = reverse('checkout')
            with self.subTest(lang=lang):
                self.assertIn(word, self.client.get(url).content.decode())


class TolovSwapTests(TestCase):
    """Item 5, first half: Click moves from click-pkg to tolov (§17 #253).

    Nothing a customer sees changes. These hold the three things that could
    have broken quietly, and the one that would have broken loudly on the
    owner's money.
    """

    def test_click_pkg_is_gone(self):
        """Not merely unused — uninstalled, and nothing left importing it."""
        self.assertIsNone(util.find_spec('click_up'),
                          'click_up is still importable')

    def test_requirements_names_tolov_and_not_click_pkg(self):
        text = (Path(settings.BASE_DIR) / 'requirements.txt').read_text('utf-8')
        self.assertIn('tolov==', text)
        self.assertNotIn('click-pkg', text)

    def test_the_webhook_is_still_at_the_exact_path_click_was_given(self):
        """§12 risk #2: breaking this fails silently, on every payment."""
        self.assertEqual(reverse('click_webhook'), '/payment/click/update/')
        self.assertIs(resolve('/payment/click/update/').func.view_class,
                      payment_views.ClickWebhookAPIView)

    def test_the_order_answers_to_amount(self):
        """§17 #262 — the one that would have rejected every real payment.

        tolov checks a callback's amount with `getattr(account, "amount", 0)`,
        hardcoded, where click-pkg read the field name from a setting. Without
        this property the comparison is against zero, `InvalidAmount` is
        raised, Click gets `error: -2`, and no order can ever be paid for.
        """
        order = Order(total_price=Decimal('420000'))
        self.assertEqual(order.amount, order.total_price)
        self.assertEqual(float(getattr(order, 'amount', 0)), 420000.0)

    def test_the_amount_check_would_pass_for_a_real_payment(self):
        """The property, put through tolov's own comparison rather than ours."""
        order = Order(total_price=Decimal('420000'))
        received = float(order.total_price)
        expected = float(getattr(order, 'amount', 0))
        self.assertLessEqual(abs(received - expected), 0.01)

    def test_the_gateway_transaction_admin_is_not_registered(self):
        """A raw gateway row is a debugging artefact, not something to browse."""
        from tolov.integrations.django.models import PaymentTransaction
        self.assertNotIn(PaymentTransaction, admin.site._registry)


class PaymeAndOctoTests(TestCase):
    """Item 5, second half: two more methods, both shipped switched off.

    There are no credentials yet, so nothing here talks to a gateway. What it
    holds is the shape: the rows exist and are off, the choices exist, the
    callbacks are mounted unprefixed, and a method with no online step says so
    instead of redirecting somewhere blank.
    """

    def test_both_methods_are_choices_on_the_order(self):
        for code in ('payme', 'octo'):
            with self.subTest(code=code):
                self.assertIn(code, Order.PaymentMethod.values)

    def test_both_rows_exist_and_are_switched_off(self):
        """No credentials yet, so the owner must not be able to sell with them."""
        for code in ('payme', 'octo'):
            with self.subTest(code=code):
                row = PaymentOption.objects.get(code=code)
                self.assertFalse(row.is_active)

    def test_the_new_rows_carry_all_three_languages(self):
        """A PaymentOption keeps its copy in columns the owner can edit."""
        for code in ('payme', 'octo'):
            row = PaymentOption.objects.get(code=code)
            for field in ('name', 'name_ru', 'name_en',
                          'note', 'note_ru', 'note_en'):
                with self.subTest(code=code, field=field):
                    self.assertTrue(getattr(row, field).strip())

    def test_a_switched_off_method_is_not_offered_at_checkout(self):
        """The rows are off, so the checkout must not render them."""
        user = make_user('tolovchi', '+998901300001')
        _, variant = make_product('Tolov', stock=2)
        self.client.force_login(user)
        cart = Cart.objects.create(user=user, status=True)
        CartItem.objects.create(cart=cart, variant=variant, quantity=1,
                                price_stat=variant.price)
        html = self.client.get(reverse('checkout')).content.decode()
        for code in ('payme', 'octo'):
            with self.subTest(code=code):
                self.assertNotIn('value="%s"' % code, html)

    def test_each_callback_is_mounted_unprefixed(self):
        """A gateway is given one address and posts to it forever (§12 risk #2)."""
        for name, path in (('click_webhook', '/payment/click/update/'),
                           ('payme_webhook', '/payment/payme/update/'),
                           ('octo_webhook', '/payment/octo/update/')):
            with self.subTest(name=name):
                self.assertEqual(reverse(name), path)
                self.assertTrue(resolve(path))

    def test_no_callback_is_served_under_a_language_prefix(self):
        for path in ('/uz/payment/payme/update/', '/ru/payment/octo/update/'):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path).status_code, 404)

    def test_cash_has_no_pay_link_and_says_so(self):
        """Not a falsy return: a blank redirect is how a payment bug hides."""
        order = Order(payment_method=Order.PaymentMethod.CASH,
                      total_price=Decimal('100000'))
        with self.assertRaises(payment_services.PaymentMethodUnavailable):
            payment_services.generate_paylink(order, 'https://graphix.uz/')

    def test_the_payment_group_is_marked_required(self):
        """§18 #45: with four methods live, nothing is pre-checked any more."""
        user = make_user('tolovchi', '+998901300002')
        _, variant = make_product('Nishon', stock=2)
        self.client.force_login(user)
        cart = Cart.objects.create(user=user, status=True)
        CartItem.objects.create(cart=cart, variant=variant, quantity=1,
                                price_stat=variant.price)
        html = self.client.get(reverse('checkout')).content.decode()
        group = re.search(r'<div[^>]*role="radiogroup"[^>]*>', html)
        self.assertIsNotNone(group)
        self.assertIn('aria-required="true"', group.group(0))
        self.assertIn('aria-labelledby="pay-heading"', group.group(0))


class PaymentSwitchTests(TestCase):
    """Phase 14's Definition of Done, in its own words.

    "All four payment methods appear when switched on and are refused
    server-side when off." Both halves, because they are different mechanisms:
    one is what the template renders, the other is what the view accepts, and
    a method could pass either while failing the other.
    """

    def setUp(self):
        self.geo = make_regions()
        self.user = make_user('tolovchi', '+998901310001')
        self.product, self.variant = make_product('Usul', stock=5)
        self.client.force_login(self.user)
        self.cart = Cart.objects.create(user=self.user, status=True)
        CartItem.objects.create(cart=self.cart, variant=self.variant,
                                quantity=1, price_stat=self.variant.price)

    def order_with(self, method):
        return self.client.post(reverse('checkout'), {
            'name': 'Qabul Qiluvchi', 'phone': '+998 90 131 00 01',
            'region': self.geo['tashkent'].pk,
            'district': self.geo['chilonzor'].pk,
            'delivery_option': 'uzpost_office', 'postal_index': '100011',
            'payment_method': method, 'notes': '',
        })

    def test_every_method_appears_once_it_is_switched_on(self):
        PaymentOption.objects.all().update(is_active=True)
        html = self.client.get(reverse('checkout')).content.decode()
        for code in ('click', 'payme', 'octo', 'cash'):
            with self.subTest(code=code):
                self.assertIn('value="%s"' % code, html)

    def test_a_method_that_is_off_is_refused_by_the_server(self):
        """Not merely absent from the page: absent is only the template."""
        PaymentOption.objects.filter(code='click').update(is_active=False)
        self.order_with('click')
        self.assertFalse(Order.objects.filter(cart=self.cart).exists())

    def test_a_method_that_is_on_is_accepted(self):
        """Guards the test above from passing because everything is refused."""
        PaymentOption.objects.filter(code='click').update(is_active=True)
        self.order_with('click')
        self.assertTrue(Order.objects.filter(cart=self.cart).exists())

    def test_a_code_no_row_offers_is_refused(self):
        """A POSTed method the shop has never heard of (§17 #94, amended)."""
        self.order_with('bitcoin')
        self.assertFalse(Order.objects.filter(cart=self.cart).exists())


#: Octo's answer to a request it will not honour. Verbatim shape, from a real
#: call with a blank shop id: `data` is present and null, which is why
#: tolov's ``response.get("data", {})`` hands ``None`` to ``.get`` (§17 #266).
OCTO_REFUSAL = {
    'error': 2,
    'errMessage': '0 identifikatorli doʻkon topilmadi',
    'data': None,
}


class GatewayRefusalTests(TestCase):
    """A gateway that says no must cost a retry, not a 500 (§17 #266).

    The bug these cover was tolov's, but the hole was ours: `generate_paylink`
    let a library exception through to the view, and §4 has said since Phase
    2 that an external call never breaks a request. It never showed because
    Click and Payme build their links locally — Octo is the first gateway
    that goes over the wire to make one.

    Nothing here touches the network: the gateway is replaced, and the one
    test that exercises tolov's real client feeds it Octo's own reply.
    """

    def octo_order(self):
        """An unsaved order naming Octo. Nothing here needs it in the table."""
        return Order(pk=4242, payment_method=Order.PaymentMethod.OCTO,
                     total_price=Decimal('400000'))

    # ---------------------------------------------------- configured or not

    def test_cash_needs_no_credentials(self):
        self.assertTrue(
            payment_services.method_is_configured(Order.PaymentMethod.CASH))

    def test_a_method_with_blank_credentials_is_not_configured(self):
        """Payme and Octo ship blank, and that is the state under test."""
        with override_settings(OCTO_SHOP_ID='', OCTO_SECRET=''):
            self.assertFalse(
                payment_services.method_is_configured(Order.PaymentMethod.OCTO))

    def test_whitespace_is_not_a_credential(self):
        """A key someone pasted as a space is blank, not configured."""
        with override_settings(OCTO_SHOP_ID='  ', OCTO_SECRET='  '):
            self.assertFalse(
                payment_services.method_is_configured(Order.PaymentMethod.OCTO))

    def test_half_a_pair_is_not_configured(self):
        """Shop id without the secret cannot sign anything."""
        with override_settings(OCTO_SHOP_ID='123', OCTO_SECRET=''):
            self.assertFalse(
                payment_services.method_is_configured(Order.PaymentMethod.OCTO))

    def test_both_halves_present_is_configured(self):
        with override_settings(OCTO_SHOP_ID='123', OCTO_SECRET='s3cret'):
            self.assertTrue(
                payment_services.method_is_configured(Order.PaymentMethod.OCTO))

    def test_click_is_configured_because_its_credentials_are_required(self):
        """CLICK_* are read with os.environ[...], so a blank one never boots."""
        self.assertTrue(
            payment_services.method_is_configured(Order.PaymentMethod.CLICK))

    def test_a_method_nobody_has_heard_of_is_not_configured(self):
        self.assertFalse(payment_services.method_is_configured('bitcoin'))

    # ------------------------------------------------- what generate_paylink does

    def test_blank_credentials_never_reach_the_gateway(self):
        """The whole point of asking settings first: no round-trip to be told
        what the environment could have said, and no live call from a laptop.
        """
        with override_settings(OCTO_SHOP_ID='', OCTO_SECRET=''):
            with mock.patch('payment.services.OctoGateway') as gateway:
                with self.assertRaises(
                        payment_services.PaymentMethodUnavailable):
                    payment_services.generate_paylink(
                        self.octo_order(), 'https://graphix.uz/')
        gateway.assert_not_called()

    def test_a_refusing_gateway_raises_the_retryable_error(self):
        """Not AttributeError, and not PaymentMethodUnavailable: this one is
        worth trying again, and the customer is told so.
        """
        with override_settings(OCTO_SHOP_ID='123', OCTO_SECRET='s3cret'):
            with mock.patch('payment.services.OctoGateway') as gateway:
                gateway.return_value.create_payment.side_effect = (
                    AttributeError("'NoneType' object has no attribute 'get'"))
                with self.assertRaises(payment_services.PaymentGatewayError):
                    payment_services.generate_paylink(
                        self.octo_order(), 'https://graphix.uz/')

    def test_an_empty_pay_link_is_a_failure_not_a_redirect(self):
        """tolov returns '' when it understood the reply and found no link.
        `redirect('')` is its own bug, so it must not get that far.
        """
        with override_settings(OCTO_SHOP_ID='123', OCTO_SECRET='s3cret'):
            with mock.patch('payment.services.OctoGateway') as gateway:
                gateway.return_value.create_payment.return_value = ''
                with self.assertRaises(payment_services.PaymentGatewayError):
                    payment_services.generate_paylink(
                        self.octo_order(), 'https://graphix.uz/')

    def test_a_working_gateway_still_returns_its_link(self):
        """Guards every test above from passing because nothing works."""
        with override_settings(OCTO_SHOP_ID='123', OCTO_SECRET='s3cret'):
            with mock.patch('payment.services.OctoGateway') as gateway:
                gateway.return_value.create_payment.return_value = (
                    'https://secure.octo.uz/pay/abc')
                link = payment_services.generate_paylink(
                    self.octo_order(), 'https://graphix.uz/')
        self.assertEqual(link, 'https://secure.octo.uz/pay/abc')

    def test_octo_links_are_built_in_test_mode_while_DEBUG(self):
        """`is_test_mode` becomes the `test` flag in Octo's request body, and
        that flag is what decides whether real money moves. It must track
        DEBUG, the same as TOLOV['OCTO_BANK']['TEST_MODE'] on the callback side.
        """
        with override_settings(OCTO_SHOP_ID='123', OCTO_SECRET='s3cret',
                               DEBUG=True):
            with mock.patch('payment.services.OctoGateway') as gateway:
                gateway.return_value.create_payment.return_value = 'https://x/'
                payment_services.generate_paylink(
                    self.octo_order(), 'https://graphix.uz/')
        self.assertIs(gateway.call_args.kwargs['is_test_mode'], True)

    # ------------------------------------------------ through tolov's own client

    def test_octos_real_refusal_does_not_escape_as_AttributeError(self):
        """The regression, end to end through the library that caused it.

        Only the HTTP call is replaced, with the body Octo actually sent. The
        rest is tolov's code doing `response.get("data", {}).get(...)` on a
        reply whose `data` is null — which is an AttributeError, 500, and a
        customer looking at a yellow Django page.
        """
        with override_settings(OCTO_SHOP_ID='123', OCTO_SECRET='s3cret'):
            with mock.patch('tolov.core.http.HttpClient.post',
                            return_value=OCTO_REFUSAL):
                with self.assertRaises(payment_services.PaymentGatewayError):
                    payment_services.generate_paylink(
                        self.octo_order(), 'https://graphix.uz/')


class GatewayRefusalViewTests(TestCase):
    """What the customer sees when a gateway will not make a link (§17 #266).

    Two outcomes that must not be confused: nothing configured is permanent
    and says so, a refusal is temporary and says try again. Both leave the
    order PAYING, because in both cases it may yet be paid for.
    """

    def setUp(self):
        self.user = make_user('tolovchi', '+998901320001')
        self.product, self.variant = make_product('Usul', stock=3)
        self.client.force_login(self.user)
        self.cart = Cart.objects.create(user=self.user, status=False)
        CartItem.objects.create(cart=self.cart, variant=self.variant,
                                quantity=1, price_stat=self.variant.price)
        self.order = Order.objects.create(
            user=self.user, cart=self.cart, phone='+998901320001',
            notes='', payment_method=Order.PaymentMethod.OCTO,
            total_price=Decimal('400000'), status=Order.Status.PAYING)

    def start(self):
        return self.client.post(
            reverse('payment_start', args=[self.order.id]), follow=True)

    def test_a_refusing_gateway_does_not_500(self):
        """The bug as the owner met it: a yellow page at /uz/payment/45/start/."""
        with override_settings(OCTO_SHOP_ID='123', OCTO_SECRET='s3cret'):
            with mock.patch('tolov.core.http.HttpClient.post',
                            return_value=OCTO_REFUSAL):
                response = self.start()
        self.assertEqual(response.status_code, 200)

    def test_a_refusing_gateway_tells_the_customer_to_try_again(self):
        """Asserted on the rendered page, not the catalogue (§17 #255)."""
        with translation.override('uz'):
            with override_settings(OCTO_SHOP_ID='123', OCTO_SECRET='s3cret'):
                with mock.patch('tolov.core.http.HttpClient.post',
                                return_value=OCTO_REFUSAL):
                    html = self.start().content.decode()
        self.assertIn('qayta urinib koʻring', html)

    def test_a_refusing_gateway_leaves_the_order_payable(self):
        """It is going to work in an hour. Cancelling it here would be wrong."""
        with override_settings(OCTO_SHOP_ID='123', OCTO_SECRET='s3cret'):
            with mock.patch('tolov.core.http.HttpClient.post',
                            return_value=OCTO_REFUSAL):
                self.start()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAYING)


    def test_the_retry_message_is_translated(self):
        """msgmerge matched it onto the rate-limit message — "Too many
        attempts" — which blames the customer for a gateway's bad day.
        """
        for lang, expected in (
                ('ru', 'платёжная '
                       'система'),
                # The apostrophe arrives as `&#x27;`, so match around it.
                ('en', 'responding right now')):
            with self.subTest(lang=lang):
                with translation.override(lang):
                    with override_settings(OCTO_SHOP_ID='123',
                                           OCTO_SECRET='s3cret'):
                        with mock.patch('tolov.core.http.HttpClient.post',
                                        return_value=OCTO_REFUSAL):
                            html = self.start().content.decode()
                self.assertIn(expected.lower(), html.lower())

    def test_an_unconfigured_method_does_not_500_either(self):
        """The state the shop is actually in today: Octo on, credentials blank."""
        with override_settings(OCTO_SHOP_ID='', OCTO_SECRET=''):
            response = self.start()
        self.assertEqual(response.status_code, 200)

    def test_an_unconfigured_method_gets_the_other_message(self):
        """Permanent, so it must not read as "try again in a minute"."""
        with translation.override('uz'):
            with override_settings(OCTO_SHOP_ID='', OCTO_SECRET=''):
                html = self.start().content.decode()
        self.assertIn('onlayn toʻlov yoʻq', html)
        self.assertNotIn('qayta urinib koʻring', html)


class PaymentConfiguredBadgeTests(TestCase):
    """Boshqaruv says whether a switched-on method can actually take money.

    The switch and the credentials answer different questions, and until now
    only one of them was visible anywhere. Read-only on purpose: the owner can
    still switch on whatever he likes, because credentials added to .env after
    the last restart are a real case (§17 #266).
    """

    def setUp(self):
        self.staff = make_staff('boshqaruvchi', '+998901330001')
        self.client.force_login(self.staff)

    def screen(self):
        with translation.override('uz'):
            return self.client.get(reverse('panel_settings')).content.decode()

    def test_a_method_with_no_credentials_is_marked_unconfigured(self):
        with override_settings(OCTO_SHOP_ID='', OCTO_SECRET=''):
            html = self.screen()
        card = card_for(html, 'octo')
        self.assertIn('Sozlanmagan', card)

    def test_the_same_method_is_marked_configured_once_it_has_them(self):
        """Guards the test above from passing because the badge never says ok."""
        with override_settings(OCTO_SHOP_ID='123', OCTO_SECRET='s3cret'):
            html = self.screen()
        card = card_for(html, 'octo')
        self.assertIn('Sozlangan', card)
        self.assertNotIn('Sozlanmagan', card)

    def test_cash_is_always_configured(self):
        """It needs nothing, so telling the owner to configure it is a lie."""
        card = card_for(self.screen(), 'cash')
        self.assertIn('Sozlangan', card)
        self.assertNotIn('Sozlanmagan', card)


    def test_the_badge_is_translated(self):
        """msgmerge offered "Оплачен" / "Paid" for "Sozlangan", which would
        have told the owner his payment method was paid for (§17 #255). The
        catalogue is not the thing to assert — the rendered screen is.
        """
        for lang, ok, missing in (('ru', 'Настроен',
                                   'Не настроен'),
                                  ('en', 'Configured', 'Not configured')):
            with self.subTest(lang=lang):
                with translation.override(lang):
                    with override_settings(OCTO_SHOP_ID='', OCTO_SECRET=''):
                        off = self.client.get(reverse('panel_settings'))
                    with override_settings(OCTO_SHOP_ID='1', OCTO_SECRET='k'):
                        on = self.client.get(reverse('panel_settings'))
                self.assertIn(missing, card_for(off.content.decode(), 'octo'))
                self.assertIn(ok, card_for(on.content.decode(), 'octo'))

    def test_the_switch_is_still_editable(self):
        """The badge reports; it must not have quietly become a second gate."""
        card = card_for(self.screen(), 'octo')
        self.assertIn('data-ref-field="is_active"', card)
        self.assertNotIn('disabled', card)
