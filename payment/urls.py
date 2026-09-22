"""Payment routes: checkout, Click pay link / webhook, and order views."""
from django.urls import path
from . import views

# Machine-facing. Kept in its own list because config/urls.py includes it OUTSIDE
# i18n_patterns: Click POSTs to this exact path and would 404 against /uz/, /ru/
# or /en/. Breaking it means silent payment failures (§12 risk #2), so a test
# asserts the path resolves unprefixed.
#
# One callback URL per gateway, each handling every step that gateway has:
# tolov routes by the request's own action. The trailing slash matters — a
# gateway POSTs to the exact path it was given, and a slash-less POST would
# not match.
webhook_urlpatterns = [
    path("payment/click/update/", views.ClickWebhookAPIView.as_view(), name='click_webhook'),
    # Payme and Octo, Phase 14 item 5, and unprefixed for the same reason:
    # a gateway is given one address and posts to it forever. Click's path is
    # the one that must never move because Click already has it; these two are
    # new, so the shape is chosen to match rather than inherited.
    path("payment/payme/update/", views.PaymeWebhookAPIView.as_view(), name='payme_webhook'),
    path("payment/octo/update/", views.OctoWebhookAPIView.as_view(), name='octo_webhook'),
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
