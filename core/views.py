"""Static pages (home, about), the legal documents, the contact form, the
staff style guide, the two paths browsers ask for on their own, and error
handlers."""
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpResponse
from django.template.loader import select_template
from django.utils import translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import get_language, gettext as _
from django.shortcuts import render, redirect
from django.contrib import messages
from django.urls import Resolver404, resolve, reverse
from product.models import Product, Category
from django.templatetags.static import static
from . import legal, seo, telegram
from .models import Msg
from .ratelimit import is_rate_limited, is_currently_limited, RATE_LIMIT_MESSAGE


# ---------- legal documents ----------

def _back_url(request, key):
    """Where "Orqaga" leads: the page the visitor came from, if it is ours.

    The signup form links here and keeps its draft in the tab, so going back
    to it is the point. A referrer on another site, a path that is not a page,
    or the document itself is not somewhere to send anybody back to.

    "The document itself" means in any language. The switcher is a plain link,
    so a visitor who reads the terms in Uzbek and switches to Russian arrives
    with the Uzbek terms as the referrer - and a text match against the
    Russian path let "Назад" lead to the Uzbek copy of the page they were on
    (§17 #212). The referrer is resolved instead, in its own language, since
    a prefixed path only resolves while its language is active.
    """
    ref = request.META.get('HTTP_REFERER') or ''
    if ref and url_has_allowed_host_and_scheme(
            ref, allowed_hosts={request.get_host()},
            require_https=request.is_secure()):
        path = urlsplit(ref).path
        language = translation.get_language_from_path(path) or get_language()
        try:
            with translation.override(language):
                match = resolve(path)
        except Resolver404:
            match = None
        if match is not None and match.view_name != key:
            return ref
    return reverse('home')


def _legal_page(request, key, **extra):
    """Render one of the three legal documents in the reader's language.

    Each document is written out whole, once per language, in
    ``templates/legal/<key>.<lang>.html`` (§17 #182). A legal text is read -
    and reviewed - as one piece, while a .po file cuts it into fragments
    that fall back to Uzbek one at a time whenever the source wording
    changes. The Uzbek text is the authoritative one, because the
    E-commerce Law wants contract terms in the state language, and it
    stands in if a translation is ever missing.

    The body is rendered first so the contents list can be read out of it
    rather than written a second time beside it.
    """
    lang = get_language() or settings.LANGUAGE_CODE
    body = select_template([f'legal/{key}.{lang}.html', f'legal/{key}.uz.html'])
    context = {
        'doc_key': key,
        'doc_title': legal.TITLES[key],
        'doc_description': DOC_DESCRIPTIONS.get(key, ''),
        'back_url': _back_url(request, key),
        **legal.document(key),
        **extra,
    }
    html = body.render(context, request)
    context.update(body_html=html, toc=legal.contents(html))
    return render(request, 'legal/document.html', context)


#: What each document is, in one sentence, for the search result and the share
#: card. Not the document's own first line: that is a legal sentence, and a
#: result page is read by somebody deciding whether to open it at all.
DOC_DESCRIPTIONS = {
    'terms': _('GRAPHIX ommaviy ofertasi: buyurtma, toʻlov, yetkazib berish, '
               'qaytarish va almashtirish shartlari.'),
    'privacy': _('GRAPHIX maxfiylik siyosati: qanday maʼlumotlar yigʻiladi, '
                 'nima uchun va qancha muddat saqlanadi.'),
    'delivery': _('Oʻzbekiston boʻylab yetkazib berish: pochta boʻlimiga yoki '
                  'eshikkacha — muddatlar, narxlar va qaytarish tartibi.'),
}


def terms(request):
    """Terms of use and the public offer (plan §9 Phase 8 item 2).

    The payment methods are the rows the checkout offers, for the reason the
    delivery prices are (§17 #111): a terms page promising a method the
    checkout does not take is worse than a wrong number.
    """
    from payment.models import PaymentOption
    return _legal_page(request, 'terms', payment_options=list(
        PaymentOption.objects.filter(is_active=True)))


def privacy(request):
    """The privacy policy (plan §9 Phase 8 item 1)."""
    return _legal_page(request, 'privacy')


