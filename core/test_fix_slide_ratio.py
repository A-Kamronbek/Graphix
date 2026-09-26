"""The home page's slides: 16:9 below 860 px, 16:5 from 860 px, both tokens.

The owner's two shapes (§17 #257). The laptop strip was 1120:300, written as a
literal in pages.css, until the owner asked for 16:5 (§17 #299). Pinned here
so a change to either shape is a decision, and so the strip stays a token -
the literal was the one design value in the stylesheets that was not.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS = Path(settings.BASE_DIR) / 'static' / 'css'


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
