"""WSGI entry point for the ValleyMade project (used by gunicorn in production)."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vm.settings')

application = get_wsgi_application()
