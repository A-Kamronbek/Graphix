"""App config for the staff panel.

The panel has no models of its own — it is views over the models the rest of
the site already owns. It is a separate app anyway, because a screen that
edits products, orders, reviews and regions belongs to none of those apps and
putting it in any one of them would make that app import the other three.
"""
from django.apps import AppConfig


class PanelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'panel'
    verbose_name = 'Boshqaruv paneli'
