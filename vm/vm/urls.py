"""URL configuration for vm project."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # core: home, about, contact
    path('', include('core.urls')),

    # auth: login, signup, logout, account
    path('', include('user.urls')),

    # shop, item
    path('', include('product.urls')),

    # cart, add/update/remove
    path('cart/', include('cart.urls')),

    # checkout, payment, status, order
    path('', include('payment.urls')),
]

# serve media in dev
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / 'static')

# custom error handlers (Django will use templates/404.html, templates/500.html automatically when DEBUG=False)
handler404 = 'core.views.handler404'
handler500 = 'core.views.handler500'
