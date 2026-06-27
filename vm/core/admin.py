from django.contrib import admin
from .models import Msg

# ---- panel branding ----
admin.site.site_header = "ValleyMade boshqaruv paneli"
admin.site.site_title = "ValleyMade admin"
admin.site.index_title = "Boshqaruv"


@admin.register(Msg)
class MsgAdmin(admin.ModelAdmin):
    """Customer contact messages — read-only (they come from the public form)."""
    list_display = ('topic', 'user', 'phone_num', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('topic', 'msg_text', 'user__username', 'phone_num')
    readonly_fields = ('user', 'phone_num', 'topic', 'msg_text', 'created_at')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
