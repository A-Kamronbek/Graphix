"""All type on the site is one face, drawn from the site's own file (§17 #311, #312).

Playfair Display, Onest and IBM Plex Mono gave way to Inter, a face in
Helvetica's style, cut to the characters the three old files covered between
them. These tests read the stylesheets, the templates and the font file as
shipped. They fail when a second face is named, when a page asks for a second
font file, or when the file loses a letter the three languages need.

The three old files stay in static/fonts until the owner has agreed the new
look (plan §9 Phase 17 item 1). Nothing may point at them.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from PIL import ImageFont

ROOT = Path(settings.BASE_DIR)
CSS = ROOT / 'static' / 'css'
JS = ROOT / 'static' / 'js'
TEMPLATES = ROOT / 'templates'
FONT = ROOT / 'static' / 'fonts' / 'inter-var.woff2'

#: The faces the site used before, by family name and by file name.
RETIRED = re.compile(r'Playfair|\bOnest\b|IBM Plex|playfair-display|onest-var|ibm-plex')

#: Every page shell that links the stylesheets, and so preloads the font.
SHELLS = ('base.html', 'boshqaruv/base.html', 'boshqaruv/style.html')

#: What the two preloaded files weighed together before the change. One file
#: for every role is only a saving while it stays under this.
REPLACED_PRELOAD_BYTES = 112_844

#: A private-use code point no font on the site draws. Whatever the file shows
#: for it is what it shows for any letter it does not have.
ABSENT = ''


def read_by_a_browser():
    """Every stylesheet, script and template, as (path, text)."""
    for folder, pattern in ((CSS, '*.css'), (JS, '*.js'), (TEMPLATES, '*.html')):
        for path in sorted(folder.rglob(pattern)):
            yield path, path.read_text(encoding='utf-8')


def stylesheets():
    """The text of every stylesheet, joined, for rules that may sit in any of them."""
    return '\n'.join(path.read_text(encoding='utf-8') for path in sorted(CSS.glob('*.css')))


class OneFaceTests(SimpleTestCase):
    """The stylesheets and templates name one face and one file."""

    def test_no_retired_face_is_named(self):
        for path, text in read_by_a_browser():
            with self.subTest(file=str(path.relative_to(ROOT))):
                self.assertIsNone(RETIRED.search(text))

    def test_one_font_face_block_and_it_is_the_new_file(self):
        blocks = re.findall(r'@font-face\s*\{([^}]*)\}', stylesheets())
        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertIn('font-family: "Inter";', block)
        self.assertIn('url("../fonts/inter-var.woff2")', block)
        # The whole range, so 500, 600 and 700 are drawn and not faked.
        self.assertIn('font-weight: 100 900;', block)
        self.assertIn('font-display: swap;', block)

    def test_the_three_roles_share_the_face(self):
        tokens = (CSS / 'tokens.css').read_text(encoding='utf-8')
        self.assertRegex(tokens, r'--f-body:\s*"Inter",')
        self.assertRegex(tokens, r'--f-display:\s*var\(--f-body\);')
        self.assertRegex(tokens, r'--f-mono:\s*var\(--f-body\);')

    def test_no_rule_names_a_family_itself(self):
        """Outside the one @font-face, a family is always a token."""
        for path, text in read_by_a_browser():
            text = re.sub(r'@font-face\s*\{[^}]*\}', '', text)
            for value in re.findall(r'font-family:\s*([^;}]+)', text):
                with self.subTest(file=str(path.relative_to(ROOT)), value=value):
                    self.assertRegex(value.strip(), r'^var\(--f-(body|display|mono)\)$')

    def test_each_shell_preloads_the_one_file(self):
        for name in SHELLS:
            with self.subTest(shell=name):
                text = (TEMPLATES / name).read_text(encoding='utf-8')
                preloads = re.findall(r'<link rel="preload" as="font"[^>]*>', text)
                self.assertEqual(len(preloads), 1)
                self.assertIn("{% static 'fonts/inter-var.woff2' %}", preloads[0])
                # Without crossorigin the browser fetches the file twice.
                self.assertIn('crossorigin', preloads[0])


class PicturesTests(SimpleTestCase):
    """Type that lives inside a picture is the same face, and can be drawn again."""

    BRAND = ROOT / 'docs' / 'brand'
    IMG = ROOT / 'static' / 'img'

    def test_each_picture_source_draws_with_the_site_file(self):
        for name in ('og-card.html', 'size-guide.html'):
            with self.subTest(source=name):
                text = (self.BRAND / name).read_text(encoding='utf-8')
                self.assertIn('static/fonts/inter-var.woff2', text)
                self.assertIsNone(RETIRED.search(text))

    def test_the_size_chart_source_names_its_picture(self):
        text = (self.BRAND / 'size-guide.html').read_text(encoding='utf-8')
        self.assertIn('size_guide.png', text)
        self.assertIn('--window-size=1200,871', text)

    def test_the_size_chart_carries_the_seeded_measurements(self):
        """The picture's numbers and the rows the site seeds are one table."""
        from product import size_charts
        text = (self.BRAND / 'size-guide.html').read_text(encoding='utf-8')
        for cut, table in (('regular', size_charts.REGULAR), ('oversize', size_charts.OVERSIZE)):
            block = re.search(r'data-cut="%s".*?</table>' % cut, text, re.S).group(0)
            rows = re.findall(r'<tr>((?:<td>[^<]*</td>)+)</tr>', block)
            drawn = {cells[0]: tuple(cells[1:]) for cells in
                     (re.findall(r'<td>([^<]*)</td>', row) for row in rows)}
            seeded = {size: tuple(str(int(float(value))) for value in values)
                      for size, values in table.items()}
            with self.subTest(cut=cut):
                self.assertEqual(drawn, seeded)

    def test_the_lockups_are_outlines(self):
        """Paths only, so they need no font where they are used."""
        for name in ('logo-full.svg', 'logo-stacked.svg'):
            with self.subTest(lockup=name):
                text = (self.IMG / name).read_text(encoding='utf-8')
                self.assertNotIn('<text', text)
                self.assertNotIn('font', text)
                self.assertIn('aria-label="GRAPHIX"', text)


