"""Admin: global site branding and the read-only contact-message view."""
from django.contrib import admin
from .models import Msg

admin.site.site_header = "GRAPHIX boshqaruv paneli"
admin.site.site_title = "GRAPHIX admin"
admin.site.index_title = "Boshqaruv"


@admin.register(Msg)
class MsgAdmin(admin.ModelAdmin):
    """Read-only admin for contact-form messages (add/edit disabled)."""
    list_display = ('topic', 'user', 'phone_num', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('topic', 'msg_text', 'user__username', 'phone_num')
    readonly_fields = ('user', 'phone_num', 'topic', 'msg_text', 'created_at')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
