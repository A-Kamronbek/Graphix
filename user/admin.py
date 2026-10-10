"""Admin registration for the custom User model."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from . import services
from .models import User, normalize_uz_phone


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

    def save_model(self, request, obj, form, change):
        """Keep how an account is signed in to in step with what is changed here.

        This form is where a customer's number is changed when they ask the
        shop to, and the number is the account (§17 #309). Two edits would
        otherwise leave a way in that should have closed:

        * a customer's new number. The username goes with it, and every
          session ends, so whoever holds the old number or an old session is
          no longer signed in to this account;
        * a customer made staff. A session they opened with an SMS code must
          not become a staff session, so those end too, and the account is
          signed in to again with the password set for it here.
        """
        before = (User.objects.filter(pk=obj.pk).values('phone', 'is_staff', 'is_superuser').first()
                  if change else None)
        if before:
            was_staff = before['is_staff'] or before['is_superuser']
            is_staff = services.is_staff_account(obj)
            obj.phone = normalize_uz_phone(obj.phone)
            if not is_staff and obj.phone != before['phone']:
                services.rekey(obj)
            elif is_staff and not was_staff and not obj.has_usable_password():
                obj.set_unusable_password()
        super().save_model(request, obj, form, change)
