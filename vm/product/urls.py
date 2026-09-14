"""Storefront routes: shop listing, search, saved items and product detail."""
from django.urls import path
from . import views

urlpatterns = [
    path('shop/', views.shop, name='shop'),
    path('qidiruv/', views.search, name='search'),
    path('saqlanganlar/', views.liked, name='liked'),
    path('mahsulot/<slug:slug>/', views.item, name='item'),
    # The heart. POST only, and it answers either JSON or a redirect depending
    # on what asked — so the same URL serves the fetch and the plain form.
    path('mahsulot/<slug:slug>/saqlash/', views.like_toggle, name='product_like'),
    # The old integer URL keeps working with a 301: links, bookmarks and search
    # results pointing at /item/<pk>/ exist in the wild. The URL *name* 'item'
    # stays on the canonical slug route (plan §4).
    path('item/<int:pk>/', views.item_legacy_redirect, name='item_legacy'),

    # Writing a review. The path sits under /order/ because the order is what
    # grants the right to write one (§9 Phase 12 item 1) — but the view is
    # catalogue work, so it lives here with the rest of it rather than in
    # payment. The URL conf does not have to agree with the app layout, and
    # pretending otherwise would mean payment importing product's views.
    path('order/<int:order_id>/sharh/', views.review_create, name='review_create'),
]
