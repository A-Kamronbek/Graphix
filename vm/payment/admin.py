from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.utils.html import format_html_join
from click_up.models import ClickTransaction
from .models import Order

# click_up registers its own ClickTransaction admin on import. Drop it so we
# can register our read-only version below without an AlreadyRegistered error.
try:
    admin.site.unregister(ClickTransaction)
except NotRegistered:
    pass


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """
    Order management. The admin's main job here is moving the status forward
    (paying → processing → on_the_way → done) and seeing the delivery details.
    Everything except status is read-only so checkout data can't be corrupted.
    """
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


# @admin.register(ClickTransaction)
# class ClickTransactionAdmin(admin.ModelAdmin):
#     """Click payment ledger. Rows are created by the webhook, so this is a
#     read-only audit view — don't hand-edit transactions."""
#     list_display = ('id', 'account_id', 'transaction_id', 'amount', 'state', 'created_at')
#     list_filter = ('state', 'created_at')
#     search_fields = ('transaction_id',)
#     ordering = ('-created_at',)
#     readonly_fields = ('account_id', 'transaction_id', 'amount', 'state', 'created_at', 'updated_at')
#
#     def has_add_permission(self, request):
#         return False
#
#     def has_change_permission(self, request, obj=None):
#         return False
