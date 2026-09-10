"""Order model: a checked-out cart with delivery details and payment status,
plus the delivery options and Uzpost pickup points an order can point at.

Translation follows the project convention: Uzbek lives in the base field,
Russian and English in ``_ru`` / ``_en`` (plan §7, §17 #8).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from cart.models import Cart
from user.models import phone_regex, normalize_uz_phone  # reuse same validator + normalizer as User.phone


class DeliveryOption(models.Model):
    """A shipping tier the customer picks at checkout.

    Rows are seeded, not hardcoded, so the owner can change a price or switch a
    tier off from the admin without a deploy. ``free_from_items`` is 0 today —
    there is no free-delivery threshold — but the field exists so a promotion
    can be turned on later the same way (plan §7).
    """
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120, help_text="Oʻzbekcha — asosiy matn")
    name_ru = models.CharField(max_length=120, blank=True, default='')
    name_en = models.CharField(max_length=120, blank=True, default='')
    note = models.TextField(blank=True, default='', help_text="Oʻzbekcha — asosiy matn")
    note_ru = models.TextField(blank=True, default='')
    note_en = models.TextField(blank=True, default='')
    price = models.DecimalField(max_digits=15, decimal_places=0)
    free_from_items = models.PositiveSmallIntegerField(default=0)
    requires_pickup_point = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"{self.name} ({self.price})"

    def price_for_items(self, item_count):
        """Return the fee for a cart of ``item_count`` items — 0 once free kicks in."""
        if self.free_from_items and item_count >= self.free_from_items:
            return 0
        return self.price

    class Meta:
        ordering = ['sort_order', 'code']


class PickupPoint(models.Model):
    """An Uzbekiston pochtasi branch the customer can collect an order from.

    Our own dataset rather than a live API: the branch list changes rarely, and
    a seeded table keeps checkout working when the network doesn't. Refreshed by
    the ``seed_pickup_points`` management command.
    """
    code = models.CharField(max_length=20, unique=True)   # postal index, e.g. "100007"
    name = models.CharField(max_length=160, help_text="Oʻzbekcha — asosiy matn")
    name_ru = models.CharField(max_length=160, blank=True, default='')
    name_en = models.CharField(max_length=160, blank=True, default='')
    region = models.CharField(max_length=80, db_index=True)
    district = models.CharField(max_length=80, db_index=True)
    address = models.CharField(max_length=255, help_text="Oʻzbekcha — asosiy matn")
    address_ru = models.CharField(max_length=255, blank=True, default='')
    address_en = models.CharField(max_length=255, blank=True, default='')
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    working_hours = models.CharField(max_length=120, blank=True, default='')
    phone = models.CharField(max_length=30, blank=True, default='')
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"{self.code} — {self.name}"

    def snapshot(self):
        """Freeze the branch as the text stored on an order (see Order.pickup_snapshot)."""
        return f"{self.code} — {self.name}\n{self.region}, {self.district}\n{self.address}"

    class Meta:
        ordering = ['region', 'district', 'name']


class Order(models.Model):
    """A placed order, created from a cart at checkout.

    Linked one-to-one to the (now closed) Cart it was made from. ``address`` is a
    TextField so it can hold real multi-line addresses, and ``total_price`` is in
    whole so'm — the value Click validates the payment amount against.

    ``delivery_price`` and ``pickup_snapshot`` are frozen at checkout for the
    same reason ``CartItem.price_stat`` is: if a fee changes or a branch is
    renamed a year later, the order still records what was actually agreed.
    """
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
    # What the customer and the courier quote. The integer PK is never shown
    # again: it leaks how many orders the shop has taken.
    order_no = models.CharField(max_length=20, unique=True, blank=True, db_index=True)
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

    # Delivery. Both FKs are PROTECT: an option or branch referenced by a real
    # order must not vanish from under it.
    delivery_option = models.ForeignKey(DeliveryOption, on_delete=models.PROTECT,
                                        null=True, blank=True, related_name='orders')
    delivery_price = models.DecimalField(max_digits=15, decimal_places=0, default=0)
    pickup_point = models.ForeignKey(PickupPoint, on_delete=models.PROTECT,
                                     null=True, blank=True, related_name='orders')
    pickup_snapshot = models.TextField(blank=True, default='')
    # Door delivery only — where the courier is actually going.
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    def __str__(self):
        return f"Order {self.order_no or self.id} | {self.user.username} | {self.get_status_display()}"

    @classmethod
    def next_order_no(cls, when=None):
        """Return the next free number for ``when`` (today by default).

        Format ``GX-YYMMDD-NNNN``, sequential within the day. Uniqueness is
        ultimately enforced by the column's unique constraint; the caller
        retries on collision (see ``payment.services``).
        """
        day = when or timezone.localdate()
        prefix = f"GX-{day:%y%m%d}-"
        last = (cls.objects.filter(order_no__startswith=prefix)
                .order_by('-order_no')
                .values_list('order_no', flat=True)
                .first())
        seq = int(last.rsplit('-', 1)[1]) + 1 if last else 1
        return f"{prefix}{seq:04d}"

    def clean(self):
        """Delivery option and pickup point have to agree (plan §7)."""
        super().clean()
        if self.delivery_option_id and self.delivery_option.requires_pickup_point and not self.pickup_point_id:
            raise ValidationError({'pickup_point': _('Bu yetkazib berish turi uchun pochta boʻlimi tanlanishi shart.')})
        if self.delivery_option_id and not self.delivery_option.requires_pickup_point and self.pickup_point_id:
            raise ValidationError({'pickup_point': _('Eshikkacha yetkazib berishda pochta boʻlimi tanlanmaydi.')})

    def save(self, *args, **kwargs):
        """Normalise the phone and assign an order number on first save."""
        self.phone = normalize_uz_phone(self.phone)
        if not self.order_no:
            self.order_no = self.next_order_no()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']
