"""URL routes for sign-in, sign-up, the code page and the account."""
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # the two doors
    path('login/',  views.login_view,  name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),

    # account pages
    path('account/', views.account, name='account'),
    path('account/orders/', views.account_orders, name='account_orders'),
    path('account/settings/', views.account_settings, name='account_settings'),

    # the code page, which both doors lead to
    path('verify-phone/', views.verify_phone, name='verify_phone'),
    path('verify-phone/resend/', views.resend_otp, name='resend_otp'),
    path('verify-phone/cancel/', views.cancel_verification, name='cancel_verification'),
    path('verify-phone/expire/', views.expire_verification, name='expire_verification'),

    # Password pages from before sign-in by code (§17 #309). A URL name never
    # stops resolving, so each of these still does, and leads to sign-in.
    path('account/forgot-password/', views.retired, name='account_forgot_password'),
    path('parolni-tiklash/', views.retired, name='password_reset_request'),
    path('parolni-tiklash/kod/', views.retired, name='password_reset_verify'),
    path('parolni-tiklash/kod/qayta/', views.retired, name='password_reset_resend'),
    path('parolni-tiklash/kod/tugadi/', views.retired, name='password_reset_expire'),
    path('parolni-tiklash/yangi/', views.retired, name='password_reset_set'),
]
