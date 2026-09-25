"""The project's test runner: every test starts in Uzbek, a failure under
``--parallel`` is reported instead of ending the run, and no test can notify
the real shop.

Two things made a failing suite hard to read, and both are fixed here rather
than in each test.

**The language one test leaves behind.** ``LocaleMiddleware`` activates the
language of every request it handles and nothing deactivates it afterwards. A
test that requests an ``/en/`` page leaves English active for whatever runs
next in the same process, so a bare ``reverse()`` in the next test builds an
``/en/`` URL and an assertion about Uzbek copy reads an English page
(§17 #124). Under ``--parallel`` "next" is whichever class the pool happens to
hand that worker, so the failure moves around as classes are added: Phase 8's
tests did it to a Phase 7 dashboard test that had passed for days. Resetting
the language as each test starts removes the order dependence from every test
at once (§17 #199).

**A traceback cannot cross a process without tblib.** The parallel runner
pickles each failure to send it to the parent, a traceback does not pickle,
and tblib is a dependency the project does not take (§4). So the first failing
assertion used to kill the worker pool, and every test still queued reported
an ``OperationalError`` about a test database that had already been dropped -
the real failure was one line in several hundred. A failure now travels as
text, with its own traceback in it, and the run finishes.

**A developer's .env is not a test's.** Once the bot service's address and
secret are pasted into ``.env``, a test that creates an order would send it to
the shop's staff (§17 #207). The run blanks every notification setting first;
a test that needs one sets it itself.
"""
import atexit
import os
import shutil
import tempfile
import traceback
import unittest

from django.conf import settings
from django.test.runner import (DiscoverRunner, ParallelTestSuite,
                                RemoteTestResult, RemoteTestRunner)
from django.utils import translation


def use_throwaway_media():
    """Send every upload a test makes to a temporary folder.

    Tests save real files through real storage, and MEDIA_ROOT is the
    developer's own `media/`, so a run used to leave its photographs there:
    over a thousand of them by the time anyone counted, mixed in with the
    demo catalogue's real pictures.

    Done here rather than with a mixin per test class, which was the earlier
    plan. A mixin has to be remembered by whoever writes the next test that
    saves a file, and the symptom of forgetting is invisible. Setting it once
    for the run cannot be forgotten and covers tests that do not exist yet.
    The folder is removed when the run ends.

    It matters more since a deleted row deletes its file: a test that deletes
    a product must never be pointed at the folder holding real photographs.
    """
    folder = tempfile.mkdtemp(prefix='gx-test-media-')
    settings.MEDIA_ROOT = folder
    atexit.register(shutil.rmtree, folder, ignore_errors=True)
    return folder


#: Settings that reach a live outside service - the shop's Telegram.
OFFLINE = ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID',
           'TELEGRAM_BOT_WEBHOOK_URL', 'WEBSITE_WEBHOOK_SECRET')


def project_python_files():
    """Yield every ``.py`` file this project wrote, and none it merely installed.

    The apps and the settings package sit at the repository root now, beside
    ``.venv``, ``.git``, ``docs`` and ``deploy``. A test that wants to read the
    project's own source therefore cannot walk ``BASE_DIR`` any more: it would
    parse every installed dependency and every scratch script on the machine,
    and one of those failing to compile would fail the test for a reason that
    has nothing to do with the site. That is exactly what happened when the
    repository was flattened.

    Django already knows where each installed app lives, so ask it and keep the
    ones that are direct children of the repository root - which excludes
    everything under ``.venv`` without naming ``.venv``. The settings package is
    added separately because it is not an app, and it is found through
    ``SETTINGS_MODULE`` so that renaming it again cannot leave this behind.

    Migrations and the tests themselves are left out: neither is user-facing
    code, and both are written in shapes these scans would misread.

    Yields ``(path, rel)`` pairs sorted by path, where ``rel`` names the file
    the way a developer would, so a failure message can quote it.
    """
    from pathlib import Path

    from django.apps import apps

    base = Path(settings.BASE_DIR)
    roots = [Path(c.path) for c in apps.get_app_configs()
             if Path(c.path).parent == base]
    roots.append(base / settings.SETTINGS_MODULE.split('.')[0])
    for path in sorted({p for root in roots for p in root.rglob('*.py')}):
        rel = path.relative_to(base).as_posix()
        if 'migrations/' in rel or '/test' in rel:
            continue
        yield path, rel


def go_offline():
    """Blank :data:`OFFLINE` in this process and in every worker it starts.

    A worker started by ``spawn`` - the only way on Windows - imports the
    settings afresh, and python-dotenv never overrides a variable that is
    already set, an empty one included. So a blank in the environment reaches
    the workers, and the attribute covers this process, whose settings are
    already loaded.
    """
    for name in OFFLINE:
        os.environ[name] = ''
        setattr(settings, name, '')


class ReportedFailure(AssertionError):
    """A failed assertion from a worker, carried as the text of its traceback.

    An ``AssertionError`` so the parent still counts it as a failure and not
    as an error.
    """


class ReportedError(Exception):
    """An exception from a worker, carried as the text of its traceback."""


def _portable(err):
    """``err`` (an ``exc_info`` tuple) in a form that survives pickling.

    The traceback is formatted in the worker, where it still exists, and
    travels as the message; the class says whether it was a failure.
    """
    exc_type, exc, tb = err
    text = ''.join(traceback.format_exception(exc_type, exc, tb)).rstrip()
    carrier = ReportedFailure if issubclass(exc_type, AssertionError) else ReportedError
    return carrier, carrier(text), None


class StartsInUzbek:
    """Result mixin: activate the default language before every test."""

    def startTest(self, test):
        translation.activate(settings.LANGUAGE_CODE)
        super().startTest(test)


class WorkerResult(StartsInUzbek, RemoteTestResult):
    """The result a parallel worker records, with failures made portable."""

    def addError(self, test, err):
        super().addError(test, _portable(err))

    def addFailure(self, test, err):
        super().addFailure(test, _portable(err))

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, None if err is None else _portable(err))


class WorkerRunner(RemoteTestRunner):
    """Runs one worker's share of the suite with :class:`WorkerResult`."""

    resultclass = WorkerResult


class WorkerSuite(ParallelTestSuite):
    """Hands :class:`WorkerRunner` to each worker process."""

    runner_class = WorkerRunner

    #: Runs inside each worker, before Django is set up there.
    #:
    #: Only Django calls it, and only when the start method is spawn or
    #: forkserver - which is Windows. A forked worker inherits the parent's
    #: memory and already has the throwaway MEDIA_ROOT that
    #: `Runner.setup_test_environment` set; a spawned one is a fresh
    #: interpreter that has never seen it, and would write into the
    #: developer's real `media/`. The serial path and the forked path were
    #: both green while `--parallel` on Windows was still leaking, which is
    #: the reason this is a separate hook and not an oversight.
    process_setup = use_throwaway_media


class Runner(DiscoverRunner):
    """``TEST_RUNNER``: Django's runner with the three fixes above.

    Both the serial and the parallel path get the language reset; only the
    parallel one needs its failures made portable. The notification settings
    are blanked before the suite is built, so before any worker starts.
    """

    parallel_test_suite = WorkerSuite

    def setup_test_environment(self, **kwargs):
        go_offline()
        use_throwaway_media()
        super().setup_test_environment(**kwargs)

    def get_resultclass(self):
        # Keep --debug-sql and --pdb working: they choose a result class of
        # their own, and the reset is mixed into whichever one it is.
        base = super().get_resultclass() or unittest.TextTestResult
        return type(f'StartsInUzbek{base.__name__}', (StartsInUzbek, base), {})
