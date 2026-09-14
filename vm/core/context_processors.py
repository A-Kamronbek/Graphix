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
            # usable instead of 500ing the page it is rendered on. Every
            # language has a prefix now, Uzbek included (§17 #121).
            url = f'/{code}/'
        items.append({
            'code': code,
            'name': name,
            'url': url,
            'is_active': code == active,
        })

    return {'languages': items, 'active_language': active}


def size_guide(request):
    """Whether there is a size guide to link to at all.

    There are two ways for one to exist and either is enough: the image at
    ``static/img/size_guide.png``, which the owner can overwrite with no deploy
    (§17 #69), and the structured ``SizeChart`` rows, which Phase 6a seeds.
    Until neither exists the site says nothing about a guide at all — the footer
    link is hidden, the product page's link is hidden and the page itself 404s.
    A link to a page that apologises for being empty is worse than no link: the
    visitor learns only that something is missing.

    The image lookup goes through the staticfiles finders, which is what
    ``{% static %}`` uses, so it answers the same before and after
    ``collectstatic``. Neither result is cached: the owner drops the file in and
    the site picks it up without a restart.
    """
    if finders.find(SIZE_GUIDE_IMAGE):
        return {'has_size_guide': True}
    # Imported here rather than at module scope: this module is loaded while the
    # app registry is still being populated.
    from product.models import SizeChart
    return {'has_size_guide': SizeChart.objects.exists()}


def delivery_tiers(request):
    """The delivery tiers and their prices, for the footer on every page.

    The footer quoted them as literal text, and when §17 #85 moved the door
    price from 30 000 to 40 000 the footer kept saying 30 000 — on every page of
    the site, including the checkout page whose own form said 40 000 two
    hundred pixels above it. §18 #18 closed the product and delivery pages and
    missed this one, which is the argument for reading the rows rather than
    repeating them: a price written down twice is a price that will disagree
    with itself (§17 #111).

    Cached, because this runs on every request for something that changes when
    the owner edits a row. A short TTL is the right trade: a price change shows
    up within a minute and the footer costs no query in between.
    """
    from django.core.cache import cache
    tiers = cache.get('delivery_tiers')
    if tiers is None:
        from payment.models import DeliveryOption
        tiers = list(DeliveryOption.objects.filter(is_active=True))
        cache.set('delivery_tiers', tiers, 60)
    return {'delivery_tiers': tiers}
