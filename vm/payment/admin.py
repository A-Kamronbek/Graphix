"""Admin for orders: read-only details with an items summary and editable status."""
from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.utils.html import format_html_join
from click_up.models import ClickTransaction
from .models import Order


# Hide click_up's default ClickTransaction admin; raw transactions aren't exposed.
try:
    admin.site.unregister(ClickTransaction)
except NotRegistered:
    pass


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Order admin: details are read-only, but status is editable from the list."""
    list_display = ('id', 'user', 'status', 'payment_method', 'total_price', 'phone', 'created_at')
    list_editable = ('status',)            # change status straight from the list
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('id', 'phone', 'user__username', 'address')
    list_select_related = ('user', 'cart')
    ordering = ('-created_at',)

    readonly_fields = (
        'user', 'cart', 'total_price', 'payment_method',
        'phone', 'address', 'notes', 'items_summary', 'created_at', 'updated_at',
    )
    fields = (
        'user', 'status', 'payment_method', 'total_price',
        'phone', 'address', 'notes', 'items_summary', 'created_at', 'updated_at',
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
