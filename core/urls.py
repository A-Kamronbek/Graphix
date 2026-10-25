"""Public site routes: home, about, contact, one's own design, delivery, the
size guide, and the legal documents."""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    # Suggesting one's own design (§9 Phase 23 part E).
    path('oz-dizayn/', views.custom_design, name='custom_design'),
    path('yetkazib-berish/', views.delivery, name='delivery'),
    path('olcham-jadvali/', views.size_guide, name='size_guide'),
    path('terms/', views.terms, name='terms'),
    path('privacy/', views.privacy, name='privacy'),
    # The returns policy (§9 Phase 23 part A); the request page beside it is
    # the payment app's, at qaytarish/ariza/.
    path('qaytarish/', views.returns_policy, name='returns'),

    # Staff-only design-system reference, under /boshqaruv/ like the rest of
    # the panel (panel/urls.py), where Phase 2 put it before the panel existed.
    path('boshqaruv/style/', views.style_guide, name='style_guide'),
]
