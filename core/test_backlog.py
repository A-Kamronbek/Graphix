"""The backlog cleared before Phase 9 (§18 #8, #23, #28, #29, #33, #38, #39).

Kamronbek's pass before Phase 9 found three things on screens he uses: the
panel's dates in the browser's American order, a cancelled order named by its
database id, and Uzbek months written with a capital. Rechecking the backlog
found five more worth doing now rather than in the phase each was parked in,
and the recheck itself found that an unverified account could not reach the
code page in Russian or English. Each class names the decision it holds in
place (§17 #216-#225).
"""
import io
import json
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, models, transaction
from django.db.models import ProtectedError
from django.forms import modelform_factory
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation
from PIL import Image

from core.templatetags.date_tags import month_case
from core.templatetags.form_tags import form_messages
from payment.models import Order
from product import admin as product_admin
from product import images
from product.models import ImageP, Product, Review, ReviewImage, SizeChart
from user.services import delete_if_disposable

from .test_phase4 import make_product
from .test_phase6 import make_user
from .test_phase7 import make_staff
from .test_phase12 import make_order, photo

LANGS = ('uz', 'ru', 'en')
ROOT = Path(settings.BASE_DIR)
TEMPLATES = ROOT / 'templates'


def at(lang, name, *args, **kwargs):
    """``reverse`` in ``lang``: every page carries its language's prefix."""
    with translation.override(lang):
        return reverse(name, args=args, kwargs=kwargs or None)


def jpeg(name='rasm.jpg'):
    """A small, real JPEG, ready to be saved into an ImageField."""
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), (40, 30, 20)).save(buf, format='JPEG')
    return ContentFile(buf.getvalue(), name=name)


def superuser(username, phone):
    """A staff account that may use the Django admin."""
    user = make_staff(username, phone)
    user.is_superuser = True
    user.save(update_fields=['is_superuser'])
    return user


def local(year, month, day, hour=12):
    """An aware datetime in the shop's own time zone."""
    return timezone.make_aware(datetime(year, month, day, hour))


class TempMedia:
    """Mixin: uploads go to a throwaway folder, never into ``media/``."""

    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.mkdtemp(prefix='gx-media-')
        cls._media_override = override_settings(MEDIA_ROOT=cls._media)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)


# ------------------------------------------------------------------ #39
class CancelMessageTests(TestCase):
    """A cancelled order is named by its GX- number, never by its id (§17 #216)."""

    SAID = {'uz': '{no} raqamli buyurtma bekor qilindi.',
            'ru': 'Заказ {no} отменён.',
            'en': 'Order {no} has been cancelled.'}

    def setUp(self):
        self.user = make_user('bekorchi', '+998901300001')
        _, self.variant = make_product('Bekor', stock=3)
        self.client.force_login(self.user)

    def test_the_message_names_the_order_number_in_every_language(self):
        for lang in LANGS:
            with self.subTest(lang=lang):
                order = make_order(self.user, self.variant, status='paying')
                response = self.client.post(at(lang, 'order_cancel', order.pk), follow=True)
                shown = [str(m) for m in response.context['messages']]
                self.assertEqual(shown, [self.SAID[lang].format(no=order.order_no)])
                self.assertTrue(order.order_no.startswith('GX-'))
                self.assertNotIn(f'#{order.pk}', shown[0])


# ------------------------------------------------------------------ #33
class OrdersOutliveTheirCustomerTests(TestCase):
    """Deleting an account never deletes its orders (§17 #219)."""

    def setUp(self):
        _, self.variant = make_product('Saqlanadi', stock=5)

    def test_the_field_is_protect(self):
        field = Order._meta.get_field('user')
        self.assertIs(field.remote_field.on_delete, models.PROTECT)

    def test_an_account_with_an_order_cannot_be_deleted(self):
        user = make_user('xaridor', '+998901300011')
        order = make_order(user, self.variant)
        with self.assertRaises(ProtectedError):
            user.delete()
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=user.pk).exists())

    def test_an_account_without_orders_still_can_be(self):
        user = make_user('bosh', '+998901300012')
        user.delete()
        self.assertFalse(get_user_model().objects.filter(pk=user.pk).exists())

    def test_the_admin_refuses_and_keeps_both(self):
        user = make_user('admindan', '+998901300013')
        order = make_order(user, self.variant)
        self.client.force_login(superuser('bosh-admin', '+998901300014'))
        response = self.client.post(reverse('admin:user_user_delete', args=[user.pk]),
                                    {'post': 'yes'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['protected'])
        self.assertTrue(get_user_model().objects.filter(pk=user.pk).exists())
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())

    def test_an_abandoned_signup_with_an_order_is_still_left_alone(self):
        """The guard that already stood in front of the delete (§12 risk #4)."""
        user = make_user('tasdiqsiz', '+998901300015', verified=False)
        make_order(user, self.variant, status='paying')
        self.assertFalse(delete_if_disposable(user))
        self.assertTrue(get_user_model().objects.filter(pk=user.pk).exists())


