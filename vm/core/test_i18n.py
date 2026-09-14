"""Internationalisation tests.

The first test in this file is the important one: Click POSTs its payment
callback to `/payment/click/update/`, and `i18n_patterns` would happily move that
path behind a language prefix. If that ever happens, every callback 404s and
payments fail *silently* — the order simply never flips to paid (§12 risk #2).
"""
import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
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


class CrawlerFacingFilesTests(TestCase):
    """robots.txt and the manifest describe the URL tree, so they move with it.

    A `Disallow: /cart/` rule stopped covering anything real the moment every
    page took a language prefix (§17 #121): the cart is at `/uz/cart/` now, and
    a rule written for the old shape silently protects nothing.
    """

    PRIVATE = ('cart', 'account', 'checkout', 'verify-phone', 'order')

    def test_robots_disallows_the_private_areas_in_every_language(self):
        body = self.client.get('/robots.txt').content.decode()
        for code in ('uz', 'ru', 'en'):
            for area in self.PRIVATE:
                with self.subTest(code=code, area=area):
                    self.assertIn(f'Disallow: /{code}/{area}/', body)

    def test_robots_allows_each_language_root(self):
        body = self.client.get('/robots.txt').content.decode()
        for code in ('uz', 'ru', 'en'):
            self.assertIn(f'Allow: /{code}/', body)

    def test_the_manifest_starts_on_a_real_page(self):
        """`start_url: "/"` would open the installed app on a redirect."""
        import json
        manifest = json.loads(self.client.get('/site.webmanifest').content)
        self.assertEqual(self.client.get(manifest['start_url']).status_code, 200)


