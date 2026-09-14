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
]