def delivery(request):
    """Delivery and returns, in plain language (plan §9 Phase 8 item 3).

    §7 requires the two tiers to be stated everywhere a customer might look.
    The figures come from the DeliveryOption rows rather than being written
    as copy: they are rows precisely so a price change is not a deploy
    (§17 #13), and a page that states the old number is how that promise
    breaks (§18 #18). Before the rows are seeded the table does not render
    and the prose still reads.
    """
    from payment.models import DeliveryOption
    return _legal_page(request, 'delivery', delivery_options=list(
        DeliveryOption.objects.filter(is_active=True)))


def home(request):
    """Render the home page.

    A product row has to be at least partly visible at 390 x 844 without
    scrolling (§17 #29), so the hero is height-capped in CSS and the newest
    designs sit immediately under it. Three short queries, all annotated the same
    way the shop annotates, so the cards render identically wherever they appear.
    """
    from product.views import annotate_cards

    live = Product.objects.filter(is_active=True, variants__available=True)

    newest = annotate_cards(live.prefetch_related('images', 'variants'),
                            user=request.user).distinct()
    # One query for both, because they are the same query: the hero is the
    # newest design and so is the first card. Asking twice cost a second round
    # trip and a second prefetch for a row already in hand.
    latest = list(newest.order_by('-created_at')[:8])
    return render(request, 'core/home.html', {
        # The hero photograph is the newest design, so the page leads with stock
        # that is actually for sale rather than a fixed marketing image.
        'featured': latest[0] if latest else None,
        'newest': latest,
        # "Siz uchun" is most-liked until Phase 13 replaces it with the real
        # recommender — the plan's own stand-in, not a placeholder.
        'popular': list(newest.filter(likes_count__gt=0).order_by('-likes_count')[:4]),
        'categories': Category.objects.all()[:6],
        # The shop itself, and the search box a result may carry. Only on the
        # home page: an Organization repeated on forty pages is the same fact
        # forty times, and this is the page a search engine treats as the site.
        'jsonld': seo.payload(seo.organisation(request), seo.website(request)),
    })


def size_guide(request):
    """Standalone size guide, for search engines and the footer (plan §9 6a).

    The guide is whatever exists: the owner's image at
    ``static/img/size_guide.png``, plus any structured ``SizeChart`` rows once
    Phase 6 seeds them. If neither exists there is no size guide, and this 404s
    rather than rendering a page that apologises for being empty - the footer
    and product-page links are hidden in the same state, so a visitor never
    learns that something is missing (owner's call, plan §17 #69).

    The modal on the product page is Phase 6a; this page is its indexable twin.
    """
    from product.models import SizeChart
    from .context_processors import size_guide_image
    charts = list(SizeChart.objects.prefetch_related('rows__size'))
    url, _size = size_guide_image()
    if not charts and not url:
        raise Http404('no size guide has been uploaded yet')
    # The picture and its dimensions come from the context processor, which is
    # the one place that looks it up (§17 #111).
    return render(request, 'core/size_guide.html', {'charts': charts})


def about(request):
    """Render the about page."""
    return render(request, 'core/about.html')

#: The contact subject's column length, so the form and the check use one number.
SUBJECT_MAX = Msg._meta.get_field('topic').max_length


