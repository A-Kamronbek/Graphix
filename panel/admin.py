"""The status trail in the Django admin: readable, never writable.

An audit log you can edit is not an audit log. Everything here is read-only,
including for a superuser, and rows are added only by ``panel.services``.
"""
from django.contrib import admin

from .models import OrderStatusChange


@admin.register(OrderStatusChange)
class OrderStatusChangeAdmin(admin.ModelAdmin):
    list_display = ('order', 'from_status', 'to_status', 'changed_by', 'changed_at')
    list_filter = ('to_status', 'changed_at')
    search_fields = ('order__order_no', 'changed_by__username', 'note')
    list_select_related = ('order', 'changed_by')
    date_hierarchy = 'changed_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
