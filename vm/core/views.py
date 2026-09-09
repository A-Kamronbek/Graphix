"""Static pages (home, about, terms), the contact form, the staff style guide,
and error handlers."""
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.urls import reverse
from product.models import Product, Category
from .models import Msg
from .ratelimit import is_rate_limited, is_currently_limited, RATE_LIMIT_MESSAGE


def terms(request):
    """Render the terms page, linking 'back' to the referring page when safe."""
    ref = request.META.get('HTTP_REFERER') or ''
    back_url = ref if ref and reverse('terms') not in ref else reverse('home')
    return render(request, 'terms.html', {'back_url': back_url})


def home(request):
    """Render the home page."""
    return render(request, 'core/home.html')


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
                messages.error(request, "Iltimos xabar kiriting.")
            else:
                Msg.objects.create(user=request.user,
                                   phone_num=request.user.phone,
                                   topic=form_data['subject'],
                                   msg_text=form_data['message'])
                messages.success(request, "Xabar qabul qilindi.")
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
    ('--c-fg-subtle', '#7D7466'), ('--c-line', '#2C2620'), ('--c-line-strong', '#453D31'),
    ('--c-brand', '#C6A44E'), ('--c-brand-hover', '#D6B662'), ('--c-brand-fg', '#171205'),
    ('--c-success', '#86BE72'), ('--c-warning', '#D9A441'), ('--c-danger', '#E07A62'),
    ('--c-info', '#8AB4CE'),
]

STYLE_ICONS = [
    'mark', 'search', 'heart', 'cart', 'user', 'share', 'menu', 'close', 'check',
    'minus', 'plus', 'chevron-down', 'chevron-right', 'arrow-left', 'arrow-right',
    'star', 'filter', 'sort', 'truck', 'box', 'pin', 'phone', 'telegram', 'info',
    'warning', 'image', 'trash', 'ruler',
]


@staff_member_required
def style_guide(request):
    """Render every component in every state — the design-system reference.

    Staff-only and ``noindex``. It is the first page in the project to load
    tokens/base/components; the storefront keeps running on the old ``main.css``
    until Phase 5 rebuilds the pages, so the two stylesheets never meet.
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
