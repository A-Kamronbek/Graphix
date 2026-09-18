"""Template hygiene: the mistakes that render as visible text instead of failing.

A broken template usually raises, which is easy to notice. These two don't — they
produce a page that looks almost right, so they survive review. Both have already
shipped once in this project.
"""
from pathlib import Path

from django.conf import settings
from django.template import Context, Template
from django.test import TestCase


def template_files():
    """Every .html under the configured template directories."""
    for entry in settings.TEMPLATES:
        for directory in entry.get('DIRS', []):
            yield from sorted(Path(directory).rglob('*.html'))


class TemplateCommentTests(TestCase):
    """``{# #}`` is a single-line token. Spanning lines renders it as page text."""

    def test_django_still_does_not_strip_multi_line_comments(self):
        """Pins the behaviour this test exists to guard, so it can't silently change."""
        self.assertEqual(Template("A{# one line #}B").render(Context({})), 'AB')
        self.assertIn('{#', Template("A{# one\ntwo #}B").render(Context({})))

    def test_no_template_has_a_comment_that_spans_lines(self):
        offenders = []
        for path in template_files():
            depth = 0
            for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                opened = line.count('{#')
                closed = line.count('#}')
                if depth and (opened or closed or line.strip()):
                    offenders.append(f"{path.name}:{lineno}")
                    break
                depth += opened - closed
                if depth:
                    offenders.append(f"{path.name}:{lineno}")
                    break
        self.assertEqual(
            offenders, [],
            "A {# #} comment spanning lines is rendered as visible text. "
            "Use one {# ... #} per line. Offenders: " + ', '.join(offenders),
        )

    def test_every_template_has_balanced_tag_delimiters(self):
        """An unclosed ``{%`` or ``{{`` prints raw instead of raising."""
        offenders = []
        for path in template_files():
            text = path.read_text(encoding='utf-8')
            for opener, closer in (('{%', '%}'), ('{{', '}}'), ('{#', '#}')):
                if text.count(opener) != text.count(closer):
                    offenders.append(
                        f"{path.name}: {text.count(opener)}x'{opener}' vs "
                        f"{text.count(closer)}x'{closer}'"
                    )
        self.assertEqual(offenders, [], '; '.join(offenders))


class RenderedPageTests(TestCase):
    """No page ships template syntax in its output."""

    def test_key_pages_render_no_template_syntax(self):
        # follow=True: an unprefixed path is now a redirect into /uz/ and the
        # redirect body has no template output to inspect (§17 #121).
        for url in ('/', '/shop/'):
            with self.subTest(url=url):
                html = self.client.get(url, follow=True).content.decode('utf-8')
                for token in ('{#', '{%', '{{'):
                    self.assertNotIn(
                        token, html,
                        f"{url} leaks the template token {token} into its output",
                    )
