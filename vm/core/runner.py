"""The project's test runner: every test starts in Uzbek, and a failure under
``--parallel`` is reported instead of ending the run.

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
"""
import traceback
import unittest

from django.conf import settings
from django.test.runner import (DiscoverRunner, ParallelTestSuite,
                                RemoteTestResult, RemoteTestRunner)
from django.utils import translation


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


class Runner(DiscoverRunner):
    """``TEST_RUNNER``: Django's runner with the two fixes above.

    Both the serial and the parallel path get the language reset; only the
    parallel one needs its failures made portable.
    """

    parallel_test_suite = WorkerSuite

    def get_resultclass(self):
        # Keep --debug-sql and --pdb working: they choose a result class of
        # their own, and the reset is mixed into whichever one it is.
        base = super().get_resultclass() or unittest.TextTestResult
        return type(f'StartsInUzbek{base.__name__}', (StartsInUzbek, base), {})
