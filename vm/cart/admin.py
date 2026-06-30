"""Admin for carts, with a read-only line-item inline."""
from django.contrib import admin
from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    """Read-only inline of a cart's line items (no add)."""
    model = CartItem
    extra = 0
    can_delete = False
    readonly_fields = ('variant', 'quantity', 'price_stat', 'created_at')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    """Cart admin with an item-count column and the line-item inline."""
    list_display = ('id', 'user', 'status', 'item_count', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username',)
    list_select_related = ('user',)
    inlines = [CartItemInline]

    @admin.display(description='Mahsulotlar soni')
    def item_count(self, obj):
        return obj.cart_items.count()