# ------------------------------------------------------------------ #38
class PanelDateTests(TestCase):
    """The orders filter reads and shows dates day first (§17 #217)."""

    def setUp(self):
        self.client.force_login(make_staff('sana', '+998901300021'))

    def filters(self, **params):
        return self.client.get(reverse('panel_orders'), params).context['filters']

    def test_day_first_is_how_a_date_is_read_and_shown(self):
        for typed, shown in (('16/09/2026', '16/09/2026'), ('16.09.2026', '16/09/2026'),
                             ('1/9/2026', '01/09/2026'), (' 16/09/2026 ', '16/09/2026'),
                             ('2026-09-16', '16/09/2026')):
            with self.subTest(typed=typed):
                self.assertEqual(self.filters(since=typed)['since'], shown)

    def test_the_american_order_is_refused_not_misread(self):
        self.assertEqual(self.filters(until='09/16/2026')['until'], '')

    def test_the_range_filters_on_the_shop_s_own_days(self):
        user = make_user('sanachi', '+998901300022')
        _, variant = make_product('Sanali', stock=5)
        for day in (9, 10, 16, 17):
            order = make_order(user, variant)
            Order.objects.filter(pk=order.pk).update(created_at=local(2026, 9, day))
        response = self.client.get(reverse('panel_orders'),
                                   {'since': '10/09/2026', 'until': '16/09/2026'})
        self.assertEqual(response.context['total'], 2)

    def test_the_fields_are_text_with_the_calendar_behind_them(self):
        html = self.client.get(reverse('panel_orders')).content.decode()
        for name in ('since', 'until'):
            with self.subTest(field=name):
                tag = re.search(r'<input[^>]*name="%s"[^>]*>' % name, html).group(0)
                self.assertIn('type="text"', tag)
                self.assertIn('placeholder="kk/oo/yyyy"', tag)
                self.assertIn('pattern="', tag)
        self.assertEqual(html.count('data-date-pick'), 2)
        self.assertEqual(html.count('data-date-native'), 2)
        self.assertIn('href="#i-calendar"', html)

    def test_the_pattern_takes_what_the_view_reads_day_first(self):
        html = self.client.get(reverse('panel_orders')).content.decode()
        pattern = re.search(r'name="since"[^>]*pattern="([^"]+)"', html).group(1)
        for value in ('16/09/2026', '16.09.2026', '1/9/2026'):
            self.assertTrue(re.fullmatch(pattern, value), value)
        for value in ('2026-09-16', '16-09-2026', '16/09/26', 'abc'):
            self.assertFalse(re.fullmatch(pattern, value), value)

    def test_the_format_is_written_in_each_language(self):
        for lang, hint in (('uz', 'kk/oo/yyyy'), ('ru', 'дд/мм/гггг'), ('en', 'dd/mm/yyyy')):
            with self.subTest(lang=lang):
                html = self.client.get(at(lang, 'panel_orders')).content.decode()
                self.assertIn(f'placeholder="{hint}"', html)
                self.assertIn('16/09/2026', re.search(r'name="since"[^>]*title="([^"]+)"',
                                                      html).group(1))


