"""What a search engine and a share card read: URLs and structured data.

Three jobs, all of them about saying the same thing in one place:

* **one address per page.** The site answers on more than one host — the bare
  domain, ``www``, and the server's own address while it is being set up — and
  a crawler that finds the same catalogue on two of them indexes neither well.
  Every canonical, alternate and share URL here is built from ``SITE_URL``.
* **one set of language alternates.** Built from the *path*, never from the full
  query string: ``?sort=popular`` is the same page in a different order, and a
  hreflang set that carries it tells Google there are as many Russian versions
  of the shop as there are ways to sort it.
* **one structured-data block per page.** Everything the page wants to say —
  the product, its offer, its reviews, the trail that leads to it — goes into
  one ``@graph`` rather than three script elements, because two ``Product``
  nodes on one page is one product described twice.
"""
import json

from django.conf import settings
from django.urls import reverse, translate_url
from django.utils.safestring import mark_safe
from django.utils.translation import get_language


#: Open Graph asks for a locale rather than a language code. Uzbek Latin in
#: Uzbekistan, Russian and the English the site is written in.
OG_LOCALES = {'uz': 'uz_UZ', 'ru': 'ru_RU', 'en': 'en_US'}


def site_base():
    """The one origin every public URL on this site is written against."""
    return (getattr(settings, 'SITE_URL', '') or '').rstrip('/')


def absolute(request, path):
    """``path`` as an absolute URL on the site's own domain.

    ``SITE_URL`` rather than the host the request came in on: that host is
    whatever the visitor typed, and a canonical whose job is to name one address
    must not repeat it back. With no ``SITE_URL`` set - a bare checkout of the
    project - the request answers instead, so nothing here depends on
    deployment to be correct.
    """
    if not path:
        path = '/'
    if path.startswith('http://') or path.startswith('https://'):
        return path
    base = site_base()
    if base:
        return base + path
    return request.build_absolute_uri(path) if request is not None else path


def canonical(request):
    """This page's canonical URL.

    The path, plus the page number when there is one. Filters and sorts are
    deliberately dropped: ``/shop/?tag=anime`` is the catalogue shown a
    particular way, not a page of its own, and every one of those combinations
    indexed separately is thin duplicate content. The page number is kept
    because page two really does hold different products.
    """
    path = request.path
    page = (request.GET.get('page') or '').strip()
    if page.isdigit() and int(page) > 1:
        path = '%s?page=%d' % (path, int(page))
    return absolute(request, path)


def alternates(request):
    """``[{'code', 'url'}, ...]`` - this page in each language, and x-default.

    The x-default is the Uzbek copy of *this* page, not the home page: it names
    the version to show a reader whose language the site does not have, and
    sending all of them to the front door throws away the page they asked for.
    """
    path = request.path
    rows = []
    for code, _name in settings.LANGUAGES:
        try:
            url = translate_url(path, code)
        except Exception:
            # Raised on a path the URLconf cannot resolve — a 404, the admin.
            # Same fallback as the language switcher (§17 #121).
            url = '/%s/' % code
        rows.append({'code': code, 'url': absolute(request, url)})
    return rows


def default_url(request):
    """The x-default alternate: this page in Uzbek."""
    for row in alternates(request):
        if row['code'] == settings.LANGUAGE_CODE:
            return row['url']
    return absolute(request, '/')


def payload(*nodes):
    """The nodes as one ``@graph``, ready to print inside a script element.

    ``<`` is escaped for the same reason it is everywhere else on this site: a
    product name or a review is somebody's text, and ``</script>`` inside a
    JSON string would end the element early and turn it into markup. A JSON
    reader unescapes it transparently.
    """
    graph = [node for node in nodes if node]
    if not graph:
        return ''
    data = {'@context': 'https://schema.org', '@graph': graph}
    return mark_safe(json.dumps(data, ensure_ascii=False).replace('<', '\\u003c'))


def breadcrumbs(request, trail):
    """A ``BreadcrumbList`` from ``[(name, path), ...]``, in order.

    The last item is the page itself and carries no link of its own, which is
    what schema.org asks for and what the visible trail already does.
    """
    return {
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {
                '@type': 'ListItem',
                'position': position,
                'name': name,
                **({'item': absolute(request, path)} if path else {}),
            }
            for position, (name, path) in enumerate(trail, start=1)
        ],
    }


def organisation(request):
    """The shop itself: who it is, how to reach it, where else it lives.

    Read from ``core.legal`` rather than written again here - the contact card,
    the documents and this all name one phone number (§17 #111).
    """
    from django.templatetags.static import static
    from . import legal

    seller = legal.SELLER
    return {
        '@type': 'Organization',
        '@id': absolute(request, '/') + '#shop',
        'name': seller['brand'],
        'url': absolute(request, '/'),
        'logo': absolute(request, static('img/icon-512.png')),
        'email': seller['email'],
        'telephone': seller['phone'],
        'sameAs': ['https://t.me/%s' % seller['telegram']],
        'contactPoint': [{
            '@type': 'ContactPoint',
            'contactType': 'customer support',
            'telephone': seller['phone'],
            'email': seller['email'],
            'availableLanguage': ['uz', 'ru', 'en'],
        }],
    }


def website(request):
    """The site, with the search box a result page may offer.

    ``SearchAction`` describes the shop's own search endpoint. It is what lets
    a result for GRAPHIX carry a search field; Google decides whether to show
    one, and describing it costs four lines.
    """
    return {
        '@type': 'WebSite',
        '@id': absolute(request, '/') + '#site',
        'url': absolute(request, '/'),
        'name': 'GRAPHIX',
        'inLanguage': get_language() or settings.LANGUAGE_CODE,
        'publisher': {'@id': absolute(request, '/') + '#shop'},
        'potentialAction': {
            '@type': 'SearchAction',
            'target': {
                '@type': 'EntryPoint',
                'urlTemplate': absolute(request, reverse('search')) + '?q={search_term_string}',
            },
            'query-input': 'required name=search_term_string',
        },
    }
