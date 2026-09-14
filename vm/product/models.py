"""Catalog models: categories, products, images, sizes, colours, and variants,
plus tags, size charts, likes and reviews.

Translation: Uzbek lives in the base field (``name``), Russian and English in
``name_ru`` / ``name_en``. Reading goes through ``core.i18n.tfield`` or the
``|t`` template filter, which fall back to the base field when a translation is
blank. Keeping Uzbek in the base column means every existing row stays valid
with no backfill (plan §7, §17 #8).
"""
from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from colorfield.fields import ColorField


def unique_slug(instance, source):
    """Return a URL slug for ``instance`` derived from ``source``, unique in its table.

    The Uzbek modifier letters (oʻ, gʻ) are non-ASCII, so ``slugify`` drops them —
    "Oʻzbek koʻylak" becomes "ozbek-koylak", which is the URL we want. A source
    that slugifies to nothing (all Cyrillic, or only punctuation) falls back to the
    model name, and collisions get a -2, -3 … suffix.

    The data migration that backfilled existing rows repeats this logic rather than
    importing it: a migration must keep working even when the model changes.
    """
    model = instance.__class__
    base = (slugify(source) or model._meta.model_name)[:255]
    slug, n = base, 2
    while model.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
        suffix = f"-{n}"
        slug = f"{base[:255 - len(suffix)]}{suffix}"
        n += 1
    return slug


class Tag(models.Model):
    """A style, theme or collection label.

    Tags — not categories — are what the Phase 13 recommender reads: every
    product is a t-shirt, so ``Category`` carries almost no signal (§17 #26).
    """
    class Kind(models.TextChoices):
        STYLE = 'style', _('Uslub')
        THEME = 'theme', _('Mavzu')
        COLLECTION = 'collection', _('Kolleksiya')

    slug = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=60, help_text="Oʻzbekcha — asosiy matn")
    name_ru = models.CharField(max_length=60, blank=True, default='')
    name_en = models.CharField(max_length=60, blank=True, default='')
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.THEME, db_index=True)

    def __str__(self):
        return f"{self.get_kind_display()}: {self.name}"

    class Meta:
        ordering = ['kind', 'slug']


class SizeChart(models.Model):
    """A sizing guide, image first.

    The uploaded chart is the primary content and the only thing the owner has
    to supply; :class:`SizeChartRow` is optional structured data that, when
    present, renders as a table *in addition to* the image — better for screen
    readers and for search engines (§17 #15).

    ``fit`` is what lets a chart find its own products. A garment's
    measurements are a property of its cut, and the catalogue has exactly two
    cuts (§17 #70), so tagging the chart with one means the owner never has to
    remember to attach it: ``Product.resolve_size_chart`` falls back to it.
    Leave it blank for a one-off chart that belongs to a specific product.
    """
    name = models.CharField(max_length=120)
    image = models.ImageField(upload_to='size-charts/', null=True, blank=True)
    note = models.TextField(blank=True, default='', help_text="Oʻzbekcha — asosiy matn")
    note_ru = models.TextField(blank=True, default='')
    note_en = models.TextField(blank=True, default='')
    fit = models.CharField(max_length=20, blank=True, default='', db_index=True,
                           help_text="Shu qolipdagi mahsulotlar uchun standart jadval.")

    def __str__(self):
        return self.name


