from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('login/',  views.login_view,  name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    
    path('account/', views.account, name='account'),
    path('account/orders/', views.account_orders, name='account_orders'),

    path('verify-phone/', views.verify_phone, name='verify_phone'),
    path('verify-phone/resend/', views.resend_otp, name='resend_otp'),
    path('verify-phone/cancel/', views.cancel_verification, name='cancel_verification'),
    path('verify-phone/expire/', views.expire_verification, name='expire_verification'),
    # settings
    # forget password
]
