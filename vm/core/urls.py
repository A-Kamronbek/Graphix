"""Public site routes: home, about, contact, delivery, size guide, and the
two legal documents."""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('yetkazib-berish/', views.delivery, name='delivery'),
    path('olcham-jadvali/', views.size_guide, name='size_guide'),
    path('terms/', views.terms, name='terms'),
    path('privacy/', views.privacy, name='privacy'),

    # Staff-only design-system reference, under /boshqaruv/ like the rest of
    # the panel (panel/urls.py), where Phase 2 put it before the panel existed.
    path('boshqaruv/style/', views.style_guide, name='style_guide'),
]
