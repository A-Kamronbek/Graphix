"""Password validators with Uzbek-language messages."""
from django.contrib.auth.password_validation import MinimumLengthValidator
from django.core.exceptions import ValidationError


class CustomMinimumLengthValidator(MinimumLengthValidator):
    """Minimum-length validator that reports the error in Uzbek.

    Behaves exactly like Django's :class:`MinimumLengthValidator` but replaces
    the default English messages with localised ones.
    """

    def validate(self, password, user=None):
        """Raise :class:`ValidationError` if ``password`` is shorter than ``min_length``."""
        if len(password) < self.min_length:
            raise ValidationError(
                "Parol 8 belgidan kam bo'lmasligi kerak.",
                code='password_too_short',
            )

    def get_help_text(self):
        """Return the Uzbek help text shown on password forms."""
        return "Parol 8 belgidan kam bo'lmasligi kerak."
