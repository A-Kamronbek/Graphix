"""Order model: a checked-out cart with delivery details and payment status,
plus the delivery options and Uzpost pickup points an order can point at,
and the promo codes an order can be placed with.

Translation follows the project convention: Uzbek lives in the base field,
Russian and English in ``_ru`` / ``_en`` (plan §7, §17 #8).
"""
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _, ngettext
from cart.models import Cart
from user.models import phone_regex, normalize_uz_phone  # reuse same validator + normalizer as User.phone

#: The longest recipient name an order keeps: room for an Uzbek full name with
#: a patronymic. The checkout refuses anything longer with a sentence rather
#: than cutting the name that goes on the parcel (§17 #131, #154).
RECIPIENT_NAME_MAX = 120


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
    #: How long delivery usually takes, in days - shown beside the price on
    #: the product page, at checkout and on the delivery page. On the row,
    #: like the price, so the owner changes it in the panel rather than in
    #: a deploy. ``days_max`` of 0 means no time is stated (§17 #301).
    days_min = models.PositiveSmallIntegerField(default=0)
    days_max = models.PositiveSmallIntegerField(default=0)
    # Region + district + a typed postal index, not a street address. Named for
    # what the customer supplies rather than for a table, because there is no
    # branch table any more (§17 #84).
    requires_branch = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"{self.name} ({self.price})"

    def price_for_items(self, item_count):
        """Return the fee for a cart of ``item_count`` items — 0 once free kicks in."""
        if self.free_from_items and item_count >= self.free_from_items:
            return 0
        return self.price

    @property
    def days_label(self):
        """How long it usually takes - "1–2 kun" - in the reader's language, or ''.

        Counted on the upper figure, which is the number a range agrees with
        in Russian: 1–2 дня, 1–6 дней. The range is joined so it never breaks
        at the dash, like every period on the legal pages (§17 #204).
        """
        if not self.days_max:
            return ''
        from core.templatetags.legal_tags import legal_range
        low = self.days_min if 0 < self.days_min < self.days_max else self.days_max
        span = str(low) if low == self.days_max else legal_range(low, self.days_max)
        return ngettext('%(span)s kun', '%(span)s kun', self.days_max) % {'span': span}

    class Meta:
        ordering = ['sort_order', 'code']


