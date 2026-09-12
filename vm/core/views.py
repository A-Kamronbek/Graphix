"""Static pages (home, about, terms), the contact form, the staff style guide,
and error handlers."""
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.staticfiles import finders
from django.http import Http404
from django.utils.translation import gettext as _
from django.shortcuts import render, redirect
from django.contrib import messages
from django.urls import reverse
from product.models import Product, Category
from django.templatetags.static import static
from core.context_processors import SIZE_GUIDE_IMAGE
from .models import Msg
from .ratelimit import is_rate_limited, is_currently_limited, RATE_LIMIT_MESSAGE


def terms(request):
    """Render the terms page, linking 'back' to the referring page when safe."""
    ref = request.META.get('HTTP_REFERER') or ''
    back_url = ref if ref and reverse('terms') not in ref else reverse('home')
    return render(request, 'terms.html', {'back_url': back_url})


def home(request):
    """Render the home page.

    A product row has to be at least partly visible at 390 x 844 without
    scrolling (§17 #29), so the hero is height-capped in CSS and the newest
    designs sit immediately under it. Three short queries, all annotated the same
    way the shop annotates, so the cards render identically wherever they appear.
    """
    from product.views import annotate_cards

    live = Product.objects.filter(is_active=True, variants__available=True)

    newest = annotate_cards(live.prefetch_related('images', 'variants')).distinct()
    return render(request, 'core/home.html', {
        # The hero photograph is the newest design, so the page leads with stock
        # that is actually for sale rather than a fixed marketing image.
        'featured': newest.order_by('-created_at').first(),
        'newest': list(newest.order_by('-created_at')[:8]),
        # "Siz uchun" is most-liked until Phase 13 replaces it with the real
        # recommender — the plan's own stand-in, not a placeholder.
        'popular': list(newest.filter(likes_count__gt=0).order_by('-likes_count')[:4]),
        'categories': Category.objects.all()[:6],
    })


def delivery(request):
    """Delivery terms as their own page.

    §7 requires the two tiers to be stated everywhere a customer might look —
    checkout, the confirmation, this page and the terms — so nobody is surprised
    at checkout about who delivers or what it costs. The prices live in
    DeliveryOption rows, but this page states them as copy: it has to read
    correctly even before the rows are seeded on a fresh deploy.
    """
    return render(request, 'core/delivery.html')


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
    charts = list(SizeChart.objects.prefetch_related('rows__size'))
    image = finders.find(SIZE_GUIDE_IMAGE) and static(SIZE_GUIDE_IMAGE)
    if not charts and not image:
        raise Http404('no size guide has been uploaded yet')
    return render(request, 'core/size_guide.html', {
        'charts': charts,
        'size_guide_image': image,
    })


def about(request):
    """Render the about page."""
    return render(request, 'core/about.html')

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
            else:
                Msg.objects.create(user=request.user,
                                   phone_num=request.user.phone,
                                   topic=form_data['subject'],
                                   msg_text=form_data['message'])
                messages.success(request, _("Xabar qabul qilindi."))
                form_data = {}
    return render(request, 'core/contact.html', {
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
    'warning', 'image', 'trash', 'ruler',
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


# error handlers
def handler404(request, exception):
    """Render the custom 404 page."""
    return render(request, '404.html', status=404)


def handler500(request):
    """Render the custom 500 page."""
    return render(request, '500.html', status=500)
