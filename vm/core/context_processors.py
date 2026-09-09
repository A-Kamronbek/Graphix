"""Template context shared by every page's chrome."""
from django.conf import settings
from django.urls import translate_url
from django.utils.translation import get_language


def languages(request):
    """Expose the language list, each with the URL of the *current* page in it.

    Powers both the language switcher and the ``hreflang`` alternates, so the two
    can never disagree about where a language lives. ``translate_url`` rewrites
    the prefix on the current path, which keeps a visitor on the page they were
    reading instead of dropping them on the home page.
    """
    active = get_language()
    path = request.get_full_path()

    items = []
    for code, name in settings.LANGUAGES:
        try:
            url = translate_url(path, code)
        except Exception:
            # translate_url raises on a path the URLconf can't resolve — a 404,
            # or the admin. Falling back to the site root keeps the switcher
            # usable instead of 500ing the page it is rendered on.
            url = '/' if code == settings.LANGUAGE_CODE else f'/{code}/'
        items.append({
            'code': code,
            'name': name,
            'url': url,
            'is_active': code == active,
        })

    return {'languages': items, 'active_language': active}
