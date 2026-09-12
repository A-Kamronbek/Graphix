"""Template context shared by every page's chrome."""
from django.conf import settings
from django.contrib.staticfiles import finders
from django.urls import translate_url
from django.utils.translation import get_language

SIZE_GUIDE_IMAGE = 'img/size_guide.png'


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


def size_guide(request):
    """Whether there is a size guide to link to at all.

    The guide is one image the owner drops at ``static/img/size_guide.png``.
    Until that file exists there is no size guide, and the site says nothing
    about one: the footer link is hidden, the product page's link is hidden and
    the page itself 404s. A link to a page that apologises for being empty is
    worse than no link - the visitor learns only that something is missing.

    The lookup goes through the staticfiles finders, which is what ``{% static %}``
    uses, so it answers the same before and after ``collectstatic``. A negative
    result is deliberately not cached: the owner uploads the file and the site
    picks it up without a restart.
    """
    return {'has_size_guide': bool(finders.find(SIZE_GUIDE_IMAGE))}