class MonthCaseTests(TestCase):
    """A month in running Uzbek text is written in lower case (§17 #218)."""

    def test_uzbek_is_lowered(self):
        with translation.override('uz'):
            self.assertEqual(month_case('16 Sentabr 2026'), '16 sentabr 2026')
            self.assertEqual(month_case('16 Sentabr, 09:30'), '16 sentabr, 09:30')

    def test_russian_and_english_are_left_alone(self):
        for lang, text in (('ru', '16 сентября 2026'), ('en', '16 September 2026')):
            with self.subTest(lang=lang), translation.override(lang):
                self.assertEqual(month_case(text), text)

    def test_the_order_page_says_sentabr(self):
        user = make_user('oylik', '+998901300031')
        _, variant = make_product('Oylik', stock=5)
        order = make_order(user, variant)
        Order.objects.filter(pk=order.pk).update(created_at=local(2026, 9, 16))
        self.client.force_login(user)
        for lang, date_text in (('uz', '16 sentabr 2026'), ('ru', '16 сентября 2026'),
                                ('en', '16 September 2026')):
            with self.subTest(lang=lang):
                html = self.client.get(at(lang, 'order_detail', order.pk)).content.decode()
                self.assertIn(date_text, html)
                self.assertNotIn('Sentabr', html)

    def test_the_panel_says_it_too(self):
        user = make_user('oylik2', '+998901300032')
        _, variant = make_product('Oylik2', stock=5)
        order = make_order(user, variant, status='paid')
        Order.objects.filter(pk=order.pk).update(created_at=local(2026, 9, 16, 9))
        self.client.force_login(make_staff('oylik-xodim', '+998901300033'))
        for name, kwargs in (('panel_orders', {}),
                             ('panel_order', {'order_no': order.order_no})):
            with self.subTest(screen=name):
                html = self.client.get(reverse(name, kwargs=kwargs)).content.decode()
                self.assertIn('16 sentabr', html)
                self.assertNotIn('Sentabr', html)

    def test_every_month_name_in_a_template_goes_through_it(self):
        """``E``, ``F``, ``M`` and ``N`` print a month's name; each needs the filter."""
        found = 0
        for path in TEMPLATES.rglob('*.html'):
            source = path.read_text(encoding='utf-8')
            for match in re.finditer(r'\|date:(["\'])(.*?)\1(\|month_case)?', source):
                if set(re.sub(r'\\.', '', match.group(2))) & set('EFMN'):
                    found += 1
                    self.assertTrue(match.group(3), f'{path.relative_to(TEMPLATES)}: '
                                                    f'{match.group(0)}')
        self.assertGreaterEqual(found, 8)


# ------------------------------------------------------- form messages, #29
class FormMessagesTests(TestCase):
    """The browser's own validation words, in the page's language (§17 #222)."""

    REQUIRED = {'uz': 'Bu maydonni toʻldiring.', 'ru': 'Заполните это поле.',
                'en': 'Please fill in this field.'}

    @staticmethod
    def said(html):
        """The ``#gx-forms`` block of a page, decoded."""
        match = re.search(r'<script id="gx-forms" type="application/json">(.*?)</script>',
                          html, re.S)
        return json.loads(match.group(1))

    def test_the_storefront_carries_them_in_every_language(self):
        for lang in LANGS:
            with self.subTest(lang=lang):
                html = self.client.get(at(lang, 'contact')).content.decode()
                said = self.said(html)
                self.assertEqual(said['required'], self.REQUIRED[lang])
                self.assertEqual(set(said), set(form_messages()))
                self.assertIn('js/forms.js', html)
                self.assertLess(html.index('id="gx-forms"'), html.index('js/forms.js'))

    def test_the_panel_carries_them_too(self):
        self.client.force_login(make_staff('forma', '+998901300041'))
        for lang in LANGS:
            with self.subTest(lang=lang):
                html = self.client.get(at(lang, 'panel_orders')).content.decode()
                self.assertEqual(self.said(html)['required'], self.REQUIRED[lang])
                self.assertIn('js/forms.js', html)

    def test_every_message_is_written_in_russian_and_english(self):
        with translation.override('uz'):
            source = form_messages()
        for lang in ('ru', 'en'):
            with translation.override(lang):
                written = form_messages()
            for key, text in source.items():
                with self.subTest(lang=lang, key=key):
                    self.assertNotEqual(written[key], text)
                    self.assertEqual('{n}' in written[key], '{n}' in text)

    def test_the_error_page_has_them_with_no_context_at_all(self):
        """Django can render 500.html without a request (§17 #66)."""
        html = render_to_string('500.html')
        self.assertIn('id="gx-forms"', html)
        self.assertIn('js/forms.js', html)

    def test_the_review_form_has_a_translated_file_button(self):
        user = make_user('rasmli', '+998901300042')
        product, variant = make_product('Rasmli', stock=5)
        order = make_order(user, variant)
        self.client.force_login(user)
        for lang, button in (('uz', 'Rasmlarni tanlash'), ('ru', 'Выбрать фото'),
                             ('en', 'Choose photos')):
            with self.subTest(lang=lang):
                html = self.client.get(at(lang, 'review_create', order.pk)).content.decode()
                field = html[html.index('data-file-field'):]
                field = field[:field.index('field__hint')]
                self.assertIn(f'for="photos-{product.pk}">{button}</label>', field)
                self.assertIn('data-file-ui', field)
                self.assertIn('data-file-status', field)
                self.assertIn(f'type="file" name="photos" id="photos-{product.pk}"', field)

    def test_the_file_field_style_is_shared_by_both_shells(self):
        css = lambda name: (ROOT / 'static' / 'css' / name).read_text(encoding='utf-8')
        self.assertIn('.field__file {', css('components.css'))
        self.assertNotIn('.field__file {', css('panel.css'))


