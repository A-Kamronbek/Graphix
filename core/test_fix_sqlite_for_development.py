"""Which database the settings choose: SQLite for a developer, PostgreSQL for the shop.

``DEBUG`` is the switch. It is on only on a developer's machine, where the
site should start with nothing to install; the server has it off and is on
PostgreSQL as before.

The choice is made while ``settings.py`` is being read, from the environment
as it is at that moment, so nothing here can be asserted in this process:
by the time a test runs the choice has been made. Each case reads the
settings in a process of its own, as ``DeployCheckTests`` does.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase

SQLITE = 'django.db.backends.sqlite3'
POSTGRESQL = 'django.db.backends.postgresql'
#: Stand-ins for the PostgreSQL keys. Reading the settings opens no connection.
KEYS = {'DB_NAME': 'graphix', 'DB_USER': 'graphix', 'DB_PASSWORD': 'graphix'}


def chosen(**env):
    """What ``DATABASES['default']`` is with ``env`` laid over this process's."""
    run = subprocess.run(
        [sys.executable, '-c',
         "import django; django.setup(); from django.conf import settings; "
         "db = settings.DATABASES['default']; print(db['ENGINE'], db['NAME'])"],
        cwd=str(Path(settings.BASE_DIR)),
        env=dict(os.environ, DJANGO_SETTINGS_MODULE='config.settings', **env),
        capture_output=True, text=True, encoding='utf-8')
    assert run.returncode == 0, run.stderr
    engine, name = run.stdout.strip().split(' ', 1)
    return engine, name


class DatabaseChoiceTests(SimpleTestCase):
    """DEBUG on is SQLite, DEBUG off is PostgreSQL, and CI says which it wants."""

    def test_a_developers_machine_is_on_sqlite(self):
        # An empty DB_ENGINE, not a missing one: a .env file would otherwise
        # be free to put it back.
        engine, name = chosen(DEBUG='True', DB_ENGINE='')
        self.assertEqual(engine, SQLITE)
        self.assertEqual(Path(name), Path(settings.BASE_DIR) / 'db.sqlite3')

    def test_the_server_is_on_postgresql(self):
        engine, name = chosen(DEBUG='False', DB_ENGINE='', **KEYS)
        self.assertEqual((engine, name), (POSTGRESQL, 'graphix'))

    def test_postgresql_can_be_kept_with_debug_on(self):
        engine, name = chosen(DEBUG='True', DB_ENGINE='postgresql', **KEYS)
        self.assertEqual((engine, name), (POSTGRESQL, 'graphix'))

    def test_only_that_one_word_keeps_it(self):
        for word in ('sqlite', 'postgres', 'True', '1'):
            with self.subTest(word=word):
                self.assertEqual(chosen(DEBUG='True', DB_ENGINE=word)[0], SQLITE)

    @unittest.skipUnless(os.environ.get('CI'), 'only CI is held to PostgreSQL')
    def test_ci_runs_the_suite_on_postgresql(self):
        """The suite has DEBUG on. Without its DB_ENGINE line CI would run
        every test on SQLite and go on reporting green, with the checkout's
        row lock tested against an engine that takes none."""
        self.assertEqual(connection.vendor, 'postgresql')