class Category(models.Model):
    """A product category (e.g. shirts, trousers)."""
    name = models.CharField(max_length=255, help_text="Oʻzbekcha — asosiy matn")
    name_ru = models.CharField(max_length=255, blank=True, default='')
    name_en = models.CharField(max_length=255, blank=True, default='')
    slug = models.SlugField(max_length=255, unique=True)
    # Default chart for every product in the category; a product may override it.
    size_chart = models.ForeignKey(SizeChart, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='categories')

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Derive the slug from the Uzbek name when none was supplied."""
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = 'categories'


class Product(models.Model):
    """A catalog product; its sizes, colours, and prices live on related Variants."""

    class PrintMethod(models.TextChoices):
        DTF = 'dtf', 'DTF'
        DTG = 'dtg', 'DTG'
        SILKSCREEN = 'silkscreen', _('Trafaret')
        EMBROIDERY = 'embroidery', _('Naqsh')

    class Fit(models.TextChoices):
        # Two fits only, confirmed by the owner. `boxy` shipped in Phase 4 from
        # the tag examples in plan §7 and was never used; migration 0014 folds
        # any row carrying it into `oversize`, the nearer of the two. Adding a
        # third later is a migration, so it stays a decision, not a default.
        REGULAR = 'regular', _('Oddiy')
        OVERSIZE = 'oversize', _('Oversize')

    name = models.CharField(max_length=255, help_text="Oʻzbekcha — asosiy matn")
    name_ru = models.CharField(max_length=255, blank=True, default='')
    name_en = models.CharField(max_length=255, blank=True, default='')
    slug = models.SlugField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(null=True, blank=True)
    description_ru = models.TextField(blank=True, default='')
    description_en = models.TextField(blank=True, default='')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    tags = models.ManyToManyField(Tag, blank=True, related_name='products')
    is_active = models.BooleanField(default=True)

    # Denormalised counters. Maintained with F() expressions inside a transaction,
    # never a Python-side read-modify-write, so concurrent likes can't lose one.
    likes_count = models.PositiveIntegerField(default=0, db_index=True)
    rating_avg = models.DecimalField(max_digits=2, decimal_places=1, default=0, db_index=True)
    review_count = models.PositiveIntegerField(default=0)

    size_chart = models.ForeignKey(SizeChart, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='products')

    # Spec strip — structured, so it can be filtered and rendered consistently
    # instead of being buried in prose in the description.
    gsm = models.PositiveSmallIntegerField(null=True, blank=True)
    material = models.CharField(max_length=60, blank=True, default='',
                                help_text="Oʻzbekcha — asosiy matn, masalan: 100% paxta")
    material_ru = models.CharField(max_length=60, blank=True, default='')
    material_en = models.CharField(max_length=60, blank=True, default='')
    print_method = models.CharField(max_length=20, choices=PrintMethod.choices, blank=True, default='')
    fit = models.CharField(max_length=20, choices=Fit.choices, blank=True, default='')

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Derive the slug from the Uzbek name when none was supplied.

        The slug is the product's permanent URL, so it is set once and then left
        alone: renaming a product must not silently break its links.
        """
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """This product's canonical page.

        Through ``reverse`` so it follows the URL conf, including the language
        prefix every page now carries (§17 #121).
        """
        from django.urls import reverse
        return reverse('item', kwargs={'slug': self.slug})

    def resolve_size_chart(self):
        """Return the chart to show, most specific first.

        Product's own → its category's → the standard chart for its fit → none.
        The fit fallback is what makes the seeded charts work without the owner
        linking anything: measurements follow the cut, and the catalogue has two
        cuts. A product with no fit set and no explicit chart still gets nothing,
        which is correct — a chart that might not match the garment is worse than
        no chart (§17 #95).
        """
        if self.size_chart_id:
            return self.size_chart
        if self.category_id and self.category.size_chart_id:
            return self.category.size_chart
        if self.fit:
            return SizeChart.objects.filter(fit=self.fit).first()
        return None


