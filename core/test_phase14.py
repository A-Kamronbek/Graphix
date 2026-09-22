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

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from cart.models import Cart, CartItem
from payment.models import Order, PaymentOption
from product.models import Size, SizeChartRow

from .test_phase4 import make_product
from .test_phase6 import make_regions, make_user
from .test_phase7 import make_staff


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
