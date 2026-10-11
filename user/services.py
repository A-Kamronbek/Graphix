"""Making a customer's account.

An account is made in one place and at one moment: when the code sent to a
new number has been entered (§17 #309). Nothing is written for a number that
never confirms, so there is no half-made account to tidy up afterwards and no
path in the project that deletes one.
"""
import secrets

from django.db import IntegrityError, transaction

from .models import User, normalize_uz_phone


def is_staff_account(user):
    """Is this one of the shop's own accounts?

    Staff sign in with a password at the admin's form and are never sent a
    code. A superuser counts whether or not the staff box is ticked: this is
    the one place that says who is on which side of that line.
    """
    return user is not None and (user.is_staff or user.is_superuser)


def username_for(phone):
    """A customer's username: their number, as ``+998XXXXXXXXX``.

    Nobody types it and nothing shows it; Django needs the column filled and
    unique, and the number already is. Staff keep the names they sign in to
    the Django admin with.
    """
    return '+' + ''.join(ch for ch in phone if ch.isdigit())


def available_username(phone, skip=None):
    """:func:`username_for`, or that with a tail when another row holds it.

    The name is only ever a placeholder, so when it is taken (a staff account
    named like a number, or a row somebody edited by hand) the customer is
    not the one who should be stopped by it.
    """
    name = username_for(phone)
    taken = User.objects.filter(username=name)
    if skip is not None:
        taken = taken.exclude(pk=skip)
    return '%s.%s' % (name, secrets.token_hex(3)) if taken.exists() else name


def create_customer(phone, versions=None):
    """The account for a number that has just been confirmed.

    No usable password: the code is the only way in. ``versions`` are the
    document versions the customer agreed to at sign-up (§17 #272).

    Two browsers can confirm the same new number at once. Both proved they
    hold it, so the second is given the account the first one made.
    """
    user = User(username=available_username(phone), phone=phone, phone_verified=True,
                **(versions or {}))
    user.set_unusable_password()
    try:
        with transaction.atomic():
            user.save()
    except IntegrityError:
        made = User.objects.filter(phone=normalize_uz_phone(phone)).first()
        if made is None:
            raise
        return made
    return user


def is_registered(user):
    """Does this row count as an account at the two doors?

    Before accounts waited for the code, a sign-up wrote its row first, and
    one that was never finished may still be there. Nobody proved they hold
    that number or agreed to anything as its holder, so it is not an account
    yet: its number signs up like a new one, and :func:`claim_unconfirmed`
    hands the row over. Staff are made in the admin and always count.
    """
    return user is not None and (user.phone_verified or is_staff_account(user))


def claim_unconfirmed(user, versions=None):
    """Hand a row left by an unfinished sign-up to whoever confirmed its number.

    The name on it was typed by someone who never showed they hold the
    number, so it is cleared; the consent is the one just given.
    """
    user.first_name = ''
    user.username = available_username(user.phone, skip=user.pk)
    user.phone_verified = True
    user.terms_version = (versions or {}).get('terms_version', '')
    user.privacy_version = (versions or {}).get('privacy_version', '')
    user.set_unusable_password()
    user.save()
    return user


def rekey(user):
    """Give a customer the username of their number and end every session they have.

    For when staff change a customer's number: the account now belongs to
    whoever holds the new one. An unusable password is a random value, and a
    new one makes every session opened before it stop being that account's.
    """
    user.username = available_username(user.phone, skip=user.pk)
    user.set_unusable_password()
