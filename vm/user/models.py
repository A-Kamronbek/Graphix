from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


phone_regex = RegexValidator(
    regex=r'^\+998 ?\d{2} ?\d{3} ?\d{2} ?\d{2}$',
    message="format: +998 XX XXX XX XX"
)


class User(AbstractUser):
    phone = models.CharField(
        validators=[phone_regex],
        max_length=17,
        unique=True,
    )

    def save(self, *args, **kwargs):
        if self.phone:
            # Strip all spaces, then reformat as +998 XX XXX XX XX
            digits = self.phone.replace(' ', '').replace('+998', '')
            if len(digits) == 9:
                self.phone = f"+998 {digits[:2]} {digits[2:5]} {digits[5:7]} {digits[7:9]}"
        super().save(*args, **kwargs)
