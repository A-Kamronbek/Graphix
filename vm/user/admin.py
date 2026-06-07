from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


class CustomUserAdmin(UserAdmin):
    # Show phone in the user list page
    list_display = UserAdmin.list_display + ('phone',)

    # Show phone on the edit page
    fieldsets = UserAdmin.fieldsets + (
        ('Contact info', {'fields': ('phone',)}),
    )

    # Show phone on the "add user" page
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Contact info', {'fields': ('phone',)}),
    )


admin.site.register(User, CustomUserAdmin)