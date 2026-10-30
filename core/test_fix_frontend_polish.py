"""The front end's own housekeeping (§17 #424).

A pass over the stylesheets, scripts and templates found two pages drawing
each other's rules, blocks the panel renders but whose rules lived in a sheet
the panel does not load, rules nothing renders, one fetch helper written three
times, and template libraries loaded and never used. Each class here holds
one of those shut, by reading the files a browser and Django read.
"""
import re
from pathlib import Path

from django.conf import settings
from django.template import engines
from django.test import SimpleTestCase

BASE = Path(settings.BASE_DIR)
CSS = BASE / 'static' / 'css'
JS = BASE / 'static' / 'js'
TEMPLATES = BASE / 'templates'


def sheet(name):
    """A stylesheet with its comments taken out, so prose cannot match."""
    return re.sub(r'/\*.*?\*/', '', (CSS / name).read_text(encoding='utf-8'), flags=re.S)


def classes_in(css):
    """Every class a stylesheet's selectors name."""
    selectors = ' '.join(m.group(1) for m in re.finditer(r'([^{}]+)\{', css)
                         if not m.group(1).strip().startswith('@'))
    return set(re.findall(r'\.([a-zA-Z][\w-]*)', selectors))


def rules(css, selector):
    """The bodies of every rule whose selector list is exactly `selector`."""
    return [body for sel, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css)
            if sel.strip() == selector]


def template_text(path):
    """A template without its comments: a class named in a note is not used."""
    text = path.read_text(encoding='utf-8')
    text = re.sub(r'\{#.*?#\}', '', text, flags=re.S)
    return re.sub(r'\{% comment %\}.*?\{% endcomment %\}', '', text, flags=re.S)


def classes_used(paths):
    """The classes the templates write into `class="…"`, template tags read as gaps."""
    used = set()
    for path in paths:
        for attr in re.findall(r'class="([^"]*)"', template_text(path)):
            attr = re.sub(r'\{%.*?%\}|\{\{.*?\}\}', ' ', attr)
            used.update(attr.split())
    return used


def panel_templates():
    """The panel's templates and the storefront partials they include."""
    own = [p for p in (TEMPLATES / 'boshqaruv').rglob('*.html') if p.name != 'style.html']
    shared = set()
    for path in own:
        for name in re.findall(r'{% include "([^"]+)"', template_text(path)):
            if not name.startswith('boshqaruv/'):
                shared.add(TEMPLATES / name)
    return own + sorted(shared)


class TwoStepListsTests(SimpleTestCase):
    """The order page's track and the status page's steps are two blocks.

    Both were `.steps`. The status page's list was laid out in the order
    page's four columns, and the order page's bars took the status page's
    `gap: 0` and touched."""

    def test_the_status_page_alone_is_steps(self):
        css = sheet('pages.css')
        self.assertEqual(len(rules(css, '.steps')), 1)
        self.assertNotIn('repeat(4', rules(css, '.steps')[0])
        self.assertFalse(re.search(r'\.steps\s+li\b', css))
        status = (TEMPLATES / 'payment' / 'status.html').read_text(encoding='utf-8')
        self.assertIn('class="steps"', status)
        self.assertNotIn('class="track"', status)

    def test_the_line_between_steps_runs_behind_the_dots(self):
        """The joining line is a positioned `::before`; an unpositioned dot is painted under it."""
        css = sheet('pages.css')
        self.assertIn('position: absolute', rules(css, '.steps__step + .steps__step::before')[0])
        self.assertIn('position: relative', rules(css, '.steps__dot')[0])

    def test_the_order_page_is_a_track_of_four(self):
        css = sheet('pages.css')
        self.assertIn('repeat(4, minmax(0, 1fr))', rules(css, '.track')[0])
        self.assertIn('gap: var(--s-3)', rules(css, '.track')[0])
        page = (TEMPLATES / 'payment' / 'order_detail.html').read_text(encoding='utf-8')
        self.assertIn('class="track"', page)
        self.assertEqual(page.count('class="track__step'), 4)
        self.assertNotIn('class="steps"', page)


