"""Catalogue context shared by the site chrome (currently the footer's shop links)."""
from .models import Category


def nav_categories(request):
    """Expose the real categories so the footer can link to ones that exist.

    The footer used to link to hardcoded ``?category=tops|bottoms|outer`` values,
    which ``shop()`` silently ignored because it filters on ``category_id``. Those
    three links returned the whole catalogue. Rendering the actual rows keeps the
    links correct as categories are added or renamed.
    """
    return {'nav_categories': Category.objects.all()}
