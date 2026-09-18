"""App config for the product app."""
from django.apps import AppConfig


class ProductConfig(AppConfig):
    """Configuration for the product (catalog) app."""
    name = 'product'

    def ready(self):
        """Connect the catalogue's signal receivers.

        Imported for the side effect of registering them, which is what
        ``ready()`` is for. Kept to one line so it is obvious that adding a
        receiver means editing ``product/signals.py``, not this file.
        """
        from . import signals  # noqa: F401
