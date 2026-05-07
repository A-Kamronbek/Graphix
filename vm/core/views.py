from django.shortcuts import render
from django.contrib import messages
from product.models import Product, Category


def home(request):
    featured = (
        Product.objects
        .prefetch_related('images', 'variants')
        .order_by('-created_at')[:6]
    )
    return render(request, 'core/home.html', {
        'featured': featured,
        'categories': Category.objects.all()[:6],
    })


def about(request):
    return render(request, 'core/about.html')


def contact(request):
    form_data = {}
    form_errors = False
    if request.method == 'POST':
        form_data = {
            'name': request.POST.get('name', '').strip(),
            'email': request.POST.get('email', '').strip(),
            'subject': request.POST.get('subject', '').strip(),
            'message': request.POST.get('message', '').strip(),
        }
        if not form_data['name'] or not form_data['email'] or not form_data['message']:
            form_errors = True
            messages.error(request, "Please fill in all required fields.")
        else:
            # TODO: send email / save to a Message model
            messages.success(request, "Message sent. We'll get back to you soon.")
            form_data = {}
    return render(request, 'core/contact.html', {
        'form_data': form_data,
        'form_errors': form_errors,
    })


# error handlers
def handler404(request, exception):
    return render(request, '404.html', status=404)


def handler500(request):
    return render(request, '500.html', status=500)