class OneFontRequestTests(TestCase):
    """A rendered page asks for one font file."""

    def test_the_home_page_preloads_one_font(self):
        html = self.client.get('/uz/').content.decode()
        preloads = re.findall(r'<link rel="preload" as="font"[^>]*>', html)
        self.assertEqual(len(preloads), 1)
        self.assertIn('fonts/inter-var', preloads[0])
        self.assertIsNone(RETIRED.search(html))


class FontFileTests(SimpleTestCase):
    """The file that ships has the letters, the weights and the size it should."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.font = ImageFont.truetype(str(FONT), 64)
        cls.blank = cls.drawn(ABSENT)

    @classmethod
    def drawn(cls, character):
        """The pixels the file draws for one character."""
        mask = cls.font.getmask(character)
        return mask.size, bytes(mask)

    def has(self, character):
        """True when the file draws the character as something of its own."""
        return self.drawn(character) != self.blank

    def test_it_is_a_woff2_no_heavier_than_what_it_replaced(self):
        self.assertEqual(FONT.read_bytes()[:4], b'wOF2')
        self.assertLessEqual(FONT.stat().st_size, REPLACED_PRELOAD_BYTES)

    def test_the_check_can_tell_a_missing_letter(self):
        """A star is not in the file, so it must read as missing."""
        self.assertFalse(self.has('★'))

    def test_the_uzbek_modifier_letters(self):
        """Subsetting can drop these two, and nothing else fails when it does (§17 #43)."""
        self.assertTrue(self.has('ʻ'))    # oʻ, gʻ
        self.assertTrue(self.has('ʼ'))    # tutuq belgisi

    def test_latin_digits_and_cyrillic(self):
        letters = [chr(c) for c in range(0x21, 0x7f)]
        letters += [chr(c) for c in range(0x410, 0x450)] + ['Ё', 'ё']
        missing = [c for c in letters if not self.has(c)]
        self.assertEqual(missing, [])

    def test_the_marks_the_copy_uses(self):
        marks = '«»—–…№‘’“”·×²→'
        missing = ['U+%04X' % ord(c) for c in marks if not self.has(c)]
        self.assertEqual(missing, [])

    def test_weight_and_optical_size_are_axes(self):
        """Every weight from one file, and a display cut the browser picks for headings."""
        axes = {axis['name']: (axis['minimum'], axis['maximum'])
                for axis in self.font.get_variation_axes()}
        self.assertEqual(axes[b'Weight'], (100, 900))
        self.assertIn(b'Optical size', axes)
