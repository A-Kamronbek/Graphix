from django.shortcuts import render
from django.contrib import messages
from product.models import Product, Category
from .models import msg


def home(request):
    return render(request, 'core/home.html')


def about(request):
    return render(request, 'core/about.html')


def contact(request):
    form_data = {}
    form_errors = False
    if request.method == 'POST':
        form_data = {
            'subject': request.POST.get('subject', '').strip(),
            'message': request.POST.get('message', '').strip(),
        }
        if not form_data['message'] or not form_data['subject']:
            form_errors = True
            messages.error(request, "Iltimos habar kiriting.")
        else:
            msg.objects.create(user=request.user,
                               phone_num=request.user.phone,
                               topic=form_data['subject'],
                               msg_text=form_data['message'])
            messages.success(request, "Habar qabul qilindi.")
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
