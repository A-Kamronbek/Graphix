from django.contrib import admin
from click_up.models import ClickTransaction
from .models import Order

admin.site.register(Order)


# @admin.register(ClickTransaction)
# class ClickTransactionAdmin(admin.ModelAdmin):
#     """Click payment ledger. Rows are created by the webhook, so this is a
#     read-only audit view — don't hand-edit transactions."""
#     list_display = ('id', 'account_id', 'transaction_id', 'amount', 'state', 'created_at')
#     list_filter = ('state', 'created_at')
#     search_fields = ('account_id', 'transaction_id')
#     ordering = ('-created_at',)
#     readonly_fields = ('account_id', 'transaction_id', 'amount', 'state', 'created_at', 'updated_at')
#
#     def has_add_permission(self, request):
#         return False
#
#     def has_change_permission(self, request, obj=None):
#         return False

