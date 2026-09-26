"""The home page's slides: one 16:5 picture, whole on a laptop, middle on a phone.

The picture is made 16:5. From 860 px the card is 16:5 too and shows all of it;
below 860 px the card is 16:9 and `object-fit: cover` keeps the picture's full
height and cuts its sides (§17 #299, #300). The laptop strip was 1120:300, a
literal in pages.css, until the owner asked for 16:5. Pinned here so a change
to either shape is a decision, the ratios stay tokens, a phone fetches a file
as wide as the one it draws, and the owner is told the shape in every language.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.utils import translation

from product.templatetags.image_tags import SIZES

CSS = Path(settings.BASE_DIR) / 'static' / 'css'

#: The panel's instruction beside the slide upload, as the template writes it.
HINT = ('Rasmni 16:5 nisbatda tayyorlang (masalan, 2000×625 piksel). Noutbukda u toʻliq '
        'koʻrinadi, telefonda esa faqat oʻrtadagi 16:9 qismi — chetlari kesiladi. Matn va '
        'mahsulotni oʻrtaga joylashtiring.')


class SlideRatioTests(SimpleTestCase):
    """Read the stylesheets as shipped; there is no layout engine in a test."""

    def setUp(self):
        self.tokens = (CSS / 'tokens.css').read_text(encoding='utf-8')
        self.pages = (CSS / 'pages.css').read_text(encoding='utf-8')

    def test_the_two_shapes(self):
        self.assertIn('--ar-slide: 16 / 9;', self.tokens)
        self.assertIn('--ar-slide-wide: 16 / 5;', self.tokens)

    def test_the_wide_shape_starts_at_860(self):
        """The strip belongs to an 860 px query, and uses the token there."""
        blocks = re.findall(r'@media \(min-width: 860px\) \{(.*?)\n\}', self.pages, re.S)
        self.assertTrue(blocks)
        self.assertTrue(any('.slides__item { aspect-ratio: var(--ar-slide-wide); }' in b
                            for b in blocks))

    def test_no_slide_ratio_is_written_as_a_number(self):
        """Every aspect-ratio on a slide comes from a token."""
        rules = re.findall(r'\.slides__item[^{]*\{[^}]*\}', self.pages)
        self.assertTrue(rules)
        for rule in rules:
            for value in re.findall(r'aspect-ratio:\s*([^;]+);', rule):
                self.assertTrue(value.strip().startswith('var(--ar-slide'), rule)

    def test_a_phone_keeps_the_height_and_the_middle(self):
        """Cover keeps the full height of a picture wider than its card, and
        centre decides that the sides go, not one of them."""
        rule = re.search(r'\.slides__item img \{([^}]*)\}', self.pages)
        self.assertIsNotNone(rule)
        self.assertIn('object-fit: cover', rule.group(1))
        self.assertIn('object-position: center', rule.group(1))


class SlideDeliveryTests(SimpleTestCase):
    """What the browser is told before it has read a stylesheet."""

    def test_a_phone_fetches_for_the_width_it_draws(self):
        """Below 860 px the picture is (16/5) / (16/9) = 1.8 card-widths wide."""
        self.assertEqual(round(92 * (16 / 5) / (16 / 9)), 166)
        self.assertEqual(SIZES['slide'],
                         '(min-width: 1280px) 1216px, (min-width: 860px) 92vw, 166vw')

    def test_the_owner_is_told_the_shape_in_each_language(self):
        for lang, word in (('ru', 'пропорции 16:5'), ('en', 'Make the picture 16:5')):
            with translation.override(lang):
                self.assertIn(word, translation.gettext(HINT), lang)

    def test_the_template_carries_the_hint(self):
        template = (Path(settings.BASE_DIR) / 'templates' / 'boshqaruv' / 'slides.html')
        self.assertIn(HINT, template.read_text(encoding='utf-8'))
