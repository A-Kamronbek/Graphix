"""Auth and account forms: login, signup, OTP, password reset, profile."""
from django import forms
from .models import User, phone_regex, normalize_uz_phone
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, SetPasswordForm, PasswordChangeForm
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError


# Allowed username characters: letters, digits, underscore.
USERNAME_REGEX = RegexValidator(regex=r'^[A-Za-z0-9_]+$', message="Harflar, raqamlar va _  mumkin")


class LoginForm(AuthenticationForm):
    """Login form with Uzbek error messages."""
    error_messages = {
        'invalid_login': "Foydalanuvchi nomi yoki parol noto'g'ri.",
        'inactive': "Bu hisob faol emas.",
    }


class OTPForm(forms.Form):
    """Six-digit OTP entry."""
    code = forms.CharField(
        validators=[RegexValidator(regex=r'^\d{6}$', message="6 ta raqam kiriting.")],
        error_messages={'required': "Kodni kiriting."},
    )


class ForgotPasswordForm(forms.Form):
    """Phone-number entry that starts a password reset."""
    phone = forms.CharField(
        max_length=20,
        error_messages={'required': "Telefon raqamni kiriting."},
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
        self.fields['new_password1'].label = "Yangi parol"
        self.fields['new_password2'].label = "Yangi parolni qayta kiriting"
        self.error_messages['password_mismatch'] = "Parollar mos kelmadi."


class ProfileForm(forms.ModelForm):
    """Edit display name and username on the account page."""
    class Meta:
        model = User
        fields = ('first_name', 'username')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = False
        self.fields['first_name'].label = "Ism"
        self.fields['username'].label = "Foydalanuvchi nomi"
        self.fields['username'].max_length = 50
        self.fields['username'].validators.append(USERNAME_REGEX)

    def clean_username(self):
        """Reject a username already taken by another user."""
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Bu foydalanuvchi nomi band.")
        return username


class ChangePasswordForm(PasswordChangeForm):
    """Change-password form with Uzbek labels and messages."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].label = "Joriy parol"
        self.fields['new_password1'].label = "Yangi parol"
        self.fields['new_password2'].label = "Yangi parolni qayta kiriting"
        self.error_messages['password_incorrect'] = "Joriy parol noto'g'ri."
        self.error_messages['password_mismatch'] = "Parollar mos kelmadi."


class SignupForm(UserCreationForm):
    """Registration form; creates the User and triggers phone verification."""
    first_name = forms.CharField(max_length=150, required=False)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'phone')

    error_messages = {
        'password_mismatch': "Parollar mos kelmadi.",
    }

    def save(self, commit=True):
        """Save the user, copying the optional first name."""
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get('first_name', '')
        if commit:
            user.save()
        return user

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['username'].max_length = 50
        self.fields['username'].help_text = "Maximum 50ta belgi. Harflar, raqamlar va _"
        self.fields['username'].validators.append(USERNAME_REGEX)

    def clean_phone(self):
        """Normalise, validate, and reject an already-registered phone.

        Normalising before the uniqueness check stops a differently-spaced
        duplicate from slipping through and raising an IntegrityError later.
        """
        value = normalize_uz_phone(self.cleaned_data['phone'])
        phone_regex(value)
        if User.objects.filter(phone=value).exists():
            raise ValidationError("Bu raqam ro'yxatdan o'tgan.")
        return value
