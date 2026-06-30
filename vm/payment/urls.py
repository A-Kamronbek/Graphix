from django.urls import path
from . import views

urlpatterns = [
    path('checkout/', views.checkout, name='checkout'),

    path('payment/<int:order_id>/',         views.payment,       name='payment'),
    path('payment/<int:order_id>/start/',   views.payment_start, name='payment_start'),
    path("payment/click/update/",           views.ClickWebhookAPIView.as_view(), name='click_webhook'),

    path('order/<int:pk>/',         views.order_detail, name='order_detail'),
    path('order/<int:pk>/status/',  views.order_status, name='order_status'),
    path('order/<int:pk>/cancel/',  views.order_cancel, name='order_cancel'),


]
