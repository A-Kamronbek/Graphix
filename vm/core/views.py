"""Static pages (home, about, terms), the contact form, and error handlers."""
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


# error handlers
def handler404(request, exception):
    """Render the custom 404 page."""
    return render(request, '404.html', status=404)


def handler500(request):
    """Render the custom 500 page."""
    return render(request, '500.html', status=500)
