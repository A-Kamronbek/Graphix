"""Report strings the source produces that the catalogues do not carry.

Every catalogue test in `core/test_i18n.py` reads a `.po` file against
itself: no empty translation, no fuzzy entry, the three languages covering
the same msgids. All of them pass while a template string quietly stops
matching its catalogue entry, because a msgid that is in the source and not
in the `.po` is not in the `.po` for any test to find. gettext then falls
back to the msgid, and a Russian visitor reads Uzbek with nothing logged and
nothing failing. That happened once (see the decision log, #243) and cost a
page of Russian copy for several days.

Answering the question means extracting msgids again and comparing, and
`makemessages` insists on writing to `./locale` - it puts that path ahead of
`LOCALE_PATHS`. So this is a developer command and not a test: it reads the
committed catalogues, lets `makemessages` overwrite them, compares, and puts
them back with git. It refuses to start unless `locale/` is clean, and it
says so loudly if the restore does not take.

Never run it on a server. It rewrites tracked files and relies on git to
undo that.
"""
import os
import subprocess

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

#: The three catalogues, in the order the report prints them.
LANGS = ('uz', 'ru', 'en')


def catalogue_path(lang):
    """Where ``lang``'s catalogue lives."""
    from pathlib import Path
    return Path(settings.LOCALE_PATHS[0]) / lang / 'LC_MESSAGES' / 'django.po'


def _fuzzy_above(lines, at):
    """Whether the comment block above line ``at`` carries the fuzzy flag.

    gettext writes an entry's flags on one comma-separated line, so a string
    with a placeholder reads ``#, fuzzy, python-format``. Matching a bare
    ``#, fuzzy`` misses those, which is how a fuzzy add-to-cart button once
    got past two separate checks.
    """
    k = at - 1
    while k >= 0 and lines[k].startswith('#'):
        if lines[k].strip().startswith('#,') and 'fuzzy' in lines[k]:
            return True
        k -= 1
    return False


def read_catalogue(path):
    """``(active, obsolete, fuzzy)`` sets of msgids from a ``.po`` file.

    Continuation lines are joined rather than ignored: gettext wraps anything
    long across several quoted strings, and a reader that looks at the first
    line only sees ``msgid ""`` - which is also what the header looks like,
    so every long entry would be mistaken for it.

    An obsolete entry is the same shape behind a ``#~`` marker, including its
    continuation lines, and is kept apart because it is a record of a string
    the source no longer produces, not a problem.
    """
    lines = path.read_text(encoding='utf-8').splitlines()
    active, obsolete, fuzzy = set(), set(), set()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        dead = line.startswith('#~ msgid "')
        if not (dead or line.startswith('msgid "')):
            i += 1
            continue
        body = line[3:] if dead else line
        parts, j = [body[7:-1]], i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if dead and nxt.startswith('#~ "'):
                parts.append(nxt[4:-1])
            elif not dead and nxt.startswith('"'):
                parts.append(nxt[1:-1])
            else:
                break
            j += 1
        text = ''.join(parts)
        if text:                      # an empty msgid is the catalogue header
            (obsolete if dead else active).add(text)
            if not dead and _fuzzy_above(lines, i):
                fuzzy.add(text)
        i = j
    return active, obsolete, fuzzy


class Command(BaseCommand):
    help = ('Compare a fresh extraction with the committed catalogues. '
            'Rewrites locale/ and restores it with git; never run on a server.')

    def git(self, *args):
        """Run a git command in the project root and return it."""
        return subprocess.run(('git',) + args, cwd=str(settings.BASE_DIR),
                              capture_output=True, text=True, encoding='utf-8')

    def handle(self, *args, **options):
        """Snapshot, re-extract, compare, put the catalogues back.

        The restore is in a ``finally`` and is checked afterwards, because a
        half-restored catalogue directory is a worse thing to leave behind
        than an unanswered question.
        """
        dirty = self.git('status', '--porcelain', 'locale').stdout.strip()
        if dirty:
            raise CommandError(
                'locale/ has uncommitted changes, so it cannot be restored '
                'afterwards. Commit or stash them first:\n' + dirty)

        before = {lang: read_catalogue(catalogue_path(lang))[0]
                  for lang in LANGS}

        # makemessages resolves ./locale from the working directory, so the
        # command must not depend on where it was called from.
        here = os.getcwd()
        try:
            os.chdir(settings.BASE_DIR)
            call_command('makemessages', all=True, verbosity=0)
            after = {lang: read_catalogue(catalogue_path(lang))
                     for lang in LANGS}
        finally:
            os.chdir(here)
            self.git('checkout', '--', 'locale')

        left = self.git('status', '--porcelain', 'locale').stdout.strip()
        if left:
            raise CommandError(
                'locale/ could NOT be restored and is still rewritten. '
                'Run `git checkout -- locale` yourself:\n' + left)

        self.report(before, after)

    def report(self, before, after):
        """Print what changed, loudest first, and raise if anything is wrong.

        Only two of the three findings are defects. A missing msgid is a
        string rendering Uzbek on a translated page right now; a fuzzy one is
        the same thing wearing a translation gettext refuses to use. An
        obsolete entry is a translation for a string the source stopped
        producing - a record, and harmless.
        """
        broken = 0
        for lang in LANGS:
            active, obsolete, fuzzy = after[lang]
            missing = sorted(active - before[lang])
            dead = sorted(before[lang] - active)
            broken += len(missing) + len(fuzzy)
            self.stdout.write(
                '%s: %d strings, %d missing from the catalogue, %d fuzzy, '
                '%d no longer in the source, %d obsolete entries kept'
                % (lang, len(active), len(missing), len(fuzzy), len(dead),
                   len(obsolete)))
            for text in missing:
                self.stdout.write('  MISSING  %s' % text[:200])
            for text in sorted(fuzzy):
                self.stdout.write('  FUZZY    %s' % text[:200])
            for text in dead:
                self.stdout.write('  UNUSED   %s' % text[:200])

        if broken:
            raise CommandError(
                '%d string(s) will render Uzbek on a translated page. Run '
                '`makemessages`, write the translations by hand, and clear '
                'every fuzzy flag before committing.' % broken)
        self.stdout.write(self.style.SUCCESS(
            'Every string the source produces is translated in all three '
            'languages.'))