# ------------------------------------------------------------------ #23
class AdminUploadTests(TempMedia, TestCase):
    """A photograph added in the Django admin is cleaned like any other (§17 #221)."""

    def setUp(self):
        self.client.force_login(superuser('rasm-admin', '+998901300051'))
        self.product, _ = make_product('Admin rasmi', stock=2)

    @staticmethod
    def exif():
        tags = Image.Exif()
        tags[271] = 'GRAPHIX-TEST-CAMERA'
        return tags.tobytes()

    def test_a_product_photo_loses_its_metadata_and_is_resized(self):
        upload = photo(size=(3000, 1200), exif=self.exif())
        self.assertTrue(images.has_metadata(io.BytesIO(upload.read())))
        upload.seek(0)
        response = self.client.post(reverse('admin:product_imagep_add'),
                                    {'product': self.product.pk, 'order': 1,
                                     'picture': upload})
        self.assertEqual(response.status_code, 302)
        stored = ImageP.objects.get(product=self.product).picture
        self.assertTrue(stored.name.startswith('products/mahsulot'))
        self.assertFalse(images.has_metadata(stored.path))
        with Image.open(stored.path) as picture:
            self.assertEqual(picture.format, 'JPEG')
            self.assertEqual(max(picture.size), images.PRODUCT_MAX_EDGE)

    def test_a_png_is_stored_as_a_jpeg(self):
        response = self.client.post(reverse('admin:product_imagep_add'),
                                    {'product': self.product.pk, 'order': 1,
                                     'picture': photo(fmt='PNG')})
        self.assertEqual(response.status_code, 302)
        stored = ImageP.objects.get(product=self.product).picture
        self.assertTrue(stored.name.endswith('.jpg'))

    def test_something_that_is_not_a_picture_is_refused_on_the_field(self):
        response = self.client.post(reverse('admin:product_imagep_add'),
                                    {'product': self.product.pk, 'order': 1,
                                     'picture': SimpleUploadedFile('x.jpg', b'not an image')})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['adminform'].form.errors['picture'])
        self.assertFalse(ImageP.objects.exists())

    def test_every_image_form_in_the_admin_cleans(self):
        registry = django_admin.site._registry
        self.assertTrue(issubclass(registry[ImageP].form, product_admin.CleanPhotoForm))
        self.assertIs(registry[SizeChart].form, product_admin.ChartImageForm)
        inlines = {inline.model: inline.form
                   for model in (Product, Review) for inline in registry[model].inlines}
        self.assertIs(inlines[ImageP], product_admin.CleanPhotoForm)
        self.assertIs(inlines[ReviewImage], product_admin.ReviewPhotoForm)

    def test_a_review_photo_keeps_the_review_size(self):
        form_class = modelform_factory(ReviewImage, form=product_admin.ReviewPhotoForm,
                                       fields=('picture', 'order'))
        form = form_class(data={'order': 0},
                          files={'picture': photo(size=(3000, 1200), exif=self.exif())})
        self.assertTrue(form.is_valid(), form.errors)
        clean = form.cleaned_data['picture']
        self.assertEqual(clean.name, 'review.jpg')
        self.assertFalse(images.has_metadata(io.BytesIO(clean.read())))
        clean.seek(0)
        with Image.open(clean) as picture:
            self.assertEqual(max(picture.size), images.MAX_EDGE)

    def test_a_chart_saved_without_a_new_file_keeps_its_own(self):
        chart = SizeChart.objects.create(name='Jadval', image=jpeg('jadval.jpg'))
        request = RequestFactory().post('/')
        request.user = superuser('jadval-admin', '+998901300052')
        form_class = django_admin.site._registry[SizeChart].get_form(request, chart, change=True)
        form = form_class(data={'name': 'Jadval 2', 'note': '', 'note_ru': '', 'note_en': ''},
                          files={}, instance=chart)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().image.name, chart.image.name)


