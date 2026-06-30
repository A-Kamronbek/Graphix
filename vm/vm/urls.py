"""Root URL configuration: admin, app routes, SEO files, dev media, error handlers."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.views.generic import TemplateView
from core.sitemaps import sitemaps as site_maps

urlpatterns = [
    path('admin/', admin.site.urls),

    # SEO
    path('sitemap.xml', sitemap, {'sitemaps': site_maps}, name='sitemap'),
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),

    path('', include('core.urls')),
    path('', include('user.urls')),
    path('', include('product.urls')),
    path('cart/', include('cart.urls')),
    path('', include('payment.urls')),
]

# Serve uploaded media and static files via Django only in development;
# in production nginx serves them directly.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / 'static')

handler404 = 'core.views.handler404'
handler500 = 'core.views.handler500'
