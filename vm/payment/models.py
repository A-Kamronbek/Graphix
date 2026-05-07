from django.conf import settings
from django.db import models
from cart.models import Cart

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
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    address = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    total_price = models.DecimalField(max_digits=15, decimal_places=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order {self.id} | {self.user.username} | {self.get_status_display()}"

    class Meta:
        ordering = ['-created_at']
