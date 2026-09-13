"""Admin for orders, delivery tiers, payment methods and the region reference data.

Order details stay read-only — they are a record of what was agreed, and the
frozen ``delivery_price`` and ``location_snapshot`` only mean something if nobody
edits them afterwards. Status is the one editable field. The full admin pass is
Phase 7.
"""
from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.utils.html import format_html_join
from click_up.models import ClickTransaction
from .models import DeliveryOption, District, Order, PaymentOption, Region


# Hide click_up's default ClickTransaction admin; raw transactions aren't exposed.
try:
    admin.site.unregister(ClickTransaction)
except NotRegistered:
    pass


@admin.register(DeliveryOption)
class DeliveryOptionAdmin(admin.ModelAdmin):
    """Delivery tiers. Rows, not constants, so a price can change without a deploy."""
    list_display = ('name', 'code', 'price', 'requires_branch',
                    'free_from_items', 'is_active', 'sort_order')
    list_editable = ('price', 'is_active', 'sort_order')
    list_filter = ('is_active', 'requires_branch')
    search_fields = ('code', 'name', 'name_ru', 'name_en')
    fieldsets = (
        (None, {'fields': ('code', 'price', 'free_from_items',
                           'requires_branch', 'is_active', 'sort_order'),
                'description': "free_from_items = 0 boʻlsa, bepul yetkazish yoʻq."}),
        ('Oʻzbekcha', {'fields': ('name', 'note')}),
        ('Русский', {'fields': ('name_ru', 'note_ru')}),
        ('English', {'fields': ('name_en', 'note_en')}),
    )


@admin.register(PaymentOption)
class PaymentOptionAdmin(admin.ModelAdmin):
    """Payment methods. Cash ships switched off; this is where it is turned on.

    ``is_active`` is editable from the list because that is the whole job: an
    inactive method is not offered at checkout and is refused server-side, and
    flipping it needs no deploy.
    """
    list_display = ('name', 'code', 'is_active', 'sort_order')
    list_editable = ('is_active', 'sort_order')
    list_filter = ('is_active',)
    search_fields = ('code', 'name', 'name_ru', 'name_en')
    fieldsets = (
        (None, {'fields': ('code', 'is_active', 'sort_order'),
                'description': "Oʻchirilgan usul rasmiylashtirish sahifasida "
                               "umuman koʻrsatilmaydi."}),
        ('Oʻzbekcha', {'fields': ('name', 'note')}),
        ('Русский', {'fields': ('name_ru', 'note_ru')}),
        ('English', {'fields': ('name_en', 'note_en')}),
    )


class DistrictInline(admin.TabularInline):
    """The districts and cities of one region, edited where they belong."""
    model = District
    extra = 0
    fields = ('name', 'name_ru', 'name_en', 'kind', 'code', 'is_active', 'sort_order')


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    """Regions and their postal prefixes.

    The prefix is the field to be careful with: it is what the checkout checks a
    typed index against, so a wrong one silently rejects every valid index for
    that region — a lost sale the owner never hears about. Normally loaded by
    ``manage.py seed_regions``; the CSV is the source of truth.
    """
    list_display = ('name', 'code', 'postal_prefix', 'district_count',
                    'is_active', 'sort_order')
    list_editable = ('is_active', 'sort_order')
    list_filter = ('is_active',)
    search_fields = ('code', 'name', 'name_ru', 'name_en', 'postal_prefix')
    inlines = [DistrictInline]
    fieldsets = (
        (None, {'fields': ('code', 'postal_prefix', 'is_active', 'sort_order'),
                'description': "postal_prefix — indeksning boshlanishi "
                               "(masalan, Toshkent shahri uchun 100)."}),
        ('Oʻzbekcha', {'fields': ('name',)}),
        ('Русский', {'fields': ('name_ru',)}),
        ('English', {'fields': ('name_en',)}),
    )

    def get_queryset(self, request):
        from django.db.models import Count
        return super().get_queryset(request).annotate(_districts=Count('districts'))

    @admin.display(description='Tuman va shaharlar', ordering='_districts')
    def district_count(self, obj):
        return obj._districts


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    """Districts and cities. Searchable, because there are two hundred of them."""
    list_display = ('name', 'region', 'kind', 'code', 'is_active')
    list_editable = ('is_active',)
    list_filter = ('region', 'kind', 'is_active')
    search_fields = ('code', 'name', 'name_ru', 'name_en')
    list_select_related = ('region',)
    autocomplete_fields = ('region',)
    fieldsets = (
        (None, {'fields': ('region', 'code', 'kind', 'is_active', 'sort_order')}),
        ('Oʻzbekcha', {'fields': ('name',)}),
        ('Русский', {'fields': ('name_ru',)}),
        ('English', {'fields': ('name_en',)}),
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Order admin: details are read-only, but status is editable from the list."""
    list_display = ('order_no', 'user', 'status', 'payment_method', 'total_price',
                    'delivery_option', 'phone', 'created_at')
    list_display_links = ('order_no',)
    list_editable = ('status',)            # change status straight from the list
    list_filter = ('status', 'payment_method', 'delivery_option', 'created_at')
    search_fields = ('order_no', 'id', 'phone', 'user__username', 'address')
    list_select_related = ('user', 'cart', 'delivery_option')
    ordering = ('-created_at',)

    readonly_fields = (
        'order_no', 'user', 'cart', 'total_price', 'payment_method',
        'phone', 'address', 'notes', 'items_summary', 'created_at', 'updated_at',
        'delivery_option', 'delivery_price', 'region', 'district', 'postal_index',
        'location_note', 'location_snapshot', 'latitude', 'longitude',
        'address_source', 'map_link',
    )
    fields = (
        'order_no', 'user', 'status', 'payment_method', 'total_price',
        'phone', 'address', 'notes', 'items_summary',
        'delivery_option', 'delivery_price', 'region', 'district', 'postal_index',
        'location_note', 'location_snapshot', 'latitude', 'longitude',
        'address_source', 'map_link', 'created_at', 'updated_at',
    )

    @admin.display(description='Xaritada')
    def map_link(self, obj):
        """A maps deep link for the courier, when there is a pin to follow."""
        from django.utils.html import format_html
        if obj.latitude is None or obj.longitude is None:
            return '—'
        url = f"https://www.google.com/maps/search/?api=1&query={obj.latitude},{obj.longitude}"
        return format_html('<a href="{}" target="_blank" rel="noopener">{}, {}</a>',
                           url, obj.latitude, obj.longitude)

    @admin.display(description='Buyurtma tarkibi')
    def items_summary(self, obj):
        items = obj.cart.cart_items.select_related(
            'variant__product', 'variant__size', 'variant__colour'
        )
        rows = format_html_join(
            '', "<div>{} — {} / {} × {}</div>",
            (
                (
                    it.variant.product.name,
                    it.variant.colour.colour,
                    it.variant.size.size,
                    it.quantity,
                )
                for it in items
            ),
        )
        return rows or "—"
