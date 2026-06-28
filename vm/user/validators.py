"""Custom auth password validators (referenced from settings.AUTH_PASSWORD_VALIDATORS)."""
from django.contrib.auth.password_validation import MinimumLengthValidator
from django.core.exceptions import ValidationError


class CustomMinimumLengthValidator(MinimumLengthValidator):
    """Minimum-length validator with an Uzbek message."""

    def validate(self, password, user=None):
        if len(password) < self.min_length:
            raise ValidationError(
                "Parol 8 belgidan kam bo'lmasligi kerak.",
                code='password_too_short',
            )

    def get_help_text(self):
        return "Parol 8 belgidan kam bo'lmasligi kerak."
