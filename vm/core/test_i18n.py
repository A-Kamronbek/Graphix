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


class CatalogueCompletenessTests(TestCase):
    """Every string marked for translation is actually translated in ru and en.

    This exists because of a real miss: Phase 4 wrapped thirteen new labels in
    ``gettext_lazy`` and never ran ``makemessages``, so they rendered Uzbek in all
    three languages. Nothing failed — the site just quietly stopped being
    trilingual in those places, which is the hardest kind of regression to notice.

    Uzbek is the source language, so its ``msgstr`` entries stay empty on purpose:
    gettext falls back to the msgid, which *is* the Uzbek copy.
    """
    #: Untranslated by design — acronyms and words that are identical in all three.
    SAME_IN_EVERY_LANGUAGE = {'Oversize', 'Boxy', 'Email', 'Telegram', 'GRAPHIX'}

    def _entries(self, lang):
        """Return (msgid, msgstr) pairs from a catalogue, skipping the header.

        Parses continuation lines rather than matching one-line entries: gettext
        wraps anything long across several quoted strings, and a regex that only
        saw single-line entries would silently skip exactly the long strings most
        likely to be left untranslated.
        """
        entries, key, parts = [], None, {'msgid': [], 'msgstr': []}
        for raw in self._catalogue_path(lang).read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if line.startswith('msgid "'):
                if key:                                 # flush the previous entry
                    entries.append((''.join(parts['msgid']), ''.join(parts['msgstr'])))
                parts = {'msgid': [line[7:-1]], 'msgstr': []}
                key = 'msgid'
            elif line.startswith('msgstr "'):
                parts['msgstr'] = [line[8:-1]]
                key = 'msgstr'
            elif line.startswith('"') and key:          # a wrapped continuation
                parts[key].append(line[1:-1])
        if key:
            entries.append((''.join(parts['msgid']), ''.join(parts['msgstr'])))
        return [(mid, mstr) for mid, mstr in entries if mid]

    @staticmethod
    def _catalogue_path(lang):
        from pathlib import Path
        from django.conf import settings
        return Path(settings.LOCALE_PATHS[0]) / lang / 'LC_MESSAGES' / 'django.po'

    def test_the_parser_actually_finds_the_entries(self):
        """Guards the two tests below from passing vacuously on a parse failure."""
        for lang in ('uz', 'ru', 'en'):
            with self.subTest(lang=lang):
                self.assertGreaterEqual(
                    len(self._entries(lang)), 30,
                    f"only parsed {len(self._entries(lang))} entries from the {lang} "
                    "catalogue - the parser, not the catalogue, is probably broken",
                )

    def test_russian_and_english_catalogues_have_no_empty_translations(self):
        for lang in ('ru', 'en'):
            with self.subTest(lang=lang):
                empty = [mid for mid, mstr in self._entries(lang)
                         if not mstr and mid not in self.SAME_IN_EVERY_LANGUAGE]
                self.assertEqual(
                    empty, [],
                    f"{len(empty)} msgid(s) have no {lang} translation and will render "
                    f"Uzbek instead: {empty[:5]}",
                )

    def test_no_catalogue_entry_is_fuzzy(self):
        """A fuzzy entry is ignored by gettext, so the page renders Uzbek.

        ``makemessages`` marks an entry fuzzy when it guesses a translation from a
        similar old msgid — and then gettext refuses to use it. Nothing fails; the
        page is just silently monolingual in that one spot. It shipped exactly that
        way for four strings, including the add-to-cart button, because the
        empty-msgstr check above cannot see a *filled but ignored* entry.

        The catalogue header is conventionally fuzzy and is skipped.
        """
        for lang in ('uz', 'ru', 'en'):
            with self.subTest(lang=lang):
                lines = self._catalogue_path(lang).read_text(encoding='utf-8').splitlines()
                fuzzy = []
                for i, line in enumerate(lines):
                    if line.strip() != '#, fuzzy':
                        continue
                    j = i + 1
                    while j < len(lines) and lines[j].startswith('#'):
                        j += 1
                    if j < len(lines) and lines[j].startswith('msgid "'):
                        msgid = lines[j][7:-1]
                        if msgid:                       # empty msgid == the header
                            fuzzy.append(msgid)
                self.assertEqual(
                    fuzzy, [],
                    f"{len(fuzzy)} fuzzy {lang} entr(ies) will render Uzbek instead of "
                    f"being translated: {fuzzy}",
                )

    def test_the_catalogues_cover_the_same_strings(self):
        """A string present in one catalogue and missing from another is a stale run."""
        ids = {lang: {mid for mid, _ in self._entries(lang)} for lang in ('uz', 'ru', 'en')}
        self.assertEqual(ids['ru'], ids['en'], 'ru and en catalogues are out of step')
        self.assertEqual(ids['uz'], ids['ru'], 'uz catalogue is out of step')

    def test_the_phase_4_choice_labels_translate(self):
        """Spot-check the labels that were missed, so the fix can't be undone."""
        from product.models import Product, Tag
        from product.models import Review
        expected = {
            'ru': ['Обычный', 'Стиль', 'На модерации'],
            'en': ['Regular', 'Style', 'Pending'],
        }
        for lang, wanted in expected.items():
            with self.subTest(lang=lang), translation.override(lang):
                rendered = [str(dict(Product.Fit.choices)[Product.Fit.REGULAR]),
                            str(dict(Tag.Kind.choices)[Tag.Kind.STYLE]),
                            str(dict(Review.Status.choices)[Review.Status.PENDING])]
                self.assertEqual(rendered, wanted)
