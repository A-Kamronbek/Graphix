"""Cart models: one open cart per user (or per guest session), with
price-snapshotted line items."""
from django.conf import settings
from django.db import models
from django.db.models import F, Sum, Q
from product.models import Variant


class Cart(models.Model):
    """A cart, owned either by a user or — before login — by a session.

    Two partial unique constraints allow one open (``status=True``) cart per
    signed-in user and one per anonymous session; checked-out carts are kept on
    record with ``status=False``. A guest cart is merged into the user's open
    cart on login, or simply claimed by setting ``user`` if there is none.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             null=True, blank=True, related_name="carts")
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def price_calc(self):
        """Return the cart total (sum of price_stat * quantity), or 0 if empty."""
        return self.cart_items.aggregate(
            total=Sum(F('price_stat') * F('quantity'))
        )['total'] or 0

    def __str__(self):
        owner = self.user.username if self.user_id else f"guest {self.session_key or '?'}"
        return f"Cart {self.id}. {owner}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=Q(status=True) & Q(user__isnull=False),
                name='unique_open_cart_per_user',
            ),
            models.UniqueConstraint(
                fields=['session_key'],
                condition=Q(status=True) & Q(user__isnull=True),
                name='unique_open_cart_per_session',
            ),
        ]

class CartItem(models.Model):
    """A line in a cart.

    ``price_stat`` snapshots the variant price at the moment it was added, so a
    later catalogue price change can't silently alter an existing cart or order.
    """
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
