"""Catalog models: categories, products, images, sizes, colours, and variants,
plus tags, size charts, likes and reviews.

Translation: Uzbek lives in the base field (``name``), Russian and English in
``name_ru`` / ``name_en``. Reading goes through ``core.i18n.tfield`` or the
``|t`` template filter, which fall back to the base field when a translation is
blank. Keeping Uzbek in the base column means every existing row stays valid
with no backfill (plan §7, §17 #8).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
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


class TagKind(models.Model):
    """The axis a tag sits on — style, theme, collection, or whatever comes next.

    A table rather than ``TextChoices`` (§17, Phase 7 recheck). The three that
    shipped are the ones the shop's filters were designed around, but the owner
    writes the tags (§17 #71) and a taxonomy whose axes need a deploy is a
    taxonomy that stops growing at three. ``Tag.kind`` protects these rows: an
    axis that tags are using cannot be deleted out from under them.

    Ordered by id — oldest first, newest last. There was a sort-order column
    and it earned nothing: four rows do not need arranging, and a number the
    owner has to invent before he can add a print method is a box he has to
    think about for no result (§17 #171).
    """
    slug = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=60, help_text="Oʻzbekcha — asosiy matn")
    name_ru = models.CharField(max_length=60, blank=True, default='')
    name_en = models.CharField(max_length=60, blank=True, default='')

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['id']
        verbose_name = _('Teg turi')
        verbose_name_plural = _('Teg turlari')


class PrintMethod(models.Model):
    """How a design is put on the garment — DTF, silkscreen, and so on.

    A table for the same reason as :class:`TagKind`: it is a line in the spec
    strip on the product page, and a shop that adds a technique should not need
    a migration to say so. Ordered by id, for the same reason (§17 #171).
    """
    slug = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=60, help_text="Oʻzbekcha — asosiy matn")
    name_ru = models.CharField(max_length=60, blank=True, default='')
    name_en = models.CharField(max_length=60, blank=True, default='')

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['id']
        verbose_name = _('Bosma usuli')
        verbose_name_plural = _('Bosma usullari')


class Tag(models.Model):
    """A style, theme or collection label.

    Tags — not categories — are what the Phase 13 recommender reads: every
    product is a t-shirt, so ``Category`` carries almost no signal (§17 #26).
    """
    slug = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=60, help_text="Oʻzbekcha — asosiy matn")
    name_ru = models.CharField(max_length=60, blank=True, default='')
    name_en = models.CharField(max_length=60, blank=True, default='')
    # PROTECT, so removing an axis that tags are on fails loudly rather than
    # quietly unfiling every tag under it. Nullable because a tag with no axis
    # yet is a real state — it is one the owner has just typed.
    kind = models.ForeignKey(TagKind, on_delete=models.PROTECT, null=True,
                             blank=True, related_name='tags')

    def __str__(self):
        return f"{self.kind.name if self.kind_id else '—'}: {self.name}"

    class Meta:
        ordering = ['kind', 'slug']


class Measured(models.Model):
    """An uploaded image that knows its own pixel size.

    Phase 9 puts `width` and `height` on every `<img>` the site renders, so the
    browser can hold the space before the file arrives; the numbers have to be
    stored, because reading them from disk while a page renders is a file open
    per image. Filled by the signal that runs after the row commits, and by
    `manage.py build_renditions` for everything uploaded before this existed.

    ``image_field`` is the name of the column holding the file: a product
    photograph calls it `picture`, a size chart calls it `image`, and the
    template tag that renders either of them should not have to know which.
    """
    image_field = 'picture'

    width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(null=True, blank=True, editable=False)

    class Meta:
        abstract = True

    @property
    def photo_file(self):
        """The stored file this row holds, whatever its column is called."""
        return getattr(self, self.image_field, None)

    @property
    def has_photo(self):
        """True when there is a file to render at all."""
        photo = self.photo_file
        return bool(photo and photo.name)

    def sources(self):
        """``[(width, stored name), ...]`` - nothing, for an image with no renditions."""
        return []

    def srcset(self):
        """The ``srcset`` value for this image, or ``''`` when it has none."""
        photo = self.photo_file
        return ', '.join('%s %dw' % (photo.storage.url(name), width)
                         for width, name in self.sources())

    def display_url(self):
        """What ``src`` points at.

        The middle rendition rather than the largest: a browser that understands
        `srcset` never fetches `src` at all, and one that does not is old enough
        that the smaller file is the kinder answer.
        """
        rows = self.sources()
        if not rows:
            return self.photo_file.url if self.has_photo else ''
        return self.photo_file.storage.url(rows[len(rows) // 2][1])

    def zoom_url(self):
        """The largest rendition - what the full-screen viewer opens."""
        rows = self.sources()
        if not rows:
            return self.photo_file.url if self.has_photo else ''
        return self.photo_file.storage.url(rows[-1][1])


class Photograph(Measured):
    """A photograph stored once and delivered as WebP at several widths.

    The product gallery and a customer's review photograph do exactly the same
    thing with their file, so they say it once here; only ``upload_to`` differs,
    which is why ``picture`` itself stays on each table.
    """
    #: ``{'src': <the original's stored name>, 'w': [[width, name], ...]}``.
    #: Keyed by the original's name on purpose: a row whose file was replaced
    #: then describes renditions of a file it no longer holds, and saying so is
    #: what makes the signal rebuild them instead of serving the old picture.
    renditions = models.JSONField(default=dict, blank=True, editable=False)

    class Meta:
        abstract = True

    def sources(self):
        """The renditions that describe the file this row holds *now*."""
        data = self.renditions or {}
        if not self.has_photo or data.get('src') != self.photo_file.name:
            return []
        return [(int(width), name) for width, name in data.get('w', ())]


class SizeChart(Measured):
    """A sizing guide, image first.

    The uploaded chart is the primary content and the only thing the owner has
    to supply; :class:`SizeChartRow` is optional structured data that, when
    present, renders as a table *in addition to* the image — better for screen
    readers and for search engines (§17 #15).

    A name and a picture is the whole of it. There was a ``fit`` here that let
    a chart find its own products, and the cut it keyed on is gone (§17 #172):
    a chart now reaches a product because somebody chose it on the product, or
    because it is the category's, and nothing else.
    """
    #: The chart's own column, not `picture` - see :class:`Measured`.
    image_field = 'image'

    name = models.CharField(max_length=120)
    image = models.ImageField(upload_to='size-charts/', null=True, blank=True)
    note = models.TextField(blank=True, default='', help_text="Oʻzbekcha — asosiy matn")
    note_ru = models.TextField(blank=True, default='')
    note_en = models.TextField(blank=True, default='')

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
    """A catalog product; its sizes, colours, and prices live on related Variants.

    There was a ``fit`` here — two cuts, regular and oversize, as a fixed list.
    It is gone (§17 #172). A cut is a thing the owner wants to *say* about a
    garment, and he already has a way to say it that costs no schema and takes
    any value he likes: a tag. Two fixed choices bought a field on every form,
    a column on every chart, and a third cut that would have been a migration.
    """

    name = models.CharField(max_length=255, help_text="Oʻzbekcha — asosiy matn")
    name_ru = models.CharField(max_length=255, blank=True, default='')
    name_en = models.CharField(max_length=255, blank=True, default='')
    slug = models.SlugField(max_length=255, unique=True)
    # Indexed: every listing that is not filtered is ordered by it - the shop's
    # default sort, the home page's newest row, and the fallback for the
    # popularity and rating sorts (§9 Phase 9 item 8).
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # Why a second timestamp: the sitemap's <lastmod> is the only thing that
    # tells a crawler a product page is worth fetching again, and `created_at`
    # never moves - an edited description or a replaced photograph would never
    # be re-read. `auto_now` fires on save(), which is what the panel's editor
    # calls. The denormalised counters below are written with queryset
    # .update() and F() expressions, which bypass save(), so a like or a new
    # review does not pass for an edit. That is the behaviour we want: lastmod
    # should mean the owner changed the page, not that somebody tapped a heart.
    updated_at = models.DateTimeField(auto_now=True)
    description = models.TextField(null=True, blank=True)
    description_ru = models.TextField(blank=True, default='')
    description_en = models.TextField(blank=True, default='')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    # Required (§17 #228): a product with no tag cannot be filtered to or
    # recommended. `blank=False` makes the Django admin ask for one too; the
    # panel checks it in `panel.catalogue.save_product`.
    tags = models.ManyToManyField(Tag, related_name='products')
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
    # PROTECT: a technique a product is marked with cannot be deleted out from
    # under it. Nullable, because "not stated" is a real answer for a design
    # somebody else printed.
    print_method = models.ForeignKey(PrintMethod, on_delete=models.PROTECT,
                                     null=True, blank=True, related_name='products')

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

        Product's own → its category's → none. There used to be a third step,
        the standard chart for the product's cut, and it went with the cut
        (§17 #172); the migration that dropped the column wrote each product's
        resolved chart onto the product first, so nothing on the shelf lost its
        size guide. Nothing at all is still a correct answer: a chart that might
        not match the garment is worse than no chart (§17 #95).
        """
        if self.size_chart_id:
            return self.size_chart
        if self.category_id and self.category.size_chart_id:
            return self.category.size_chart
        return None


class ImageP(Photograph):
    """A product photo, displayed in ``order`` (lowest first)."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    picture = models.ImageField(upload_to="products/")
    order = models.PositiveSmallIntegerField()

    def __str__(self):
        return f"{self.id} | {self.product.name} | {self.order} | {self.picture.name.split('/')[-1]}"

    class Meta:
        ordering = ['order', 'id']


class Size(models.Model):
    """A selectable size value, in the order the shop sells them.

    The ordering matters and was missing. ``Variant`` orders by ``size``, which
    is by id, so the storefront and the panel's list already showed S, M, L, XL
    — but ``Size.objects.all()`` had no ordering at all, and the panel's
    size/price/stock grid is built from exactly that. Postgres is free to hand
    back an unordered scan in any order it likes, and it changes the order of a
    row it has updated, so the grid on the most important screen in the panel
    was one edit away from coming back shuffled. Ordering by id is the order
    the sizes were seeded in, which is the order everything else already
    assumes.
    """
    size = models.CharField(max_length=50)

    def __str__(self):
        return self.size

    class Meta:
        ordering = ['id']


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


#: At or below this many left, a size is "running low" and the panel says so.
#: It lives on the model rather than in the panel because it is a fact about the
#: catalogue, and three screens ask the question — the dashboard's tile, the
#: list behind that tile, and the coloured size pill on the products list. Three
#: copies of a threshold is three chances for the tile to say one number and
#: the list it opens to show another (§17 #179).
LOW_STOCK = 5


class VariantQuerySet(models.QuerySet):
    """The two questions every screen asks about a variant, asked once here."""

    def on_sale(self):
        """Variants a customer could actually be offered right now.

        Both switches have to agree: the owner's per-size ``available`` flag and
        the product's own ``is_active``. A size taken off sale, or a product
        withdrawn, is not stock anybody is waiting to sell.
        """
        return self.filter(available=True, product__is_active=True)

    def running_low(self):
        """On sale, and down to the last few.

        Zero is included on purpose: a size on sale with nothing behind it is
        the most urgent row on the list, not an excluded one.
        """
        return self.on_sale().filter(stock__lte=LOW_STOCK)


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

    objects = VariantQuerySet.as_manager()

    def __str__(self):
        return  f"{self.product.name} | {self.colour.colour} | {self.size.size}"

    @property
    def is_purchasable(self):
        """Available *and* actually in stock."""
        return self.available and self.stock > 0

    @property
    def is_running_low(self):
        """Still sellable, but not for many more parcels.

        Deliberately *not* the same test as the queryset's ``running_low``: this
        one drives the colour of a size pill, and a size with nothing left is
        already saying that in red. Amber is the warning before the warning.
        """
        return self.is_purchasable and self.stock <= LOW_STOCK

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
        # The product page's query, exactly: this product, approved, newest
        # first. `status` has an index of its own and `product` has the foreign
        # key's, but neither answers the three together (§9 Phase 9 item 8).
        indexes = [models.Index(fields=['product', 'status', '-created_at'])]
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


def slide_link(value):
    """A slide may point at a page on this site, or at an http(s) address.

    Nothing else, and this is not fussiness. The owner types this into a box
    in the panel and the value lands in an `href` on the busiest page of the
    site: `javascript:` there is a script injection with a human talked into
    performing it, and a protocol-relative `//host/path` is an off-site link
    that reads like an internal one. Neither has a use in a promotional card.

    Blank is allowed. A slide that announces something without linking
    anywhere is a real slide, and demanding a link would only produce a
    fake one.
    """
    if not value:
        return
    if value.startswith('/') and not value.startswith('//'):
        return
    if value.startswith('http://') or value.startswith('https://'):
        return
    raise ValidationError(
        _('Havola «/» bilan yoki https:// bilan boshlanishi kerak.'))


class Slide(Photograph):
    """A promotional card at the top of the home page, managed from the panel.

    It replaces the hero (§17 #251). The owner wanted what every marketplace
    here leads with — a row of tappable cards he changes himself — rather
    than a headline only a deploy can edit.

    On :class:`Photograph` rather than a bare `ImageField`, so a slide gets
    WebP renditions and stored pixel dimensions like every other picture on
    the site (§17 #230). Those stored dimensions are also what holds the
    carousel's box before the file arrives, and the home page is measured on
    a CLS of zero.

    ``alt`` is the one thing the owner writes beyond uploading a file and
    pasting a link, and it is not optional. A slide is an image inside a
    link, and a link whose only content is an image has no accessible name at
    all — axe-core calls it `link-name`, and Phase 9 shipped with zero
    violations over ten pages. Russian and English may be blank and fall back
    to the Uzbek, the same as every other translated row.
    """
    picture = models.ImageField(upload_to='slides/')
    #: Where tapping the card goes. See :func:`slide_link`.
    link = models.CharField(max_length=200, blank=True, default='',
                            validators=[slide_link])
    alt = models.CharField(max_length=120, help_text="Oʻzbekcha — asosiy matn")
    alt_ru = models.CharField(max_length=120, blank=True, default='')
    alt_en = models.CharField(max_length=120, blank=True, default='')
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        state = 'yoqilgan' if self.is_active else 'oʻchirilgan'
        return self.alt + ' (' + state + ')'

    class Meta:
        ordering = ['sort_order', 'id']


class ReviewImage(Photograph):
    """A photo attached to a review. Only visible once its review is approved."""
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='images')
    picture = models.ImageField(upload_to='reviews/')
    order = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"{self.review_id} · {self.picture.name.split('/')[-1]}"

    class Meta:
        ordering = ['order', 'id']