def contact(request):
    """Show and handle the contact form, storing submissions as :class:`Msg`.

    Viewing is open to everyone; sending a message requires an account. An
    anonymous POST is bounced to login and returned here afterwards, so Msg.user
    always stays a real user (no nullable-FK migration needed)."""
    form_data = {}
    form_errors = False
    if request.method == 'POST':
        # Anyone can view the page, but only logged-in users can send.
        if not request.user.is_authenticated:
            return redirect(f"{reverse('login')}?next={reverse('contact')}")
        if is_rate_limited(request, 'contact', 10, 3600, ident=f"u{request.user.pk}"):
            messages.error(request, RATE_LIMIT_MESSAGE)
            form_errors = True
        else:
            form_data = {
                'subject': request.POST.get('subject', '').strip(),
                'message': request.POST.get('message', '').strip(),
            }
            if not form_data['message'] or not form_data['subject']:
                form_errors = True
                messages.error(request, _("Iltimos, xabar kiriting."))
            elif len(form_data['subject']) > SUBJECT_MAX:
                # The column's limit, said as a sentence rather than met as a
                # 500 from the database (§17 #154).
                form_errors = True
                messages.error(request, _("Mavzu %(n)d belgidan oshmasligi kerak.")
                               % {'n': SUBJECT_MAX})
            else:
                msg = Msg.objects.create(user=request.user,
                                         phone_num=request.user.phone,
                                         topic=form_data['subject'],
                                         msg_text=form_data['message'])
                # Straight to the owner's phone, with the number ready to tap.
                # Fails silently and never breaks the page (§17 #17).
                telegram.notify_message(msg)
                messages.success(request, _("Xabar qabul qilindi."))
                form_data = {}
    return render(request, 'core/contact.html', {
        'subject_max': SUBJECT_MAX,
        'form_data': form_data,
        'form_errors': form_errors,
        'rate_limited': (request.user.is_authenticated and
                         is_currently_limited(request, 'contact', 10, ident=f"u{request.user.pk}")),
    })


# ---------- design system ----------

# The palette, listed once here so the style guide and tokens.css cannot drift
# apart silently: if a token is added to tokens.css it has to be added here to
# appear on the page, which is the prompt to check its contrast.
STYLE_SWATCHES = [
    ('--c-bg', '#100E0C'), ('--c-surface', '#17140F'), ('--c-surface-2', '#211C15'),
    ('--c-surface-3', '#2A241B'), ('--c-fg', '#EFE9DE'), ('--c-fg-muted', '#B0A697'),
    ('--c-fg-subtle', '#7D7466'), ('--c-fg-hint', '#958A79'),
    ('--c-line', '#2C2620'), ('--c-line-strong', '#453D31'),
    ('--c-brand', '#C6A44E'), ('--c-brand-hover', '#D6B662'), ('--c-brand-fg', '#171205'),
    ('--c-success', '#86BE72'), ('--c-warning', '#D9A441'), ('--c-danger', '#E07A62'),
    ('--c-info', '#8AB4CE'),
]

STYLE_ICONS = [
    'mark', 'search', 'heart', 'cart', 'user', 'share', 'menu', 'close', 'check',
    'minus', 'plus', 'chevron-down', 'chevron-right', 'arrow-left', 'arrow-right',
    'star', 'filter', 'sort', 'truck', 'box', 'pin', 'phone', 'mail', 'telegram', 'info',
    'warning', 'image', 'trash', 'ruler', 'calendar',
]


@staff_member_required
def style_guide(request):
    """Render every component in every state — the design-system reference.

    Staff-only and ``noindex``. Standalone rather than extending ``base.html``,
    because it renders every component in every state — including ones no
    storefront page uses — so it stays a reference as the pages change.
    """
    return render(request, 'boshqaruv/style.html', {
        'swatches': STYLE_SWATCHES,
        'icons': STYLE_ICONS,
    })


# ---------- paths browsers ask for on their own ----------

def favicon(request):
    """``/favicon.ico``: the icon, for the clients that ask for it there.

    Every page names its icons in ``<head>``, but a browser still requests the
    root path when it opens something that is not a page - a PDF, an image -
    and some ask regardless. That was a 404 in the log on every visit
    (§17 #213). Resolved per request, so it follows ``STATIC_URL`` and any
    hashed file name rather than baking one in at import.
    """
    return redirect(static('img/favicon.ico'), permanent=True)


def devtools_probe(request):
    """Chrome's DevTools asking whether this site is a local workspace.

    Development only (see ``config/urls.py``). DevTools requests
    ``/.well-known/appspecific/com.chrome.devtools.json`` whenever it is open,
    and the answer that means "no" is an empty one: 204 says it without a
    "Not Found" warning in the runserver log on every reload (§17 #213).
    """
    return HttpResponse(status=204)


# error handlers
def handler404(request, exception):
    """Render the custom 404 page."""
    return render(request, '404.html', status=404)


def handler500(request):
    """Render the custom 500 page."""
    return render(request, '500.html', status=500)
