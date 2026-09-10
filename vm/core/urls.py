"""Public site routes: home, about, contact, delivery, size guide, terms."""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('yetkazib-berish/', views.delivery, name='delivery'),
    path('olcham-jadvali/', views.size_guide, name='size_guide'),
    path('terms/', views.terms, name='terms'),

    # Staff-only design-system reference. The rest of /boshqaruv/ arrives in
    # Phase 7; this is the first page under it.
    path('boshqaruv/style/', views.style_guide, name='style_guide'),
]
