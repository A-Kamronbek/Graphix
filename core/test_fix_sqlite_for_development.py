"""Which database the settings choose: a configured PostgreSQL, or SQLite for a developer.

One rule for every machine. Where ``DB_NAME`` is set, that PostgreSQL database
is used: the server's ``.env`` sets it and so does CI's environment, so
neither needs telling. A machine that sets none is a developer's and runs on
SQLite, which is allowed only with ``DEBUG`` on.

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
#: A PostgreSQL configuration. Reading the settings opens no connection.
KEYS = {'DB_NAME': 'graphix', 'DB_USER': 'graphix', 'DB_PASSWORD': 'graphix'}
#: No database named. Empty, not missing: a .env file would otherwise be free
#: to put the key back.
NONE = {'DB_NAME': ''}


def read_settings(**env):
    """Read the settings with ``env`` laid over this process's environment."""
    return subprocess.run(
        [sys.executable, '-c',
         "import django; django.setup(); from django.conf import settings; "
         "db = settings.DATABASES['default']; print(db['ENGINE'], db['NAME'])"],
        cwd=str(Path(settings.BASE_DIR)),
        env=dict(os.environ, DJANGO_SETTINGS_MODULE='config.settings', **env),
        capture_output=True, text=True, encoding='utf-8')


def chosen(**env):
    """The engine and the name of ``DATABASES['default']`` under ``env``."""
    run = read_settings(**env)
    assert run.returncode == 0, run.stderr
    engine, name = run.stdout.strip().split(' ', 1)
    return engine, name


class DatabaseChoiceTests(SimpleTestCase):
    """A database that is named is used; SQLite is what a developer gets without one."""

    def test_a_machine_that_names_no_database_is_on_sqlite(self):
        engine, name = chosen(DEBUG='True', **NONE)
        self.assertEqual(engine, SQLITE)
        self.assertEqual(Path(name), Path(settings.BASE_DIR) / 'db.sqlite3')

    def test_the_server_is_on_postgresql(self):
        self.assertEqual(chosen(DEBUG='False', **KEYS), (POSTGRESQL, 'graphix'))

    def test_a_named_database_is_used_with_debug_on_as_well(self):
        """CI's case, and a developer's who has PostgreSQL: no flag, the same rule."""
        self.assertEqual(chosen(DEBUG='True', **KEYS), (POSTGRESQL, 'graphix'))

    def test_with_debug_off_and_no_database_the_site_does_not_start(self):
        """A server that lost its .env must stop. It must not open an empty
        SQLite file and take orders into it."""
        run = read_settings(DEBUG='False', **NONE)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('DB_NAME is not set', run.stderr)
        self.assertNotIn('sqlite', run.stdout)

    @unittest.skipUnless(os.environ.get('CI'), 'only CI is held to PostgreSQL')
    def test_ci_runs_the_suite_on_postgresql(self):
        """The suite must run on the engine the shop runs on: SQLite takes no
        row locks, so the lock the checkout puts on a cart would be tested
        against nothing. CI names a database, and this fails if it stops."""
        self.assertEqual(connection.vendor, 'postgresql')
