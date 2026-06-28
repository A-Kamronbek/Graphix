from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib import messages
from django.urls import reverse
from product.models import Product, Category
from .models import Msg
from .ratelimit import is_rate_limited, is_currently_limited, RATE_LIMIT_MESSAGE

def terms(request):
    # "Orqaga" returns to whatever page linked here (signup, footer, etc.).
    # Fall back to home on a direct visit or if the referer is terms itself.
    ref = request.META.get('HTTP_REFERER') or ''
    back_url = ref if ref and reverse('terms') not in ref else reverse('home')
    return render(request, 'terms.html', {'back_url': back_url})


def home(request):
    return render(request, 'core/home.html')


def about(request):
    return render(request, 'core/about.html')

@login_required
def contact(request):
    form_data = {}
    form_errors = False
    if request.method == 'POST':
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
        'rate_limited': is_currently_limited(request, 'contact', 10, ident=f"u{request.user.pk}"),
    })


# error handlers
def handler404(request, exception):
    return render(request, '404.html', status=404)


def handler500(request):
    return render(request, '500.html', status=500)
