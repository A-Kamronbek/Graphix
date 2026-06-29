from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Show phone + verification status in the user list.
    list_display = UserAdmin.list_display + ('phone', 'phone_verified')
    list_filter = UserAdmin.list_filter + ('phone_verified',)
    search_fields = UserAdmin.search_fields + ('phone',)

    # Show phone + verification on the edit page.
    fieldsets = UserAdmin.fieldsets + (
        ('Aloqa', {'fields': ('phone', 'phone_verified')}),
    )

    # Show phone on the "add user" page.
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Aloqa', {'fields': ('phone',)}),
    )
