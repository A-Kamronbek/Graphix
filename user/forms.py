"""Auth and account forms: login, signup, OTP, password reset, profile."""
from django import forms
from django.utils.translation import gettext_lazy as _
from .models import User, phone_regex, normalize_uz_phone
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, SetPasswordForm, PasswordChangeForm
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from core import legal


# Allowed username characters: letters, digits, underscore.
USERNAME_REGEX = RegexValidator(regex=r'^[A-Za-z0-9_]+$', message=_("Harflar, raqamlar va _ mumkin"))


class LoginForm(AuthenticationForm):
    """Login form with Uzbek error messages."""
    error_messages = {
        'invalid_login': _("Foydalanuvchi nomi yoki parol notoʻgʻri."),
        'inactive': _("Bu hisob faol emas."),
    }


class OTPForm(forms.Form):
    """Six-digit OTP entry."""
    code = forms.CharField(
        validators=[RegexValidator(regex=r'^\d{6}$', message=_("6 ta raqam kiriting."))],
        error_messages={'required': _("Kodni kiriting.")},
    )


class ForgotPasswordForm(forms.Form):
    """Phone-number entry that starts a password reset."""
    phone = forms.CharField(
        max_length=20,
        error_messages={'required': _("Telefon raqamni kiriting.")},
    )

    def clean_phone(self):
        """Normalise then validate the phone number."""
        value = normalize_uz_phone(self.cleaned_data['phone'])
        phone_regex(value)
        return value


class ResetPasswordForm(SetPasswordForm):
    """New-password form shown once the reset code is verified."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['new_password1'].label = _("Yangi parol")
        self.fields['new_password2'].label = _("Yangi parolni qayta kiriting")
        self.error_messages['password_mismatch'] = _("Parollar mos kelmadi.")


class ProfileForm(forms.ModelForm):
    """Edit display name and username on the account page."""
    class Meta:
        model = User
        fields = ('first_name', 'username')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = False
        self.fields['first_name'].label = _("Ism")
        self.fields['username'].label = _("Foydalanuvchi nomi")
        self.fields['username'].max_length = 50
        self.fields['username'].validators.append(USERNAME_REGEX)

    def clean_username(self):
        """Reject a username already taken by another user."""
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exclude(pk=self.instance.pk).exists():
            raise ValidationError(_("Bu foydalanuvchi nomi band."))
        return username


class ChangePasswordForm(PasswordChangeForm):
    """Change-password form with Uzbek labels and messages."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].label = _("Joriy parol")
        self.fields['new_password1'].label = _("Yangi parol")
        self.fields['new_password2'].label = _("Yangi parolni qayta kiriting")
        self.error_messages['password_incorrect'] = _("Joriy parol notoʻgʻri.")
        self.error_messages['password_mismatch'] = _("Parollar mos kelmadi.")


class SignupForm(UserCreationForm):
    """Registration form; creates the User and triggers phone verification."""
    first_name = forms.CharField(max_length=150, required=False)
    # Deliberately not required. The browser already refuses the form without
    # the box, and making the server refuse it too would change what an
    # existing endpoint does to a request that succeeds today (§18 #47). What
    # this field is for is the record: the versions are stamped only when the
    # box actually came back ticked, so the columns never claim a consent
    # nobody gave.
    agree = forms.BooleanField(required=False)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'phone')

    error_messages = {
        'password_mismatch': _("Parollar mos kelmadi."),
    }

    def save(self, commit=True):
        """Save the user, with the optional first name and the consent given.

        The signup page shows the terms and the privacy policy beside the box;
        which wording each of them had is stamped here, where the box is read,
        so the record and the thing recorded cannot drift apart (§17 #272).
        """
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get('first_name', '')
        if self.cleaned_data.get('agree'):
            for field, number in legal.accepted_versions().items():
                setattr(user, field, number)
        if commit:
            user.save()
        return user

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['username'].max_length = 50
        self.fields['username'].help_text = _("Koʻpi bilan 50 ta belgi. Harflar, raqamlar va _")
        self.fields['username'].validators.append(USERNAME_REGEX)

    def clean_phone(self):
        """Normalise, validate, and reject an already-registered phone.

        Normalising before the uniqueness check stops a differently-spaced
        duplicate from slipping through and raising an IntegrityError later.
        """
        value = normalize_uz_phone(self.cleaned_data['phone'])
        phone_regex(value)
        if User.objects.filter(phone=value).exists():
            raise ValidationError(_("Bu raqam roʻyxatdan oʻtgan."))
        return value