# ------------------------------------------------------------------ #28
class FileCleanupTests(TempMedia, TestCase):
    """A deleted image row takes its file with it, once the delete has committed (§17 #220)."""

    def setUp(self):
        self.product, _ = make_product('Fayl', stock=2)

    def photograph(self, order=1):
        return ImageP.objects.create(product=self.product, order=order, picture=jpeg())

    def test_the_file_goes_once_the_delete_commits(self):
        image = self.photograph()
        name = image.picture.name
        self.assertTrue(default_storage.exists(name))
        with self.captureOnCommitCallbacks() as waiting:
            image.delete()
        self.assertTrue(default_storage.exists(name), 'deleted before the commit')
        self.assertEqual(len(waiting), 1)
        waiting[0]()
        self.assertFalse(default_storage.exists(name))

    def test_a_rolled_back_delete_keeps_row_and_file(self):
        image = self.photograph()
        pk, name = image.pk, image.picture.name     # delete() clears image.pk
        queued = len(connection.run_on_commit)
        with self.assertRaises(RuntimeError), transaction.atomic():
            image.delete()
            raise RuntimeError('rolled back')
        self.assertEqual(len(connection.run_on_commit), queued)
        self.assertTrue(ImageP.objects.filter(pk=pk).exists())
        self.assertTrue(default_storage.exists(name))

    def test_a_file_another_row_names_is_kept(self):
        first = self.photograph()
        name = first.picture.name
        second = ImageP.objects.create(product=self.product, order=2, picture=name)
        with self.captureOnCommitCallbacks(execute=True):
            first.delete()
        self.assertTrue(default_storage.exists(name))
        with self.captureOnCommitCallbacks(execute=True):
            second.delete()
        self.assertFalse(default_storage.exists(name))

    def test_the_demo_seed_s_delete_and_recreate_keeps_its_files(self):
        """``seed_demo_catalogue`` deletes rows and recreates them over the same files."""
        name = self.photograph().picture.name
        with self.captureOnCommitCallbacks(execute=True), transaction.atomic():
            ImageP.objects.all().delete()
            ImageP.objects.create(product=self.product, order=1, picture=name)
        self.assertTrue(default_storage.exists(name))

    def test_the_panel_s_bulk_delete_is_covered(self):
        image = self.photograph()
        name = image.picture.name
        self.client.force_login(make_staff('fayl-xodim', '+998901300061'))
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse('panel_product_images', kwargs={'slug': self.product.slug}),
                {'action': 'delete', 'id': image.pk})
        self.assertEqual(response.json()['images'], [])
        self.assertFalse(default_storage.exists(name))

    def test_a_deleted_product_takes_its_photographs(self):
        names = [self.photograph(n).picture.name for n in (1, 2)]
        with self.captureOnCommitCallbacks(execute=True):
            self.product.delete()
        for name in names:
            self.assertFalse(default_storage.exists(name), name)

    def test_review_photos_and_charts_go_too(self):
        user = make_user('fayl-sharh', '+998901300062')
        _, variant = make_product('Sharhli fayl', stock=2)
        review = Review.objects.create(user=user, product=variant.product,
                                       order=make_order(user, variant), rating=5)
        review_photo = ReviewImage.objects.create(review=review, picture=jpeg()).picture.name
        chart = SizeChart.objects.create(name='Oʻchadi', image=jpeg())
        chart_file = chart.image.name
        with self.captureOnCommitCallbacks(execute=True):
            review.delete()
            chart.delete()
        self.assertFalse(default_storage.exists(review_photo))
        self.assertFalse(default_storage.exists(chart_file))

    def test_a_chart_with_no_picture_deletes_quietly(self):
        chart = SizeChart.objects.create(name='Rasmsiz')
        with self.captureOnCommitCallbacks(execute=True) as waiting:
            chart.delete()
        self.assertEqual(waiting, [])

    def test_a_file_that_will_not_delete_is_logged_not_raised(self):
        image = self.photograph()
        with mock.patch('django.core.files.storage.FileSystemStorage.delete',
                        side_effect=OSError('locked')), \
                self.assertLogs('product.signals', 'ERROR') as logs, \
                self.captureOnCommitCallbacks(execute=True):
            image.delete()
        self.assertIn(image.picture.name, logs.output[0])


