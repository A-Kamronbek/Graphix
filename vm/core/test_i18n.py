"""Internationalisation tests.

The first test in this file is the important one: Click POSTs its payment
callback to `/payment/click/update/`, and `i18n_patterns` would happily move that
path behind a language prefix. If that ever happens, every callback 404s and
payments fail *silently* — the order simply never flips to paid (§12 risk #2).
"""
from django.test import TestCase, override_settings
from django.urls import reverse, resolve
from django.utils import translation

from core.i18n import tfield
from product.models import Category, Product


class WebhookStaysUnprefixedTests(TestCase):
    """The Click callback must resolve at exactly one path, in every language."""

    def test_reverse_gives_the_unprefixed_path(self):
        self.assertEqual(reverse('click_webhook'), '/payment/click/update/')

    def test_path_resolves_to_the_webhook_view(self):
        self.assertEqual(resolve('/payment/click/update/').url_name, 'click_webhook')

    def test_reverse_is_identical_under_every_language(self):
        """Activating ru or en must not move the callback."""
        for code in ('uz', 'ru', 'en'):
            with translation.override(code):
                self.assertEqual(
                    reverse('click_webhook'), '/payment/click/update/',
                    msg=f"the Click webhook moved under {code} — payments would fail silently",
                )

    def test_prefixed_variants_are_not_served(self):
        for path in ('/ru/payment/click/update/', '/en/payment/click/update/'):
            self.assertEqual(self.client.post(path).status_code, 404, msg=path)

    def test_other_machine_paths_are_also_unprefixed(self):
        self.assertEqual(reverse('sitemap'), '/sitemap.xml')
        self.assertEqual(reverse('set_language'), '/i18n/setlang/')


class LanguagePrefixTests(TestCase):
    """Uzbek is served unprefixed; Russian and English are prefixed."""

    def test_uzbek_has_no_prefix(self):
        self.assertEqual(reverse('shop'), '/shop/')

    def test_russian_and_english_are_prefixed(self):
        with translation.override('ru'):
            self.assertEqual(reverse('shop'), '/ru/shop/')
        with translation.override('en'):
            self.assertEqual(reverse('shop'), '/en/shop/')

    def test_all_three_render(self):
        for path in ('/', '/ru/', '/en/'):
            self.assertEqual(self.client.get(path).status_code, 200, msg=path)

    def test_html_lang_follows_the_prefix(self):
        self.assertContains(self.client.get('/ru/'), '<html lang="ru">')
        self.assertContains(self.client.get('/en/'), '<html lang="en">')

    def test_page_declares_an_alternate_for_every_language(self):
        html = self.client.get('/').content.decode()
        for code in ('uz', 'ru', 'en', 'x-default'):
            self.assertIn(f'hreflang="{code}"', html)

    def test_switching_language_keeps_you_on_the_same_page(self):
        """set_language must return the visitor to the page they were reading."""
        response = self.client.post(
            reverse('set_language'), {'language': 'ru', 'next': '/shop/'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/ru/shop/')


class TranslatedMessageTests(TestCase):
    """Interface strings come from the catalogues, not from hardcoded Uzbek."""

    def test_validator_message_is_translated(self):
        from user.validators import CustomMinimumLengthValidator
        with translation.override('ru'):
            self.assertEqual(
                str(CustomMinimumLengthValidator().get_help_text()),
                "Пароль должен содержать не менее 8 символов.")
        with translation.override('en'):
            self.assertEqual(
                str(CustomMinimumLengthValidator().get_help_text()),
                "Password must be at least 8 characters.")

    def test_uzbek_falls_back_to_the_msgid(self):
        from user.validators import CustomMinimumLengthValidator
        with translation.override('uz'):
            self.assertIn("Parol 8 belgidan", str(CustomMinimumLengthValidator().get_help_text()))


class TfieldTests(TestCase):
    """Per-row content translation, with the fallback that actually matters."""

    @classmethod
    def setUpTestData(cls):
        cls.filled = Product.objects.create(
            name="Qora futbolka", name_ru="Чёрная футболка", name_en="Black tee")
        cls.blank = Product.objects.create(name="Faqat oʻzbekcha")
        cls.category = Category.objects.create(name="Futbolkalar", name_ru="Футболки")

    def test_returns_the_active_language(self):
        with translation.override('ru'):
            self.assertEqual(tfield(self.filled, 'name'), "Чёрная футболка")
        with translation.override('en'):
            self.assertEqual(tfield(self.filled, 'name'), "Black tee")

    def test_uzbek_reads_the_base_field(self):
        with translation.override('uz'):
            self.assertEqual(tfield(self.filled, 'name'), "Qora futbolka")

    def test_blank_translation_falls_back_rather_than_rendering_empty(self):
        """A half-filled row must never show an empty product name."""
        for code in ('ru', 'en'):
            with translation.override(code):
                self.assertEqual(tfield(self.blank, 'name'), "Faqat oʻzbekcha")

    def test_works_on_any_model(self):
        with translation.override('ru'):
            self.assertEqual(tfield(self.category, 'name'), "Футболки")
        with translation.override('en'):
            self.assertEqual(tfield(self.category, 'name'), "Futbolkalar")

    def test_none_is_safe(self):
        self.assertEqual(tfield(None, 'name'), '')

    def test_template_filter(self):
        from django.template import Context, Template
        tpl = Template('{% load i18n_fields %}{{ p|t:"name" }}')
        with translation.override('ru'):
            self.assertEqual(tpl.render(Context({'p': self.filled})), "Чёрная футболка")
