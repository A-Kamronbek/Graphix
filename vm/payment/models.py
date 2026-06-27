from django.conf import settings
from django.db import models
from cart.models import Cart
from user.models import phone_regex, normalize_uz_phone  # reuse same validator + normalizer as User.phone


class Order(models.Model):
    class Status(models.TextChoices):
        PAYING = 'paying', 'To\'lanmoqda'
        PAID = 'paid', 'To\'langan'
        PROCESSING = 'processing', 'Jarayonda'
        ON_THE_WAY = 'on_the_way', 'Yo\'lda'
        DONE = 'done', 'Bajarildi'
        CANCELLED = 'cancelled', 'Bekor qilindi'

    class PaymentMethod(models.TextChoices):
        CLICK = 'click', 'Click'
        CASH = 'cash', 'Naqd pul'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders')
    cart = models.OneToOneField(Cart, on_delete=models.CASCADE, related_name='order')
    phone = models.CharField(
        validators=[phone_regex],
        max_length=17,
    )
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PAYING, db_index=True)
    address = models.TextField()
    notes = models.TextField(blank=True, default='')
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CLICK,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    total_price = models.DecimalField(max_digits=15, decimal_places=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order {self.id} | {self.user.username} | {self.get_status_display()}"

    def save(self, *args, **kwargs):
        # Normalize phone the same way User does, so the stored value is canonical.
        self.phone = normalize_uz_phone(self.phone)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']


