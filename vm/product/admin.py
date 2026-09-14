"""Admin for the catalog: products with inline images/variants, plus lookups.

Phase 4 registers the new models and keeps the product form honest about what the
owner actually has to fill in: no slug (derived from the name), no colour (there
is only one colourway), and no denormalised counters (maintained by code). The
full admin pass is Phase 7.
"""
from django.contrib import admin
from django.db.models import Min, Count
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import (Category, Colour, ImageP, PrintMethod, Product,
                     ProductLike, Review, ReviewImage, Size, SizeChart,
                     SizeChartRow, Tag, TagKind, Variant, default_colour)


def _thumb(picture, size=60):
    """Small <img> preview for an ImageField, or a dash when empty."""
    if not picture:
        return mark_safe('<span style="color:#999;">—</span>')
    return format_html(
        '<img src="{}" style="height:{}px;width:{}px;object-fit:cover;'
        'border-radius:6px;" />',
        picture.url, size, size,
    )


class ImagePInline(admin.TabularInline):
    """Inline editor for a product's images."""
    model = ImageP
    extra = 1
    fields = ('preview', 'picture', 'order')
    readonly_fields = ('preview',)
    ordering = ('order', 'id')

    @admin.display(description='Ko\'rinishi')
    def preview(self, obj):
        return _thumb(obj.picture)


