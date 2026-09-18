"""App config for the payment app."""
from django.apps import AppConfig


class PaymentConfig(AppConfig):
    """Configuration for the payment app (checkout, orders, Click integration)."""
    name = 'payment'
