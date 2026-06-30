"""User model and Uzbek phone-number handling.

Defines the custom :class:`User` (phone-based authentication, no email) together
with the validator and normaliser that keep every stored phone number in the
canonical ``+998 XX XXX XX XX`` format.
"""
import re

from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


# Accepts ``+998 XX XXX XX XX`` with optional spaces; ``message`` is user-facing.
phone_regex = RegexValidator(
    regex=r'^\+998 ?\d{2} ?\d{3} ?\d{2} ?\d{2}$',
    message="format: +998 XX XXX XX XX"
)


def normalize_uz_phone(value):
    """Return ``value`` in canonical ``+998 XX XXX XX XX`` form.

    Strips everything but digits, drops a leading ``998`` country code, and
    reformats a bare 9-digit national number. Anything that doesn't look like a
    valid UZ number is returned unchanged so the validator can reject it.
    """
    if not value:
        return value

    digits = re.sub(r'\D', '', value)  # keep digits only

    if len(digits) == 12 and digits.startswith('998'):
        digits = digits[3:]

    if len(digits) == 9:
        return f"+998 {digits[:2]} {digits[2:5]} {digits[5:7]} {digits[7:9]}"

    return value


class User(AbstractUser):
    """User authenticated by phone number instead of email.

    ``phone`` is unique and validated against :data:`phone_regex`;
    ``phone_verified`` records whether the number passed OTP confirmation.
    """
    phone = models.CharField(
        validators=[phone_regex],
        max_length=17,
        unique=True,
        error_messages={
            'unique': "Ushbu raqam allaqachon ro'yxatdan o'tgan.",
        },
    )
    phone_verified = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        """Normalise the phone number before every save.

        Normalising here (not only in the form) guarantees the stored value is
        always canonical, so the ``unique`` constraint can't be bypassed by two
        differently-spaced versions of the same number.
        """
        self.phone = normalize_uz_phone(self.phone)
        super().save(*args, **kwargs)
