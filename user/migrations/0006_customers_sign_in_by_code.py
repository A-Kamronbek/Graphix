"""Customers sign in by phone and code, so their usernames and passwords go.

From this change a customer has no username to remember and no password
(§17 #309). Each customer row gets its phone number as its username, written
without spaces, and a password that can never match. Nothing is deleted.

Staff rows are left exactly as they are: staff sign in at ``/admin/`` with the
username and password they have.

A password that changes ends every session opened with the old one, so each
customer who was signed in is signed out once and comes back in with a code.

There is no way back for the passwords, so going backwards changes nothing.
The code this migration ships with never asks for one.
"""
import re

from django.contrib.auth.hashers import make_password
from django.db import migrations


def digits_of(phone):
    """The nine national digits of a number, or None if it is not one."""
    digits = re.sub(r'[^0-9]', '', phone or '')
    if len(digits) == 12 and digits.startswith('998'):
        digits = digits[3:]
    return digits if len(digits) == 9 else None


def forwards(apps, schema_editor):
    """Give every customer their number for a username and no usable password."""
    User = apps.get_model('user', 'User')
    staff = User.objects.filter(is_staff=True) | User.objects.filter(is_superuser=True)
    rows = list(User.objects.exclude(pk__in=staff.values('pk'))
                .only('pk', 'phone', 'username', 'password'))

    # Everything that would stop a row being saved is looked for first and
    # said in words, so the migration either does all of its work or none.
    national = {row.pk: digits_of(row.phone) for row in rows}
    odd = sorted(pk for pk, digits in national.items() if digits is None)
    if odd:
        raise RuntimeError(
            "These accounts have a phone that is not an Uzbek number, so nobody could "
            "sign in to them by SMS: ids %s. Correct or remove them in the admin, then "
            "migrate again." % odd)
    seen, twice = {}, []
    for pk, digits in national.items():
        if digits in seen:
            twice.append((seen[digits], pk))
        seen[digits] = pk
    if twice:
        raise RuntimeError(
            "These pairs of accounts hold the same phone number written two ways: ids %s. "
            "Keep one of each pair in the admin, then migrate again." % twice)
    names = {'+998' + digits for digits in national.values()}
    clash = sorted(names & set(staff.values_list('username', flat=True)))
    if clash:
        raise RuntimeError(
            "A staff account is named like a customer's phone number: %s. "
            "Give it another username in the admin, then migrate again." % ', '.join(clash))

    # In two steps, because a customer could already be named like another
    # customer's number: every name is moved out of the way before any number
    # is written.
    for row in rows:
        row.username = 'phase15-%d' % row.pk
    User.objects.bulk_update(rows, ['username'], batch_size=500)
    for row in rows:
        d = national[row.pk]
        row.username = '+998' + d
        # Written the one way the site looks numbers up, in case a row was
        # ever saved around the model's own tidying.
        row.phone = '+998 %s %s %s %s' % (d[:2], d[2:5], d[5:7], d[7:9])
        row.password = make_password(None)
    User.objects.bulk_update(rows, ['username', 'phone', 'password'], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0005_consent_versions'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