class LanguagePrefixTests(TestCase):
    """Every language carries a prefix, Uzbek included (§17 #121).

    Uzbek was served at `/` until 2026-09-14. An unprefixed default is a
    special case Django works around rather than supports — it forces the
    default language on every unprefixed path, which is what left the language
    switcher one-way for four phases (§17 #115).
    """

    def test_every_language_is_prefixed(self):
        for code in ('uz', 'ru', 'en'):
            with self.subTest(code=code), translation.override(code):
                self.assertEqual(reverse('shop'), f'/{code}/shop/')

    def test_all_three_render(self):
        for path in ('/uz/', '/ru/', '/en/'):
            self.assertEqual(self.client.get(path).status_code, 200, msg=path)

    def test_html_lang_follows_the_prefix(self):
        for code in ('uz', 'ru', 'en'):
            with self.subTest(code=code):
                self.assertContains(self.client.get(f'/{code}/'),
                                    f'<html lang="{code}">')

    def test_page_declares_an_alternate_for_every_language(self):
        html = self.client.get('/uz/').content.decode()
        for code in ('uz', 'ru', 'en', 'x-default'):
            self.assertIn(f'hreflang="{code}"', html)

    def test_the_bare_root_sends_a_visitor_to_a_language(self):
        """Nobody types /uz/. `/` has to lead somewhere."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn(response['Location'], ('/uz/', '/ru/', '/en/'))

    def test_an_old_unprefixed_url_still_works(self):
        """Every Uzbek URL changed shape, and links to the old ones exist."""
        for old, new in (('/shop/', '/uz/shop/'), ('/about/', '/uz/about/')):
            with self.subTest(old=old):
                response = self.client.get(old)
                self.assertEqual(response.status_code, 302, msg=old)
                self.assertEqual(response['Location'], new)
                self.assertEqual(self.client.get(new).status_code, 200)

    def test_an_old_url_lands_in_the_visitors_own_language(self):
        """The redirect negotiates rather than always sending people to Uzbek —
        which is also why it is a 302 and not a 301: the destination depends on
        who is asking, so it must never be cached as permanent."""
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'ru'
        self.assertEqual(self.client.get('/shop/')['Location'], '/ru/shop/')

    def test_switching_language_keeps_you_on_the_same_page(self):
        """set_language must return the visitor to the page they were reading."""
        response = self.client.post(
            reverse('set_language'), {'language': 'ru', 'next': '/uz/shop/'})
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

        A plural entry carries ``msgstr[0]``, ``msgstr[1]`` … instead of a single
        ``msgstr``, and is collapsed here into one pair whose translation counts
        as empty unless *every* form is filled — so a half-written plural still
        fails the check below. Before this, the parser recognised only a bare
        ``msgstr`` and so reported a fully translated plural as untranslated.
        """
        entries, key, msgid, forms = [], None, [], []

        def flush():
            """Record the entry just parsed, if it had a msgid at all."""
            if msgid:
                texts = [''.join(f) for f in forms]
                joined = '' if not texts or not all(texts) else ''.join(texts)
                entries.append((''.join(msgid), joined))

        for raw in self._catalogue_path(lang).read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if line.startswith('msgid "'):
                flush()
                key, msgid, forms = 'msgid', [line[7:-1]], []
            elif line.startswith('msgid_plural "'):
                key = None                              # same entry, nothing to collect
            elif line.startswith('msgstr "'):
                key, forms = 'msgstr', [[line[8:-1]]]
            elif line.startswith('msgstr['):            # msgstr[0] "…"
                key = 'msgstr'
                forms.append([line[line.index(']') + 2:][1:-1]])
            elif line.startswith('"') and key == 'msgid':
                msgid.append(line[1:-1])
            elif line.startswith('"') and key == 'msgstr':
                forms[-1].append(line[1:-1])
        flush()
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

        Matching a bare ``#, fuzzy`` is not enough: gettext writes all of an
        entry's flags on one comma-separated line, so a string with a placeholder
        comes back as ``#, fuzzy, python-format``. This test read the bare form
        only, which is how a fuzzy add-to-cart message got past both it and
        ``.git/po_tool.py`` during the Phase 5 gate review.
        """
        for lang in ('uz', 'ru', 'en'):
            with self.subTest(lang=lang):
                lines = self._catalogue_path(lang).read_text(encoding='utf-8').splitlines()
                fuzzy = []
                for i, line in enumerate(lines):
                    flags = line.strip()
                    if not (flags.startswith('#,') and 'fuzzy' in flags):
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
        from core.i18n import tfield
        from product.models import PrintMethod, Review, TagKind
        expected = {
            'ru': ['Стиль', 'Шелкография', 'На модерации'],
            'en': ['Style', 'Silkscreen', 'Pending'],
        }
        # Two of the three are rows rather than choices now — the tag kind and
        # the print method, since the Phase 7 recheck — so their three languages
        # live in three columns and are read the way every other translated name
        # on the site is read. `Product.Fit` was the third and is gone with the
        # cut it named (§17 #172). The assertion is the same one it always was:
        # a Russian reader sees Russian.
        style = TagKind.objects.get(slug='style')
        silkscreen = PrintMethod.objects.get(slug='silkscreen')
        for lang, wanted in expected.items():
            with self.subTest(lang=lang), translation.override(lang):
                rendered = [tfield(style, 'name'),
                            tfield(silkscreen, 'name'),
                            str(dict(Review.Status.choices)[Review.Status.PENDING])]
                self.assertEqual(rendered, wanted)


class UserFacingPythonStringTests(SimpleTestCase):
    """Every flash message and form error must go through gettext.

    Template copy is covered by `makemessages` finding `{% trans %}`, and the
    catalogue tests above prove a found string is actually translated. Neither
    can see a string that was never marked at all — and the Phase 5 gate review
    found twenty of them, across the cart, payment, signup, OTP, account and
    password-reset flows. They were not subtle failures: a Russian visitor added
    something to the cart and got Uzbek.

    So this walks the source with `ast` and fails on a literal passed to
    `messages.*` or `form.add_error`. `ast` rather than a regex because the real
    question is *which argument* carries the string, and a line-based match
    cannot tell `add_error('code', _("..."))` - a field name, correctly wrapped -
    from `add_error('code', "...")`.

    SMS bodies are deliberately out of scope: Eskiz moderates the exact message
    text, so translating one would stop it sending until re-moderated (§19 Q17).
    """

    TARGETS = ('success', 'error', 'warning', 'info', 'add_message', 'add_error')

    @staticmethod
    def _is_translated(node):
        """True if `node` is `_(...)`, or `_(...) % {...}` / `_(...).format(...)`."""
        if isinstance(node, ast.BinOp):
            return UserFacingPythonStringTests._is_translated(node.left)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in ('_', 'gettext', 'ngettext'):
                return True
            if isinstance(func, ast.Attribute):          # _("...").format(...)
                return UserFacingPythonStringTests._is_translated(func.value)
        return False

    def test_no_flash_message_or_form_error_is_an_unwrapped_literal(self):
        root = Path(settings.BASE_DIR)
        offences = []
        for path in sorted(root.rglob('*.py')):
            rel = path.relative_to(root).as_posix()
            if 'migrations/' in rel or rel.startswith('vm/') or '/test' in rel:
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=rel)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not isinstance(func, ast.Attribute):
                    continue
                # `logger.error("...")` shares three method names with
                # `messages.error("...")`, and a log line must stay English and
                # untranslated - so match on the receiver, not just the method.
                if func.attr == 'add_error':
                    pass
                elif (func.attr in self.TARGETS
                        and isinstance(func.value, ast.Name)
                        and func.value.id == 'messages'):
                    pass
                else:
                    continue
                for arg in node.args:
                    # A bare word is a field name or a level, not copy; prose has
                    # a space in it. An f-string can never be translated at all.
                    if isinstance(arg, ast.JoinedStr):
                        offences.append(f"{rel}:{node.lineno} f-string")
                    elif (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                            and ' ' in arg.value.strip()):
                        offences.append(f"{rel}:{node.lineno} {arg.value[:40]!r}")
                    elif isinstance(arg, ast.BinOp) and not self._is_translated(arg):
                        offences.append(f"{rel}:{node.lineno} unwrapped %-format")
        self.assertEqual(
            offences, [],
            f"{len(offences)} user-facing string(s) bypass gettext and will render "
            f"Uzbek in every language: {offences}",
        )