# ---------------------------------------------------------- icons and #8
class IconAndShareCardTests(TestCase):
    """The calendar joins the sprite and the style guide; the share card is redrawn."""

    SPRITE = TEMPLATES / 'partials' / '_icons.svg.html'

    def test_every_icon_used_is_drawn_and_listed(self):
        from core.views import STYLE_ICONS
        drawn = set(re.findall(r'<symbol id="i-([a-z0-9-]+)"',
                               self.SPRITE.read_text(encoding='utf-8')))
        self.assertEqual(drawn, set(STYLE_ICONS))
        used = set()
        for folder, pattern in ((TEMPLATES, '*.html'), (ROOT / 'static' / 'js', '*.js')):
            for path in folder.rglob(pattern):
                used |= set(re.findall(r'#i-([a-z0-9-]+)', path.read_text(encoding='utf-8')))
        self.assertIn('calendar', used)
        self.assertLessEqual(used, drawn)

    def test_the_share_image_is_the_size_the_page_announces(self):
        with Image.open(ROOT / 'static' / 'img' / 'og-image.png') as card:
            self.assertEqual(card.size, (1200, 630))
        head = (TEMPLATES / 'base.html').read_text(encoding='utf-8')
        self.assertIn('<meta property="og:image:width" content="1200">', head)
        self.assertIn('<meta property="og:image:height" content="630">', head)

    def test_the_card_has_a_source_in_the_brand_folder(self):
        source = ROOT / 'docs' / 'brand' / 'og-card.html'
        text = source.read_text(encoding='utf-8')
        self.assertIn('Playfair Display', text)
        self.assertIn('--window-size=1200,630', text)
        self.assertIn('og-image.png', text)


# --------------------------------------------------- verification, §17 #225
class VerificationInEveryLanguageTests(TestCase):
    """An unverified account reaches the code page in every language (§17 #225).

    The middleware's exempt paths were resolved in Uzbek only, so on
    ``/ru/verify-phone/`` it redirected to ``/ru/verify-phone/`` for ever.
    """

    def setUp(self):
        self.user = make_user('kodsiz', '+998901300071', verified=False)
        self.client.force_login(self.user)
        sms = mock.patch('user.otp.send_sms', return_value=True)
        self.sent = sms.start()
        self.addCleanup(sms.stop)

    def test_the_code_page_opens_in_every_language(self):
        for lang in LANGS:
            with self.subTest(lang=lang):
                response = self.client.get(at(lang, 'verify_phone'))
                self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sent.call_count, 1)

    def test_any_other_page_leads_there_in_its_own_language(self):
        for lang in LANGS:
            with self.subTest(lang=lang):
                response = self.client.get(at(lang, 'shop'), follow=True)
                self.assertEqual(response.redirect_chain,
                                 [(at(lang, 'verify_phone'), 302)])
                self.assertEqual(response.status_code, 200)

    def test_signing_out_works_in_every_language(self):
        for lang in LANGS:
            with self.subTest(lang=lang):
                self.client.force_login(self.user)
                self.client.post(at(lang, 'logout'))
                self.assertNotIn('_auth_user_id', self.client.session)

    def test_the_language_can_be_switched_while_waiting(self):
        target = at('ru', 'verify_phone')
        response = self.client.post('/i18n/setlang/', {'language': 'ru', 'next': target})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], target)

    def test_everything_else_still_waits_for_the_code(self):
        for lang in LANGS:
            for name in ('account', 'checkout', 'panel_orders'):
                with self.subTest(lang=lang, page=name):
                    response = self.client.get(at(lang, name))
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response['Location'], at(lang, 'verify_phone'))