class SharedBlocksTests(SimpleTestCase):
    """A block both shells render is styled by a sheet both shells load.

    The panel loads tokens, base, components and panel; the storefront loads
    tokens, base, components and pages. The pager's flipped "previous"
    chevron, the small stars and the return requests' list were in pages.css,
    so in the panel the arrow pointed forwards and the list had no indent."""

    def test_nothing_the_panel_renders_is_styled_only_by_pages_css(self):
        panel = classes_in(sheet('base.css')) | classes_in(sheet('components.css')) \
            | classes_in(sheet('panel.css'))
        only_pages = (classes_used(panel_templates()) & classes_in(sheet('pages.css'))) - panel
        self.assertEqual(only_pages, set())

    def test_the_style_guide_is_drawn_by_the_sheets_it_loads(self):
        page = TEMPLATES / 'boshqaruv' / 'style.html'
        text = page.read_text(encoding='utf-8')
        own = classes_in(re.sub(r'/\*.*?\*/', '', ''.join(re.findall(r'<style[^>]*>(.*?)</style>', text, flags=re.S)), flags=re.S))
        loaded = classes_in(sheet('base.css')) | classes_in(sheet('components.css')) | own
        elsewhere = classes_in(sheet('pages.css')) | classes_in(sheet('panel.css'))
        self.assertEqual((classes_used([page]) & elsewhere) - loaded, set())

    def test_one_pager_for_both_shells(self):
        definitions = [name for name in ('base.css', 'components.css', 'pages.css', 'panel.css')
                       if rules(sheet(name), '.pager')]
        self.assertEqual(definitions, ['components.css'])
        self.assertEqual(rules(sheet('base.css'), '.i--flip'), [' transform: rotate(180deg); '])

    def test_no_selector_is_written_in_two_sheets(self):
        def selectors(name):
            found = set()
            for sel in re.findall(r'([^{}]+)\{', sheet(name)):
                if not sel.strip().startswith('@'):
                    found.update(s.strip() for s in re.split(r',(?![^(]*\))', sel))
            return found
        names = ('base.css', 'components.css', 'pages.css', 'panel.css')
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                with self.subTest(a=a, b=b):
                    self.assertEqual(selectors(a) & selectors(b), set())


class DeadRulesTests(SimpleTestCase):
    """Every class a stylesheet styles is one something renders.

    A rule nothing renders still has to be read, and it misleads: `.modal`
    described a sheet the checkout no longer has, and `.i--solid` was
    documented in the sprite for icons that fill themselves. A class built
    from a value at run time is named here, with where it is built."""

    BUILT = {
        'toast--success', 'toast--danger',          # main.js and panel.js: 'toast--' + kind
        'design__chip--white', 'design__chip--black',
        'design__chip--grey', 'design__chip--other',  # custom_design.html: design__chip--{{ value }}
        'js',                                          # base.html's first script: html.js
    }

    def used(self):
        found = classes_used(TEMPLATES.rglob('*.html'))
        code = ' '.join(p.read_text(encoding='utf-8') for p in JS.glob('*.js'))
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.S)
        for literal in re.findall(r"'([^'\n]*)'|\"([^\"\n]*)\"", code):
            for text in literal:
                found.update(re.findall(r'[a-zA-Z][\w-]*', text))
        return found

    def test_every_class_is_rendered_somewhere(self):
        used = self.used() | self.BUILT
        for name in ('base.css', 'components.css', 'pages.css', 'panel.css'):
            with self.subTest(sheet=name):
                self.assertEqual(classes_in(sheet(name)) - used, set())


class TapTargetTests(SimpleTestCase):
    """The floor a finger needs is one token, not thirty copies of 44px."""

    def test_the_floor_is_a_token(self):
        self.assertIn('--tap: 44px;', (CSS / 'tokens.css').read_text(encoding='utf-8'))
        self.assertIn('--nav-h: calc(var(--tap)', (CSS / 'tokens.css').read_text(encoding='utf-8'))

    def test_no_sheet_writes_the_number(self):
        for name in ('base.css', 'components.css', 'pages.css', 'panel.css'):
            css = sheet(name)
            # The panel's switch is a 44 px drawing of a track, not a target.
            css = css.replace('.switch input { appearance: none; width: 44px;', '')
            with self.subTest(sheet=name):
                self.assertNotIn('44px', css)


class ScriptHelpersTests(SimpleTestCase):
    """The panel saves through one helper; main.js exports what is borrowed."""

    def test_the_panel_has_one_fetch(self):
        panel = (JS / 'panel.js').read_text(encoding='utf-8')
        self.assertEqual(panel.count('fetch('), 1)
        self.assertEqual(panel.count('function SEND('), 1)
        for gone in ('function csrf(', 'function token(', 'function post(', 'function send('):
            self.assertNotIn(gone, panel)

    def test_every_export_has_a_borrower(self):
        scripts = {p.name: p.read_text(encoding='utf-8') for p in JS.glob('*.js')}
        for owner, text in scripts.items():
            for name in re.findall(r'^\s*GX\.(\w+) = ', text, flags=re.M):
                with self.subTest(export=name, owner=owner):
                    borrowers = [n for n, t in scripts.items()
                                 if re.search(r'GX\.' + name + r'\b(?! = )', t)]
                    self.assertTrue(borrowers)


class TemplateLibrariesTests(SimpleTestCase):
    """A template loads the libraries it uses and no others."""

    def test_no_library_is_loaded_and_left_unused(self):
        libraries = engines['django'].engine.template_libraries
        for path in sorted(TEMPLATES.rglob('*.html')):
            text = path.read_text(encoding='utf-8')
            for load in re.finditer(r'{%\s*load\s+([^%]+?)\s*%}', text):
                rest = text[:load.start()] + text[load.end():]
                for name in load.group(1).split():
                    library = libraries[name]
                    words = set(library.tags) | set(library.filters)
                    used = any(re.search(r'\{%\s*' + w + r'\b|\|\s*' + w + r'\b', rest) for w in words)
                    with self.subTest(template=str(path.relative_to(TEMPLATES)), library=name):
                        self.assertTrue(used)
