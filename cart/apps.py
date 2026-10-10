"""App config for the cart app."""
from django.apps import AppConfig


class CartConfig(AppConfig):
    """Configuration for the cart app."""
    name = 'cart'

    def ready(self):
        """Connect the receiver that merges a guest cart at sign-in."""
        from . import signals  # noqa: F401
