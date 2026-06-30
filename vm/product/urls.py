"""Storefront routes: shop listing and product detail."""
from django.urls import path
from . import views

urlpatterns = [
    path('shop/', views.shop, name='shop'),
    path('item/<int:pk>/', views.item, name='item'),
]
