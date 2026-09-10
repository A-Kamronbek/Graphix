"""Storefront routes: shop listing and product detail."""
from django.urls import path
from . import views

urlpatterns = [
    path('shop/', views.shop, name='shop'),
    path('mahsulot/<slug:slug>/', views.item, name='item'),
    # The old integer URL keeps working with a 301: links, bookmarks and search
    # results pointing at /item/<pk>/ exist in the wild. The URL *name* 'item'
    # stays on the canonical slug route (plan §4).
    path('item/<int:pk>/', views.item_legacy_redirect, name='item_legacy'),
]
