import re

from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


phone_regex = RegexValidator(
    regex=r'^\+998 ?\d{2} ?\d{3} ?\d{2} ?\d{2}$',
    message="format: +998 XX XXX XX XX"
)


def normalize_uz_phone(value):
    """
    Normalize an Uzbek phone number to the canonical '+998 XX XXX XX XX' format,
    independent of how the input was separated (spaces, dashes, dots, parens, etc).

    Accepts, e.g.:
        +998-90-123-45-67
        +998 (90) 123 45 67
        998901234567
        90 123 45 67          (national number, country code added)

    Returns the input UNCHANGED if it can't be normalized to a 9-digit national
    number, so the RegexValidator on the field still rejects genuinely invalid
    input during full_clean(). This makes the result correct even for direct ORM
    saves (shell, fixtures, admin) that bypass form-level validation.
    """
    if not value:
        return value

    digits = re.sub(r'\D', '', value)  # keep digits only

    # Drop a leading 998 country code if present (12 digits total).
    if len(digits) == 12 and digits.startswith('998'):
        digits = digits[3:]

    if len(digits) == 9:
        return f"+998 {digits[:2]} {digits[2:5]} {digits[5:7]} {digits[7:9]}"

    return value


class User(AbstractUser):
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
        # Canonicalize before saving so the stored value is always in the
        # +998 XX XXX XX XX format regardless of input separators.
        self.phone = normalize_uz_phone(self.phone)
        super().save(*args, **kwargs)
