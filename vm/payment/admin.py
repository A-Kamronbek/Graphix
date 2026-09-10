"""Admin for orders, delivery tiers and pickup points.

Order details stay read-only — they are a record of what was agreed, and the
frozen ``delivery_price`` and ``pickup_snapshot`` only mean something if nobody
edits them afterwards. Status is the one editable field. The full admin pass is
Phase 7.
"""
from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.utils.html import format_html_join
from click_up.models import ClickTransaction
from .models import DeliveryOption, Order, PickupPoint


# Hide click_up's default ClickTransaction admin; raw transactions aren't exposed.
try:
    admin.site.unregister(ClickTransaction)
except NotRegistered:
    pass


@admin.register(DeliveryOption)
class DeliveryOptionAdmin(admin.ModelAdmin):
    """Delivery tiers. Rows, not constants, so a price can change without a deploy."""
    list_display = ('name', 'code', 'price', 'requires_pickup_point',
                    'free_from_items', 'is_active', 'sort_order')
    list_editable = ('price', 'is_active', 'sort_order')
    list_filter = ('is_active', 'requires_pickup_point')
    search_fields = ('code', 'name', 'name_ru', 'name_en')
    fieldsets = (
        (None, {'fields': ('code', 'price', 'free_from_items',
                           'requires_pickup_point', 'is_active', 'sort_order'),
                'description': "free_from_items = 0 boʻlsa, bepul yetkazish yoʻq."}),
        ('Oʻzbekcha', {'fields': ('name', 'note')}),
        ('Русский', {'fields': ('name_ru', 'note_ru')}),
        ('English', {'fields': ('name_en', 'note_en')}),
    )


@admin.register(PickupPoint)
class PickupPointAdmin(admin.ModelAdmin):
    """Uzpost branches. Normally loaded by ``manage.py seed_pickup_points``.

    Editing one by hand is fine, but the CSV is the source of truth: the next seed
    run overwrites whatever the command finds for that ``code``.
    """
    list_display = ('code', 'name', 'region', 'district', 'is_active', 'sort_order')
    list_editable = ('is_active', 'sort_order')
    list_filter = ('is_active', 'region')
    search_fields = ('code', 'name', 'name_ru', 'name_en', 'address', 'district')
    ordering = ('region', 'district', 'name')
    fieldsets = (
        (None, {'fields': ('code', 'region', 'district', 'latitude', 'longitude',
                           'working_hours', 'phone', 'is_active', 'sort_order')}),
        ('Oʻzbekcha', {'fields': ('name', 'address')}),
        ('Русский', {'fields': ('name_ru', 'address_ru')}),
        ('English', {'fields': ('name_en', 'address_en')}),
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
        'delivery_option', 'delivery_price', 'pickup_point', 'pickup_snapshot',
        'latitude', 'longitude',
    )
    fields = (
        'order_no', 'user', 'status', 'payment_method', 'total_price',
        'phone', 'address', 'notes', 'items_summary',
        'delivery_option', 'delivery_price', 'pickup_point', 'pickup_snapshot',
        'latitude', 'longitude', 'created_at', 'updated_at',
    )

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
