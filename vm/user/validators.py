"""Password validators with translated messages."""
from django.contrib.auth.password_validation import MinimumLengthValidator
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class CustomMinimumLengthValidator(MinimumLengthValidator):
    """Minimum-length validator that reports the error in the active language.

    Behaves exactly like Django's :class:`MinimumLengthValidator` but replaces
    the default English messages with translated ones.
    """

    def validate(self, password, user=None):
        """Raise :class:`ValidationError` if ``password`` is shorter than ``min_length``."""
        if len(password) < self.min_length:
            raise ValidationError(
                _("Parol 8 belgidan kam boʻlmasligi kerak."),
                code='password_too_short',
            )

    def get_help_text(self):
        """Return the help text shown on password forms."""
        return _("Parol 8 belgidan kam boʻlmasligi kerak.")