class VariantInline(admin.TabularInline):
    """Inline editor for a product's variants.

    ``colour`` is deliberately absent: the storefront has no colour picker, so
    ProductAdmin.save_formset fills it with the default colour. One row per size
    is all the owner should have to think about.
    """
    model = Variant
    extra = 1
    fields = ('size', 'price', 'available', 'stock')
    autocomplete_fields = ('size',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Product admin with image/variant inlines and annotated list columns."""
    list_display = ('thumb', 'name', 'category', 'is_active', 'variant_count',
                    'stock_total', 'min_price', 'image_count', 'created_at')
    list_display_links = ('thumb', 'name')
    list_editable = ('is_active',)
    list_filter = ('is_active', 'category', 'tags', 'print_method', 'fit', 'created_at')
    search_fields = ('name', 'name_ru', 'name_en', 'slug', 'description')
    inlines = [ImagePInline, VariantInline]
    list_select_related = ('category',)
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ('tags',)
    autocomplete_fields = ('category', 'size_chart')
    # Maintained with F() expressions by the like and review flows, never by hand.
    readonly_fields = ('likes_count', 'rating_avg', 'review_count', 'created_at')

    # One fieldset per language, Uzbek first, so it is obvious which box is
    # which and that Uzbek is the source the other two are written from.
    # Russian and English may be left blank: |t falls back to the Uzbek field.
    fieldsets = (
        (None, {'fields': ('category', 'slug', 'is_active', 'tags')}),
        ('Oʻzbekcha', {'fields': ('name', 'description', 'material')}),
        ('Русский', {'fields': ('name_ru', 'description_ru', 'material_ru'),
                      'description': "Boʻsh qoldirilsa, oʻzbekcha matn koʻrsatiladi."}),
        ('English', {'fields': ('name_en', 'description_en', 'material_en'),
                     'description': "Boʻsh qoldirilsa, oʻzbekcha matn koʻrsatiladi."}),
        ('Xususiyatlari', {'fields': ('gsm', 'print_method', 'fit', 'size_chart'),
                           'description': "Mahsulot sahifasidagi xususiyatlar qatori."}),
        ('Hisoblangan', {'fields': ('likes_count', 'rating_avg', 'review_count', 'created_at'),
                         'classes': ('collapse',)}),
    )

    def save_formset(self, request, form, formset, change):
        """Give every new variant the default colour (plan §7, §17 #23).

        The owner never picks a colour, so one is assigned here. An existing
        variant that already points at some other colour is left untouched.
        """
        instances = formset.save(commit=False)
        if formset.model is Variant:
            fallback = None
            for instance in instances:
                if not instance.colour_id:
                    fallback = fallback or default_colour()
                    instance.colour = fallback
        for instance in instances:
            instance.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()

    @admin.display(description='Rasm')
    def thumb(self, obj):
        first = obj.images.first()
        return _thumb(first.picture if first else None, size=48)

    def get_queryset(self, request):
        """Annotate variant/image counts and min price for the list columns."""
        qs = super().get_queryset(request)
        return qs.annotate(
            _variants=Count('variants', distinct=True),
            _images=Count('images', distinct=True),
            _min_price=Min('variants__price'),
        )

    @admin.display(description='Variantlar', ordering='_variants')
    def variant_count(self, obj):
        return obj._variants

    @admin.display(description='Omborda')
    def stock_total(self, obj):
        """Total units across this product's variants — the number that matters daily."""
        return sum(v.stock for v in obj.variants.all())

    @admin.display(description='Rasmlar', ordering='_images')
    def image_count(self, obj):
        return obj._images

    @admin.display(description='Eng arzon narx', ordering='_min_price')
    def min_price(self, obj):
        return obj._min_price


@admin.register(Variant)
class VariantAdmin(admin.ModelAdmin):
    """Variant admin with inline price/availability/stock editing."""
    list_display = ('product', 'size', 'price', 'available', 'stock', 'purchasable')
    list_editable = ('price', 'available', 'stock')
    list_filter = ('available', 'size')
    search_fields = ('product__name',)
    autocomplete_fields = ('product', 'colour', 'size')
    list_select_related = ('product', 'colour', 'size')

    @admin.display(description='Sotiladi', boolean=True)
    def purchasable(self, obj):
        return obj.is_purchasable


class LookupAdmin(admin.ModelAdmin):
    """The shape both small lookup tables want: name, order, and a slug.

    ``TagKind`` and ``PrintMethod`` are edited from the panel; this is the
    fallback, and it exists mainly so a superuser can see what is in them.
    """
    list_display = ('name', 'slug', 'order', 'name_ru', 'name_en')
    list_editable = ('order',)
    search_fields = ('name', 'name_ru', 'name_en', 'slug')
    prepopulated_fields = {'slug': ('name',)}


admin.site.register(TagKind, LookupAdmin)
admin.site.register(PrintMethod, LookupAdmin)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    """Tag lookup admin. Tags, not categories, drive filtering and recommendations."""
    list_display = ('name', 'kind', 'slug', 'product_count')
    list_filter = ('kind',)
    list_select_related = ('kind',)
    search_fields = ('name', 'name_ru', 'name_en', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        (None, {'fields': ('kind', 'slug')}),
        ('Oʻzbekcha', {'fields': ('name',)}),
        ('Русский', {'fields': ('name_ru',)}),
        ('English', {'fields': ('name_en',)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_products=Count('products'))

    @admin.display(description='Mahsulotlar', ordering='_products')
    def product_count(self, obj):
        return obj._products


class SizeChartRowInline(admin.TabularInline):
    """Optional measured rows for a chart. The uploaded image is the real content."""
    model = SizeChartRow
    extra = 0
    autocomplete_fields = ('size',)
    ordering = ('order',)


@admin.register(SizeChart)
class SizeChartAdmin(admin.ModelAdmin):
    """Size-guide admin. Image first; the table is optional (§17 #15)."""
    list_display = ('preview', 'name', 'row_count')
    list_display_links = ('preview', 'name')
    search_fields = ('name',)
    inlines = [SizeChartRowInline]
    readonly_fields = ('big_preview',)
    fieldsets = (
        (None, {'fields': ('name', 'image', 'big_preview'),
                'description': "Rasm asosiy mazmun. Jadval majburiy emas."}),
        ('Oʻzbekcha', {'fields': ('note',)}),
        ('Русский', {'fields': ('note_ru',)}),
        ('English', {'fields': ('note_en',)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_rows=Count('rows'))

    @admin.display(description='Rasm')
    def preview(self, obj):
        return _thumb(obj.image, size=48)

    @admin.display(description='Ko\'rinishi')
    def big_preview(self, obj):
        return _thumb(obj.image, size=260)

    @admin.display(description='Qatorlar', ordering='_rows')
    def row_count(self, obj):
        return obj._rows


class ReviewImageInline(admin.TabularInline):
    """Photos attached to a review; visible on the site only once approved."""
    model = ReviewImage
    extra = 0
    fields = ('preview', 'picture', 'order')
    readonly_fields = ('preview',)

    @admin.display(description='Ko\'rinishi')
    def preview(self, obj):
        return _thumb(obj.picture, size=80)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    """Review moderation. Nothing reaches the site until a staff member approves it."""
    list_display = ('product', 'user', 'rating', 'status', 'created_at')
    list_filter = ('status', 'rating', 'created_at')
    search_fields = ('product__name', 'user__username', 'text')
    list_select_related = ('product', 'user')
    autocomplete_fields = ('product', 'user', 'order')
    inlines = [ReviewImageInline]
    readonly_fields = ('user', 'product', 'order', 'rating', 'text',
                       'moderated_by', 'moderated_at', 'created_at')
    actions = ['approve_selected', 'reject_selected']

    def _moderate(self, request, queryset, status):
        """Stamp who moderated and when, and move the product's rating with it.

        Through the service rather than a bare ``update()`` here: the update is
        a bulk statement, so it fires no signals, and approving a review used
        to leave ``rating_avg`` and ``review_count`` exactly as they were —
        the moderation queue worked and the product page never heard about it.
        """
        from .services import moderate
        return moderate(queryset, status, by=request.user)

    @admin.action(description='Tasdiqlash')
    def approve_selected(self, request, queryset):
        count = self._moderate(request, queryset, Review.Status.APPROVED)
        self.message_user(request, f"{count} sharh tasdiqlandi.")

    @admin.action(description='Rad etish')
    def reject_selected(self, request, queryset):
        count = self._moderate(request, queryset, Review.Status.REJECTED)
        self.message_user(request, f"{count} sharh rad etildi.")


@admin.register(ProductLike)
class ProductLikeAdmin(admin.ModelAdmin):
    """Read-only view of likes; the public count lives on Product.likes_count."""
    list_display = ('product', 'user', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('product__name', 'user__username')
    list_select_related = ('product', 'user')
    readonly_fields = ('user', 'product', 'created_at')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Category lookup admin."""
    list_display = ('name', 'slug', 'name_ru', 'name_en')
    search_fields = ('name', 'name_ru', 'name_en', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    autocomplete_fields = ('size_chart',)
    fieldsets = (
        (None, {'fields': ('slug', 'size_chart')}),
        ('Oʻzbekcha', {'fields': ('name',)}),
        ('Русский', {'fields': ('name_ru',)}),
        ('English', {'fields': ('name_en',)}),
    )


@admin.register(Size)
class SizeAdmin(admin.ModelAdmin):
    """Size lookup admin."""
    list_display = ('size',)
    search_fields = ('size',)


@admin.register(Colour)
class ColourAdmin(admin.ModelAdmin):
    """Colour lookup admin.

    Colour is hidden from the storefront UI but kept in the data model (§17 #23),
    so these translations exist for the admin and for a future re-enable.
    """
    list_display = ('colour', 'colour_ru', 'colour_en', 'hex_code')
    search_fields = ('colour', 'colour_ru', 'colour_en')
    fieldsets = (
        (None, {'fields': ('hex_code',)}),
        ('Oʻzbekcha', {'fields': ('colour',)}),
        ('Русский', {'fields': ('colour_ru',)}),
        ('English', {'fields': ('colour_en',)}),
    )


@admin.register(ImageP)
class ImagePAdmin(admin.ModelAdmin):
    """Standalone product-image admin with thumbnail previews."""
    list_display = ('thumb', 'product', 'order')
    list_display_links = ('thumb', 'product')
    search_fields = ('product__name',)
    autocomplete_fields = ('product',)
    readonly_fields = ('preview',)
    fields = ('product', 'picture', 'preview', 'order')

    @admin.display(description='Rasm')
    def thumb(self, obj):
        return _thumb(obj.picture, size=48)

    @admin.display(description='Ko\'rinishi')
    def preview(self, obj):
        return _thumb(obj.picture, size=200)