class PaymentOption(models.Model):
    """A way to pay, as a row rather than a constant.

    The shop takes Click. Cash exists in the model and in this table but ships
    **switched off**, and the owner turns it on from the admin if he ever wants
    it — the same reasoning as :class:`DeliveryOption` (§17 #13): a commercial
    decision should not need a deploy.

    An inactive option is not rendered at all rather than rendered greyed out.
    A disabled control on a checkout page reads as "coming soon" and invites the
    customer to wait for something that may never arrive; an option that is off
    is simply absent, and the checkout refuses it server-side either way.
    """
    code = models.CharField(max_length=20, unique=True)   # matches Order.PaymentMethod
    name = models.CharField(max_length=120, help_text="Oʻzbekcha — asosiy matn")
    name_ru = models.CharField(max_length=120, blank=True, default='')
    name_en = models.CharField(max_length=120, blank=True, default='')
    note = models.CharField(max_length=200, blank=True, default='',
                            help_text="Oʻzbekcha — asosiy matn")
    note_ru = models.CharField(max_length=200, blank=True, default='')
    note_en = models.CharField(max_length=200, blank=True, default='')
    is_active = models.BooleanField(default=False, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"{self.name} ({'yoqilgan' if self.is_active else 'oʻchirilgan'})"

    class Meta:
        ordering = ['sort_order', 'code']


class Region(models.Model):
    """A viloyat, Qoraqalpogʻiston, or Toshkent shahri.

    Fourteen rows plus one escape. They replace the branch table (§17 #84):
    there is no public Uzpost branch list to own, but the administrative
    divisions *are* published, and the customer supplies the one thing we
    cannot — the postal index of their own branch.

    ``postal_prefix`` is what makes a typed index safe. Uzbek indexes encode the
    province in their leading digits, and that is two digits for most regions
    and three for Toshkent shahri, so the check is ``startswith`` and never a
    fixed slice. The escape row has no prefix, which is what switches the check
    off for an address the classifier does not cover while the six-digit format
    check still applies (§17 #86).
    """
    code = models.CharField(max_length=4, unique=True)      # SOATO code
    name = models.CharField(max_length=80, help_text="Oʻzbekcha — asosiy matn")
    name_ru = models.CharField(max_length=80, blank=True, default='')
    name_en = models.CharField(max_length=80, blank=True, default='')
    postal_prefix = models.CharField(max_length=3, blank=True, default='', db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return self.name

    def index_matches(self, postal_index):
        """Does ``postal_index`` belong to this region?

        A region with no prefix accepts any index — that is the escape, and it
        is deliberate: we do not know where an address we could not classify
        sits, so the only honest answer is not to guess.
        """
        if not self.postal_prefix:
            return True
        return str(postal_index).startswith(self.postal_prefix)

    class Meta:
        ordering = ['sort_order', 'name']


class District(models.Model):
    """A tuman, a city of regional subordination, or the escape.

    Both are in one table because the customer is choosing one thing — where
    they are — and someone in Angren is looking for a city, not scanning an
    alphabetical mix of districts. ``kind`` is what lets the drawer group them
    under separate headings rather than flatten them (§17 #87).
    """
    class Kind(models.TextChoices):
        DISTRICT = 'district', _('Tuman')
        CITY = 'city', _('Shahar')
        # The escape. It is a row rather than a UI-only option because an order
        # points at a district through a PROTECT foreign key, and because
        # `location_snapshot` has to be able to freeze what was chosen.
        OTHER = 'other', _('Boshqa')

    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name='districts')
    code = models.CharField(max_length=8, unique=True)      # SOATO code
    name = models.CharField(max_length=80, help_text="Oʻzbekcha — asosiy matn")
    name_ru = models.CharField(max_length=80, blank=True, default='')
    name_en = models.CharField(max_length=80, blank=True, default='')
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.DISTRICT)
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"{self.region.name} — {self.name}"

    class Meta:
        ordering = ['region', 'sort_order', 'name']
        unique_together = ('region', 'name')


def location_text(region=None, district=None, postal_index='', location_note='',
                  address=''):
    """Render a destination as the text an order freezes in ``location_snapshot``.

    A free function rather than a method because the checkout service needs it
    *before* the Order exists — and freezing has to happen at that moment, not
    later. The rows are read once, here, and never consulted again for this
    order: that is the whole point, and it is why a district renamed or
    deactivated a year from now cannot rewrite where a parcel was actually sent
    (§17 #14).

    Both methods now carry a region and a district (§17 #106), so the text reads
    the same way for either — province, district, then whichever of the index or
    the street address the method uses. The address is collapsed onto one line
    because this is a single line of frozen text, not the address field itself.
    """
    parts = []
    if region is not None:
        parts.append(region.name)
        if district is not None:
            parts.append(location_note or district.name)
        elif location_note:
            parts.append(location_note)
    if postal_index:
        parts.append(postal_index)
    street = ' '.join((address or '').split())
    if street:
        parts.append(street)
    return ' · '.join(parts)