class ImageP(models.Model):
    """A product photo, displayed in ``order`` (lowest first)."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    picture = models.ImageField(upload_to="products/")
    order = models.PositiveSmallIntegerField()

    def __str__(self):
        return f"{self.id} | {self.product.name} | {self.order} | {self.picture.name.split('/')[-1]}"

    class Meta:
        ordering = ['order', 'id']


class Size(models.Model):
    """A selectable size value."""
    size = models.CharField(max_length=50)

    def __str__(self):
        return self.size


class Colour(models.Model):
    """A selectable colour, with an optional hex code for the swatch.

    Hidden from the storefront UI — every design ships in one colourway, so the
    picker is noise — but kept in the data model, because deleting it would be a
    destructive migration for no gain (§17 #23).
    """
    colour = models.CharField(max_length=100, help_text="Oʻzbekcha — asosiy matn")
    colour_ru = models.CharField(max_length=100, blank=True, default='')
    colour_en = models.CharField(max_length=100, blank=True, default='')
    hex_code = ColorField(null=True, blank=True)

    def __str__(self):
        return self.colour


#: The one colourway every design ships in. Kept as a row rather than removing the
#: column, because dropping Colour would be a destructive migration for no gain
#: (§17 #23), and the product page's variant picker still keys on a colour id.
DEFAULT_COLOUR_NAME = 'Standart'


def default_colour():
    """Return (creating if needed) the colour the admin assigns automatically.

    The storefront renders no colour picker, so the owner should never have to
    choose one. Every variant gets this row unless an existing variant already
    has a different colour, which is left alone.
    """
    colour, _ = Colour.objects.get_or_create(
        colour=DEFAULT_COLOUR_NAME,
        defaults={'colour_ru': 'Стандарт', 'colour_en': 'Standard'},
    )
    return colour


class Variant(models.Model):
    """A buyable variant (product + size + colour) with its own price and stock.

    ``unique_together`` keeps one row per (product, size, colour). Purchasable
    means ``available AND stock > 0``: ``available`` is the owner's switch,
    ``stock`` is the count, and both have to agree.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    size = models.ForeignKey(Size, on_delete=models.PROTECT)
    colour = models.ForeignKey(Colour, on_delete=models.PROTECT)
    price = models.DecimalField(max_digits=15, decimal_places=0)
    available = models.BooleanField(default=False)
    stock = models.PositiveIntegerField(default=0)

    def __str__(self):
        return  f"{self.product.name} | {self.colour.colour} | {self.size.size}"

    @property
    def is_purchasable(self):
        """Available *and* actually in stock."""
        return self.available and self.stock > 0

    class Meta:
        unique_together = ('product', 'size', 'colour')
        ordering = ['product', 'size']
        indexes = [models.Index(fields=['product', 'available'])]


class SizeChartRow(models.Model):
    """One measured row of a size chart. Optional — the chart image is the source."""
    chart = models.ForeignKey(SizeChart, on_delete=models.CASCADE, related_name='rows')
    size = models.ForeignKey(Size, on_delete=models.PROTECT)
    chest_cm = models.DecimalField(max_digits=4, decimal_places=1)
    length_cm = models.DecimalField(max_digits=4, decimal_places=1)
    shoulder_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    sleeve_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"{self.chart.name} · {self.size.size}"

    class Meta:
        ordering = ['order']
        unique_together = ('chart', 'size')


class ProductLike(models.Model):
    """One heart: it both saves the product privately and counts publicly.

    There is no separate favourite model — one action, the way every fashion
    store and social app works (§17 #3). ``Product.likes_count`` is the
    denormalised public number.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='likes')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} ♥ {self.product}"

    class Meta:
        unique_together = ('user', 'product')
        ordering = ['-created_at']


class Review(models.Model):
    """A verified-purchase review, invisible until a staff member approves it.

    ``order`` records *which* delivered order granted the right to review, so
    eligibility can be re-checked later. Photos are user-uploaded content on a
    public page, which is why nothing appears before moderation (§17 #25).
    """
    class Status(models.TextChoices):
        PENDING = 'pending', _('Kutilmoqda')
        APPROVED = 'approved', _('Tasdiqlangan')
        REJECTED = 'rejected', _('Rad etilgan')

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    # String reference: payment imports cart, cart imports product, so importing
    # payment here would close the loop. Django resolves this lazily.
    order = models.ForeignKey('payment.Order', on_delete=models.PROTECT, related_name='reviews')
    rating = models.PositiveSmallIntegerField(choices=[(i, str(i)) for i in range(1, 6)])
    text = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=Status.choices,
                              default=Status.PENDING, db_index=True)
    moderated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='moderated_reviews')
    moderated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product} · {self.rating}★ · {self.get_status_display()}"

    class Meta:
        unique_together = ('user', 'product')
        ordering = ['-created_at']
        constraints = [
            # `choices` is a form-and-admin convenience; it is not enforced by
            # anything that writes through the ORM. This column feeds
            # `Product.rating_avg`, which is a public number on a public page,
            # so a six-star row would quietly poison it with no way to notice.
            # The view validates the rating for the customer's benefit; this is
            # the guarantee.
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name='review_rating_between_1_and_5',
            ),
        ]


class ReviewImage(models.Model):
    """A photo attached to a review. Only visible once its review is approved."""
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='images')
    picture = models.ImageField(upload_to='reviews/')
    order = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"{self.review_id} · {self.picture.name.split('/')[-1]}"

    class Meta:
        ordering = ['order', 'id']
