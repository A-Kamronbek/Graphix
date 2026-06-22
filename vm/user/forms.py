from django import forms
from .models import User, phone_regex, normalize_uz_phone
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, SetPasswordForm
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import MinimumLengthValidator


# settings
# forget password

class LoginForm(AuthenticationForm):
    error_messages = {
        'invalid_login': "Foydalanuvchi nomi yoki parol noto'g'ri.",
        'inactive': "Bu hisob faol emas.",
    }


class OTPForm(forms.Form):
    code = forms.CharField(
        min_length=6,
        max_length=6,
        validators=[RegexValidator(regex=r'^\d{6}$', message="6 ta raqam kiriting.")],
        error_messages={'required': "Kodni kiriting."},
    )


class ForgotPasswordForm(forms.Form):
    """Phone-entry step of the password reset. Normalizes then validates the
    number so '+998-90-...' style input is accepted the same way as signup."""
    phone = forms.CharField(
        max_length=20,
        error_messages={'required': "Telefon raqamni kiriting."},
    )

    def clean_phone(self):
        value = normalize_uz_phone(self.cleaned_data['phone'])
        phone_regex(value)  # raises ValidationError with the +998 format message
        return value


class ResetPasswordForm(SetPasswordForm):
    """SetPasswordForm with Uzbek labels. Inherits the password-match check and
    runs AUTH_PASSWORD_VALIDATORS (incl. CustomMinimumLengthValidator)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['new_password1'].label = "Yangi parol"
        self.fields['new_password2'].label = "Yangi parolni qayta kiriting"
        self.error_messages['password_mismatch'] = "Parollar mos kelmadi."


class SignupForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, required=False)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'phone')

    error_messages = {
        'password_mismatch': "Parollar mos kelmadi.",
    }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get('first_name', '')
        if commit:
            user.save()
        return user

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['username'].max_length = 50
        self.fields['username'].help_text = "Maximum 50ta belgi. Harflar, raqamlar va _"
        self.fields['username'].validators.append(
            RegexValidator(
                regex=r'^[A-Za-z0-9_]+$',
                message="Harflar, raqamlar va _  mumkin"
            )
        )


class CustomMinimumLengthValidator(MinimumLengthValidator):

    def validate(self, password, user=None):
        if len(password) < self.min_length:
            raise ValidationError(
                "Parol 8 belgidan kam bo'lmasligi kerak.",
                code='password_too_short',
            )

    def get_help_text(self):
        return "Parol 8 belgidan kam bo'lmasligi kerak."
