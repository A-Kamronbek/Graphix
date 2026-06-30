"""Admin for the catalog: products with inline images/variants, plus lookups."""
from django.contrib import admin
from django.db.models import Min, Count
from django.utils.html import format_html
from .models import Product, Category, Size, Colour, ImageP, Variant


def _thumb(picture, size=60):
    """Small <img> preview for an ImageField, or a dash when empty."""
    if not picture:
        return format_html('<span style="color:#999;">\u2014</span>')
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
    """Inline editor for a product's variants."""
    model = Variant
    extra = 1
    fields = ('colour', 'size', 'price', 'available')
    autocomplete_fields = ('colour', 'size')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Product admin with image/variant inlines and annotated list columns."""
    list_display = ('thumb', 'name', 'category', 'variant_count', 'min_price', 'image_count', 'created_at')
    list_display_links = ('thumb', 'name')
    list_filter = ('category', 'created_at')
    search_fields = ('name', 'description')
    inlines = [ImagePInline, VariantInline]
    list_select_related = ('category',)

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

    @admin.display(description='Rasmlar', ordering='_images')
    def image_count(self, obj):
        return obj._images

    @admin.display(description='Eng arzon narx', ordering='_min_price')
    def min_price(self, obj):
        return obj._min_price


@admin.register(Variant)
class VariantAdmin(admin.ModelAdmin):
    """Variant admin with inline price/availability editing."""
    list_display = ('product', 'colour', 'size', 'price', 'available')
    list_editable = ('price', 'available')
    list_filter = ('available', 'size', 'colour')
    search_fields = ('product__name',)
    autocomplete_fields = ('product', 'colour', 'size')
    list_select_related = ('product', 'colour', 'size')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Category lookup admin."""
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Size)
class SizeAdmin(admin.ModelAdmin):
    """Size lookup admin."""
    list_display = ('size',)
    search_fields = ('size',)


@admin.register(Colour)
class ColourAdmin(admin.ModelAdmin):
    """Colour lookup admin."""
    list_display = ('colour', 'hex_code')
    search_fields = ('colour',)


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
