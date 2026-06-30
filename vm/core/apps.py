"""App config for the core app."""
from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Configuration for the core app (site pages, contact, SMS, rate limiting)."""
    name = 'core'
