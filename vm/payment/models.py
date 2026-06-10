from django.conf import settings
from django.db import models
from cart.models import Cart
from user.models import phone_regex  # reuse same validator as User.phone


def _normalize_phone(value):
    """
    Normalize a phone string to the canonical '+998 XX XXX XX XX' format.
    Same logic as User.save() — kept here so Order has a single source of truth.
    Returns the input unchanged if it doesn't look normalizable; the
    RegexValidator on the field will reject it during full_clean().
    """
    if not value:
        return value
    digits = value.replace(' ', '').replace('+998', '')
    if len(digits) == 9 and digits.isdigit():
        return f"+998 {digits[:2]} {digits[2:5]} {digits[5:7]} {digits[7:9]}"
    return value


class Order(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        PAYING = 'paying', 'To\'lanmoqda'
        PAID = 'paid', 'To\'langan'
        PROCESSING = 'processing', 'Jarayonda'
        ON_THE_WAY = 'on_the_way', 'Yo\'lda'
        DONE = 'done', 'Bajarildi'
        CANCELLED = 'cancelled', 'Bekor qilindi'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders')
    cart = models.OneToOneField(Cart, on_delete=models.CASCADE, related_name='order')
    phone = models.CharField(
        validators=[phone_regex],
        max_length=17,
    )
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    address = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    total_price = models.DecimalField(max_digits=15, decimal_places=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order {self.id} | {self.user.username} | {self.get_status_display()}"

    def save(self, *args, **kwargs):
        # Normalize phone the same way User does, so the stored value is canonical.
        self.phone = _normalize_phone(self.phone)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']


