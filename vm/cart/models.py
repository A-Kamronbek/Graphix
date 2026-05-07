from django.conf import settings
from django.db import models
from django.db.models import F, Sum
from product.models import Variant


class Cart(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="carts")
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def price_calc(self):
        return self.cart_items.aggregate(
            total=Sum(F('price_stat') * F('quantity'))
        )['total'] or 0

    def __str__(self):
        return f"Cart {self.id}. {self.user.username}"

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="cart_items")
    variant = models.ForeignKey(Variant, on_delete=models.PROTECT, related_name="cart_items")
    quantity = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    price_stat = models.DecimalField(max_digits=15, decimal_places=0)

    def __str__(self):
        return f"cart {self.cart.id} | {self.quantity} x {self.variant.product.name}"

    class Meta:
        unique_together = ('cart', 'variant')
        indexes = [models.Index(fields=['cart']),]



