"""Admin registration for the custom User model."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """User admin extended with the phone and phone_verified fields."""
    list_display = UserAdmin.list_display + ('phone', 'phone_verified')
    list_filter = UserAdmin.list_filter + ('phone_verified',)
    search_fields = UserAdmin.search_fields + ('phone',)

    fieldsets = UserAdmin.fieldsets + (
        ('Aloqa', {'fields': ('phone', 'phone_verified')}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Aloqa', {'fields': ('phone',)}),
    )
