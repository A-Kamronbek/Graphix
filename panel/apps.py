"""App config for the staff panel.

Almost all of the panel is views over models the rest of the site already
owns; the one table of its own is ``OrderStatusChange``, which exists for the
panel's sake and which payment does not read. It is a separate app because a
screen that edits products, orders, reviews and regions belongs to none of
those apps, and putting it in any one of them would make that app import the
other three.
"""
from django.apps import AppConfig


class PanelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'panel'
    verbose_name = 'Boshqaruv paneli'
