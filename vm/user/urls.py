"""URL routes for auth, account, phone verification, and password reset."""
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # auth
    path('login/',  views.login_view,  name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),

    # account pages
    path('account/', views.account, name='account'),
    path('account/orders/', views.account_orders, name='account_orders'),
    path('account/settings/', views.account_settings, name='account_settings'),
    path('account/forgot-password/', views.account_forgot_password, name='account_forgot_password'),

    # phone verification (signup OTP)
    path('verify-phone/', views.verify_phone, name='verify_phone'),
    path('verify-phone/resend/', views.resend_otp, name='resend_otp'),
    path('verify-phone/cancel/', views.cancel_verification, name='cancel_verification'),
    path('verify-phone/expire/', views.expire_verification, name='expire_verification'),

    # password reset (OTP-based)
    path('parolni-tiklash/', views.password_reset_request, name='password_reset_request'),
    path('parolni-tiklash/kod/', views.password_reset_verify, name='password_reset_verify'),
    path('parolni-tiklash/kod/qayta/', views.password_reset_resend, name='password_reset_resend'),
    path('parolni-tiklash/kod/tugadi/', views.password_reset_expire, name='password_reset_expire'),
    path('parolni-tiklash/yangi/', views.password_reset_set, name='password_reset_set'),
]
