from django.contrib import admin
from django.db.models import Min, Count
from .models import Product, Category, Size, Colour, ImageP, Variant


class ImagePInline(admin.TabularInline):
    """Manage a product's images right on the product page."""
    model = ImageP
    extra = 1
    fields = ('picture', 'order')
    ordering = ('order', 'id')


class VariantInline(admin.TabularInline):
    """Manage a product's colour/size/price/stock right on the product page."""
    model = Variant
    extra = 1
    fields = ('colour', 'size', 'price', 'available')
    autocomplete_fields = ('colour', 'size')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'variant_count', 'min_price', 'image_count', 'created_at')
    list_filter = ('category', 'created_at')
    search_fields = ('name', 'description')
    inlines = [ImagePInline, VariantInline]
    list_select_related = ('category',)

    def get_queryset(self, request):
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
    """Bulk-manage stock: edit price + availability straight from the list."""
    list_display = ('product', 'colour', 'size', 'price', 'available')
    list_editable = ('price', 'available')
    list_filter = ('available', 'size', 'colour')
    search_fields = ('product__name',)
    autocomplete_fields = ('product', 'colour', 'size')
    list_select_related = ('product', 'colour', 'size')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Size)
class SizeAdmin(admin.ModelAdmin):
    list_display = ('size',)
    search_fields = ('size',)


@admin.register(Colour)
class ColourAdmin(admin.ModelAdmin):
    list_display = ('colour', 'hex_code')
    search_fields = ('colour',)


@admin.register(ImageP)
class ImagePAdmin(admin.ModelAdmin):
    list_display = ('product', 'order')
    search_fields = ('product__name',)
    autocomplete_fields = ('product',)
