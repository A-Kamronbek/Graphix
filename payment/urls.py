"""Payment routes: checkout, Click pay link / webhook, and order views."""
from django.urls import path
from . import views

# Machine-facing. Kept in its own list because config/urls.py includes it OUTSIDE
# i18n_patterns: Click POSTs to this exact path and would 404 against /uz/, /ru/
# or /en/. Breaking it means silent payment failures (§12 risk #2), so a test
# asserts the path resolves unprefixed.
#
# Single Click callback URL — handles both Prepare and Complete; click_up routes
# by the request's action. The trailing slash matters: Click POSTs to this exact
# path, and a slash-less POST wouldn't match.
webhook_urlpatterns = [
    path("payment/click/update/", views.ClickWebhookAPIView.as_view(), name='click_webhook'),
]

# Human-facing. Translated, and therefore language-prefixed.
urlpatterns = [
    path('checkout/', views.checkout, name='checkout'),

    path('payment/<int:order_id>/',         views.payment,       name='payment'),
    path('payment/<int:order_id>/start/',   views.payment_start, name='payment_start'),

    path('order/<int:pk>/',         views.order_detail, name='order_detail'),
    path('order/<int:pk>/status/',  views.order_status, name='order_status'),
    path('order/<int:pk>/cancel/',  views.order_cancel, name='order_cancel'),
]
