"""Panel routes, under /boshqaruv/.

Flat names with a `panel_` prefix rather than a namespace, because that is how
every other URL on this project is named and §4 says a URL name never changes —
introducing a namespace now would mean renaming `style_guide`, which already
lives under this path.

Language-prefixed like everything else (§17 #121). The panel is Uzbek in
practice, but it is a page a person reads, and a page a person reads carries a
language prefix; nothing here is called by a machine.
"""
from django.urls import path

from . import views

urlpatterns = [
    path('boshqaruv/', views.dashboard, name='panel_dashboard'),
    path('boshqaruv/buyurtmalar/', views.orders, name='panel_orders'),
    # By order_no, not by pk: it is the number on the parcel, and the id is
    # deliberately never shown to anyone.
    path('boshqaruv/buyurtmalar/<str:order_no>/', views.order_detail, name='panel_order'),
    path('boshqaruv/buyurtmalar/<str:order_no>/holat/', views.order_status,
         name='panel_order_status'),

    # Products. By slug, like the storefront's own product URLs, so a page open
    # in the panel and the same product open on the site are recognisably the
    # same thing.
    path('boshqaruv/mahsulotlar/', views.products, name='panel_products'),
    path('boshqaruv/mahsulotlar/yangi/', views.product_form, name='panel_product_new'),
    path('boshqaruv/mahsulotlar/<slug:slug>/', views.product_form, name='panel_product'),
    path('boshqaruv/mahsulotlar/<slug:slug>/tahrir/', views.product_inline,
         name='panel_product_inline'),
    path('boshqaruv/mahsulotlar/<slug:slug>/rasmlar/', views.product_images,
         name='panel_product_images'),

    # Moderation and the inbox — the other two things that arrive on their own
    # and wait for somebody.
    path('boshqaruv/sharhlar/', views.reviews, name='panel_reviews'),
    path('boshqaruv/sharhlar/<int:pk>/qaror/', views.review_moderate,
         name='panel_review_moderate'),
    path('boshqaruv/xabarlar/', views.messages_inbox, name='panel_messages'),
    path('boshqaruv/xabarlar/<int:pk>/oqildi/', views.message_read,
         name='panel_message_read'),

    # Reference data: rows somebody changes two or three times a year, so that
    # none of it needs a deploy.
    path('boshqaruv/sozlamalar/', views.settings_screen, name='panel_settings'),
    path('boshqaruv/sozlamalar/teg/', views.tag_new, name='panel_tag_new'),
    path('boshqaruv/sozlamalar/jadval/', views.chart_new, name='panel_chart_new'),
    path('boshqaruv/hududlar/', views.regions, name='panel_regions'),
    path('boshqaruv/malumot/<str:kind>/<int:pk>/', views.reference_inline,
         name='panel_reference_inline'),
]
