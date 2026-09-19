"""Template context shared by every page's chrome."""
import os

from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.urls import translate_url
from django.utils.translation import get_language

from . import seo as seo_module

SIZE_GUIDE_IMAGE = 'img/size_guide.png'

#: The drawn guide's pixel size, remembered against the file's modification
#: time. Reading it costs a file open, the product page renders the chart on
#: every request, and the owner may still drop a new picture in without a
#: restart (§17 #69) - the stat call is what keeps both true.
_GUIDE_SIZE = {}


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


def size_guide_image():
    """``(url, (width, height))`` for the drawn size guide, or ``(None, None)``.

    One lookup for the three places that need it - the product page's hidden
    chart, the standalone page and this module - so they cannot show different
    files or different sizes (§17 #111).
    """
    path = finders.find(SIZE_GUIDE_IMAGE)
    if not path:
        return None, None
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return None, None
    cached = _GUIDE_SIZE.get(path)
    if not cached or cached[0] != stamp:
        from product import images
        cached = (stamp, images.measure_path(path))
        _GUIDE_SIZE[path] = cached
    return static(SIZE_GUIDE_IMAGE), cached[1]


def has_size_guide():
    """Is there a size guide at all - a drawn one, or structured rows?

    The page, the footer link, the product page's link and the sitemap all ask
    this one question, so none of them can advertise a guide another one 404s.
    """
    if finders.find(SIZE_GUIDE_IMAGE):
        return True
    # Imported here rather than at module scope: this module is loaded while the
    # app registry is still being populated.
    from product.models import SizeChart
    return SizeChart.objects.exists()


def seo(request):
    """The canonical URL and the language alternates for this page.

    A context processor rather than a tag, because every page needs them and
    none of them should have to remember. The 500 page renders with no context
    at all (§17 #66), so base.html prints each of these only if it is there.
    """
    # Carried even on the 500 page, which renders with no request at all
    # (§17 #66): a pre-launch site should not become indexable by erroring.
    indexable = {'site_indexable': settings.SITE_INDEXABLE}
    if request is None or not hasattr(request, 'path'):
        return indexable
    rows = seo_module.alternates(request)
    active = get_language() or settings.LANGUAGE_CODE
    return {
        **indexable,
        'canonical_url': seo_module.canonical(request),
        'seo_alternates': rows,
        'seo_default_url': seo_module.default_url(request),
        # Open Graph wants a locale, not a language: `uz`, which is what the
        # `lang` attribute carries, is not one.
        'og_locale': seo_module.OG_LOCALES.get(active, 'uz_UZ'),
        'og_locale_alternates': [seo_module.OG_LOCALES[row['code']] for row in rows
                                 if row['code'] != active
                                 and row['code'] in seo_module.OG_LOCALES],
    }


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
    ``collectstatic``. The owner drops the file in and the site picks it up
    without a restart.

    The URL and the picture's size come with it, so the product page and the
    standalone page no longer each work them out (§9 Phase 9 item 4 wants a
    ``width`` and a ``height`` on every image, and an image the template is
    handed as a bare URL has neither).
    """
    url, size = size_guide_image()
    return {
        'has_size_guide': bool(url) or has_size_guide(),
        'size_guide_image': url,
        'size_guide_size': size or ('', ''),
    }


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