class PromoCode(models.Model):
    """A code a customer types at checkout to pay less.

    One of five kinds, chosen when the code is made: a sum or a share off one
    item, a sum or a share off the whole order, or free delivery. One code
    discounts one item or one order, never more (§17 #314 to #317). The rules
    themselves, when a code may be used and what it takes off, are in
    ``payment/promos.py``; this is the row they read.

    ``used_count`` is how many paid orders hold the code. It moves when an
    order is paid for or a paid one is cancelled, never when an order is only
    placed: an unpaid order holds no use, as it holds no stock.

    A code an order points at is never deleted, only switched off: the order
    keeps a ``PROTECT`` key to it, so the owner can still read what a code
    was a year after it ended.
    """
    class Kind(models.TextChoices):
        PRODUCT_SUM = 'product_sum', _('Bitta mahsulotdan summa')
        PRODUCT_PERCENT = 'product_percent', _('Bitta mahsulotdan foiz')
        ORDER_SUM = 'order_sum', _('Buyurtmadan summa')
        ORDER_PERCENT = 'order_percent', _('Buyurtmadan foiz')
        FREE_DELIVERY = 'free_delivery', _('Bepul yetkazib berish')

    #: The kinds that discount one item, and so need to know which products.
    PRODUCT_KINDS = (Kind.PRODUCT_SUM, Kind.PRODUCT_PERCENT)
    #: The kinds whose ``value`` is a share, 1 to 100, and not a sum.
    PERCENT_KINDS = (Kind.PRODUCT_PERCENT, Kind.ORDER_PERCENT)

    #: What a code is written in: Latin capitals and digits, three to
    #: twenty-four of them. No spaces and no look-alike letters from another
    #: alphabet, so a code read out over the phone has one spelling.
    CODE_RE = re.compile(r'^[A-Z0-9]{3,24}$')

    code = models.CharField(max_length=24, unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    # So'm for the two sum kinds, 1 to 100 for the two percentages, and
    # nothing for free delivery, which takes off whatever the fee is.
    value = models.DecimalField(max_digits=15, decimal_places=0, default=0)
    # The products a product code may be used on. Empty for the other kinds.
    products = models.ManyToManyField('product.Product', blank=True,
                                      related_name='promo_codes')
    is_active = models.BooleanField(default=True, db_index=True)

    # Every limit is optional: blank dates mean no start or no end, a blank
    # ``max_uses`` means any number, and a zero minimum means none.
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    min_subtotal = models.DecimalField(max_digits=15, decimal_places=0, default=0)
    once_per_customer = models.BooleanField(default=True)

    used_count = models.PositiveIntegerField(default=0)
    # For the owner alone: who the code was made for, or why.
    note = models.CharField(max_length=200, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code

    @property
    def is_percent(self):
        """Whether ``value`` is a share of a price and not a sum of money."""
        return self.kind in self.PERCENT_KINDS

    @property
    def is_for_products(self):
        """Whether this code discounts one item, and so names its products."""
        return self.kind in self.PRODUCT_KINDS

    def clean(self):
        """A code has one spelling and a value that fits its kind."""
        super().clean()
        errors = {}
        self.code = re.sub(r'\s+', '', self.code or '').upper()
        if not self.CODE_RE.match(self.code):
            errors['code'] = _('Promokod 3 tadan 24 tagacha lotin harfi va '
                               'raqamdan iborat boʻlishi kerak.')
        value = self.value or 0
        if self.kind == self.Kind.FREE_DELIVERY:
            self.value = 0
        elif self.is_percent and not 1 <= value <= 100:
            errors['value'] = _('Foiz 1 dan 100 gacha boʻlishi kerak.')
        elif not self.is_percent and value < 1:
            errors['value'] = _('Summani kiriting.')
        if self.starts_at and self.ends_at and self.ends_at < self.starts_at:
            errors['ends_at'] = _('Tugash sanasi boshlanish sanasidan oldin '
                                  'boʻlishi mumkin emas.')
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Keep the code in the one spelling it is matched in."""
        self.code = re.sub(r'\s+', '', self.code or '').upper()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at', '-id']


class Order(models.Model):
    """A placed order, created from a cart at checkout.

    Linked one-to-one to the (now closed) Cart it was made from. ``address`` is a
    TextField so it can hold real multi-line addresses, and ``total_price`` is in
    whole so'm — the value Click validates the payment amount against.

    ``delivery_price`` and ``location_snapshot`` are frozen at checkout for the
    same reason ``CartItem.price_stat`` is: if a fee changes or a district is
    renamed a year later, the order still records what was actually agreed.
    """
    # Translated, and spelt with U+02BB. These labels are on the customer's own
    # orders page and in every status badge on the site, and they were plain
    # Uzbek strings with ASCII apostrophes — so a Russian customer was told
    # "To'lanmoqda" in the middle of an otherwise Russian page, and the
    # apostrophe was the wrong character in Uzbek as well. They predate §4's
    # no-hardcoded-strings rule, which is exactly why nothing caught them.
    class Status(models.TextChoices):
        PAYING = 'paying', _('Toʻlanmoqda')
        PAID = 'paid', _('Toʻlangan')
        PROCESSING = 'processing', _('Jarayonda')
        # The word the dashboard tile uses (§17 #178, #189): the tile counts
        # these orders, so the two must say the same thing. The stored value
        # does not change.
        ON_THE_WAY = 'on_the_way', _('Yetkazilmoqda')
        DONE = 'done', _('Bajarildi')
        CANCELLED = 'cancelled', _('Bekor qilindi')

    class PaymentMethod(models.TextChoices):
        # Brand names; the same in all three languages, so no gettext.
        CLICK = 'click', 'Click'
        PAYME = 'payme', 'Payme'
        OCTO = 'octo', 'Octo'
        CASH = 'cash', _('Naqd pul')

    # PROTECT, not CASCADE: an order is a sales record the Tax Code keeps and
    # the privacy policy promises to keep after an account is closed, so
    # deleting the account must not take it along. With orders on file, the
    # admin refuses the delete and says why; closing such an account means
    # clearing its name and phone and keeping the orders (§18 #33, §17 #219).
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders')
    cart = models.OneToOneField(Cart, on_delete=models.CASCADE, related_name='order')
    # What the customer and the courier quote. The integer PK is never shown
    # again: it leaks how many orders the shop has taken.
    order_no = models.CharField(max_length=20, unique=True, blank=True, db_index=True)
    phone = models.CharField(
        validators=[phone_regex],
        max_length=17,
    )
    # Who the parcel is addressed to, as typed at checkout. Often not the
    # account holder - a gift, a parent ordering for a child - and a post
    # office hands a parcel to the name written on it. The checkout asked for
    # this from the start and dropped it; blank only on orders from before.
    recipient_name = models.CharField(max_length=RECIPIENT_NAME_MAX, blank=True, default='')
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PAYING, db_index=True)
    address = models.TextField()
    notes = models.TextField(blank=True, default='')
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CLICK,
    )
    # Indexed: orders are listed newest first everywhere they are listed - the
    # customer's account, the panel's list, the dashboard's day and month
    # figures - and the panel filters them by date (§9 Phase 9 item 8).
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    total_price = models.DecimalField(max_digits=15, decimal_places=0)
    updated_at = models.DateTimeField(auto_now=True)

    # Delivery. Every FK here is PROTECT: something a real order points at must
    # not vanish from under it.
    delivery_option = models.ForeignKey(DeliveryOption, on_delete=models.PROTECT,
                                        null=True, blank=True, related_name='orders')
    delivery_price = models.DecimalField(max_digits=15, decimal_places=0, default=0)

    # Branch delivery: where the parcel is going, as the customer chose it.
    region = models.ForeignKey(Region, on_delete=models.PROTECT,
                               null=True, blank=True, related_name='orders')
    district = models.ForeignKey(District, on_delete=models.PROTECT,
                                 null=True, blank=True, related_name='orders')
    postal_index = models.CharField(max_length=6, blank=True, default='', db_index=True)
    # Free text for the Boshqa escape — the district the classifier does not
    # know about, in the customer's own words.
    location_note = models.CharField(max_length=160, blank=True, default='')

    # Frozen at checkout, as text, whichever method was used. Same reason
    # CartItem.price_stat exists: a district renamed or deactivated a year later
    # must not be able to rewrite where a parcel was actually sent.
    location_snapshot = models.TextField(blank=True, default='')

    # Home delivery only — where the courier is actually going.
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    # Whether those coordinates are the customer's own dropped pin or absent
    # because they typed the address instead. One column, and it answers the
    # question the courier actually has (§17 #88).
    address_source = models.CharField(max_length=10, blank=True, default='',
                                      choices=[('map', _('Xaritadan')),
                                               ('manual', _('Qoʻlda kiritilgan'))])

    # Which wording the customer accepted by placing this order;
    # ``created_at`` is when. The checkout says in so many words that pressing
    # the button accepts both documents, and an order is where a dispute
    # starts, so the pair is frozen onto the row for the same reason
    # ``location_snapshot`` is: amending a document a year later must not be
    # able to rewrite what was agreed (§17 #272). Blank on orders placed
    # before this was recorded.
    terms_version = models.CharField(max_length=10, blank=True, default='')
    privacy_version = models.CharField(max_length=10, blank=True, default='')

    # The promo code the order was placed with, frozen like the delivery
    # price: the code as it was typed, what it took off in so'm, and for a
    # code that discounts one item, the product it was taken from. A code
    # edited or switched off later cannot rewrite an order. ``total_price``
    # is goods + delivery - discount, and stays the figure a gateway is asked
    # for (§17 #310).
    promo = models.ForeignKey(PromoCode, on_delete=models.PROTECT,
                              null=True, blank=True, related_name='orders')
    promo_code = models.CharField(max_length=24, blank=True, default='')
    discount = models.DecimalField(max_digits=15, decimal_places=0, default=0)
    discount_product = models.ForeignKey('product.Product', on_delete=models.PROTECT,
                                         null=True, blank=True, related_name='+')

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
        """The delivery method and the address fields have to agree.

        This is the point of the redesign (§17 #86), and it lives here as well
        as in the checkout view because the view will not always be the only
        thing that builds an order.

        Four checks, in order of what they cost the customer:

        * **both** methods must carry a region and a district. A courier needs
          the province and the district as much as the post office does, and a
          customer who picks them from a drawer cannot misspell them — which is
          why the home form stopped asking for them inside a free-text address
          (§17 #106);
        * the district must belong to the chosen region;
        * for a branch order the index must be six digits, whatever region it is
          for, because a five-digit index is wrong everywhere; a home order must
          not carry one at all;
        * the index's leading digits must match the chosen region's prefix.
          That is the one error worth catching automatically: it is the typo
          that sends a real parcel to another province, and the customer finds
          out at the form rather than three weeks later.
        """
        super().clean()
        if not self.delivery_option_id:
            return

        branch = self.delivery_option.requires_branch
        errors = {}

        if not self.region_id:
            errors['region'] = _('Viloyatni tanlang.')
        if not self.district_id:
            errors['district'] = _('Tuman yoki shaharni tanlang.')
        elif self.region_id and self.district.region_id != self.region_id:
            errors['district'] = _('Tanlangan tuman bu viloyatga tegishli emas.')

        if branch:
            if not self.postal_index:
                errors['postal_index'] = _('Pochta indeksini kiriting.')
            elif not (self.postal_index.isdigit() and len(self.postal_index) == 6):
                errors['postal_index'] = _('Pochta indeksi 6 ta raqamdan iborat boʻlishi kerak.')
            elif self.region_id and not self.region.index_matches(self.postal_index):
                errors['postal_index'] = _(
                    'Bu indeks tanlangan viloyatga toʻgʻri kelmadi. '
                    'Indeksni yoki viloyatni tekshiring.'
                )
        else:
            if self.postal_index:
                errors['postal_index'] = _(
                    'Eshikkacha yetkazib berishda pochta boʻlimi tanlanmaydi.'
                )
            if not (self.address or '').strip():
                # The pin adds precision on top of an address; it never replaces
                # one, because a courier delivers to an address (§17 #91).
                errors['address'] = _('Manzilni kiriting.')

        if errors:
            raise ValidationError(errors)

    @property
    def amount(self):
        """What this order costs, under the name tolov looks for.

        Not a column and not a second source of truth — `total_price` is the
        number, in whole so'm, and this is an alias.

        It exists because tolov checks a payment callback's amount with
        ``getattr(account, "amount", 0)``, hardcoded, where click-pkg read the
        field name from a setting. Without this the check compares a real
        payment against **zero** and raises `InvalidAmount`, which answers
        Click with `error: -2` and means no order can ever be paid for
        (§17 #262). A property rather than a rename because `total_price` is
        what the rest of the shop, the panel and the Telegram message all say.
        """
        return self.total_price

    def location_text(self):
        """This order's frozen destination text. See :func:`location_text`."""
        return location_text(self.region if self.region_id else None,
                             self.district if self.district_id else None,
                             self.postal_index, self.location_note, self.address)

    def save(self, *args, **kwargs):
        """Normalise the phone and assign an order number on first save."""
        self.phone = normalize_uz_phone(self.phone)
        if not self.order_no:
            self.order_no = self.next_order_no()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']


#: The statuses of an order the shop was paid for and kept: a sale. Stock is
#: held by these orders and by no others, the dashboard counts these and
#: nothing else as takings, and a promo code's use belongs to one of them.
#: `paying` is out because nobody has paid; `cancelled` is out whether or not
#: money moved first (§17 #57, #297).
SOLD = (Order.Status.PAID, Order.Status.PROCESSING,
        Order.Status.ON_THE_WAY, Order.Status.DONE)
