"""The staff panel: what the owner does every day, from a phone.

Phase 7a is three screens — a dashboard, a list of orders and one order — and
the rule that shapes all three is that the owner is standing up, holding a
parcel, with one hand free. So: numbers that are links to the screen that acts
on them, a status control on the list itself rather than two taps away, and a
detail page whose first job is to make a phone number tappable.

The panel assumes JavaScript (Kamronbek's decision, §17). It is the one part of
the project that does — the storefront still works without it — and the reason
is that inline saving, drag-to-reorder and client-side image checks are what
make this usable on a phone, and a staff tool runs on a known device. The
status control degrades anyway: it is a real form with a real submit button
that `panel.js` upgrades, because that cost nothing.
"""
import re
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum, Value
from django.db.models.functions import Replace
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from core.models import Msg
from payment.models import DeliveryOption, Order
from product.models import Review, Variant

from .auth import staff_only
from .services import PANEL_CHOICES, PANEL_SETTABLE, UnknownStatus, set_status

#: A variant at or below this is worth telling the owner about. Five is a
#: weekend: enough to sell through before a reprint arrives, not so many that
#: the number is permanently lit and therefore ignored.
LOW_STOCK = 5

#: Orders per page in the list. Twenty fills a laptop screen and is three
#: thumb-scrolls on a phone.
PER_PAGE = 20


@staff_only
def dashboard(request):
    """Today and this week, as numbers that are links.

    Every tile answers a question the owner actually has when they open the
    panel, and every tile that represents *work* goes somewhere that can do it.
    A number with nowhere to go is a number you read twice and then ignore.
    """
    now = timezone.localtime()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = today - timedelta(days=today.weekday())

    # `paying` is excluded from both counts and from revenue: an order nobody
    # has paid for is not a sale, and counting it makes every number flattering
    # and useless.
    real = Order.objects.exclude(status=Order.Status.PAYING)

    def money(qs):
        return qs.aggregate(total=Sum('total_price'))['total'] or 0

    counts = Order.objects.aggregate(
        awaiting=Count('pk', filter=Q(status=Order.Status.PAYING)),
        to_pack=Count('pk', filter=Q(status__in=[Order.Status.PAID,
                                                 Order.Status.PROCESSING])),
        on_the_way=Count('pk', filter=Q(status=Order.Status.ON_THE_WAY)),
    )

    return render(request, 'boshqaruv/dashboard.html', {
        'screen': 'dashboard',
        'orders_today': real.filter(created_at__gte=today).count(),
        'orders_week': real.filter(created_at__gte=week).count(),
        'revenue_today': money(real.filter(created_at__gte=today)),
        'revenue_week': money(real.filter(created_at__gte=week)),
        'awaiting': counts['awaiting'],
        'to_pack': counts['to_pack'],
        'on_the_way': counts['on_the_way'],
        'low_stock': (Variant.objects
                      .filter(available=True, product__is_active=True,
                              stock__lte=LOW_STOCK)
                      .select_related('product', 'size')
                      .order_by('stock')[:8]),
        'low_stock_count': Variant.objects.filter(
            available=True, product__is_active=True, stock__lte=LOW_STOCK).count(),
        'unread': Msg.objects.filter(is_read=False).count(),
        'pending_reviews': Review.objects.filter(
            status=Review.Status.PENDING).count(),
        'latest': _order_list().filter(created_at__gte=week)[:5],
        # The shared order row carries a status control, so the dashboard has
        # to supply its options too. Without this the include rendered a select
        # with nothing in it — a box with an arrow and no text — on a page that
        # still returned 200, which is why only a screenshot caught it.
        'settable': PANEL_CHOICES,
        'settable_values': PANEL_SETTABLE,
    })


def _order_list():
    """Every order, with the rows each screen reads, newest first."""
    return (Order.objects
            .select_related('user', 'delivery_option', 'region', 'district')
            .order_by('-created_at'))


@staff_only
def orders(request):
    """The list, with the filters the daily job actually needs.

    The filters are read from the query string rather than kept in a session,
    so a filtered list is a URL: the owner can bookmark "everything to pack"
    and send "this customer's orders" to somebody in a message.
    """
    qs = _order_list()

    status = request.GET.get('status', '')
    if status in Order.Status.values:
        qs = qs.filter(status=status)

    method = request.GET.get('method', '')
    if method in Order.PaymentMethod.values:
        qs = qs.filter(payment_method=method)

    tier = request.GET.get('tier', '')
    if tier.isdigit():
        qs = qs.filter(delivery_option_id=int(tier))

    # A date range, either end optional. Given as plain dates, because that is
    # what a date input sends and what somebody types.
    since, until = request.GET.get('since', ''), request.GET.get('until', '')
    if since:
        qs = qs.filter(created_at__date__gte=since)
    if until:
        qs = qs.filter(created_at__date__lte=until)

    # One box for the three things a staff member has in front of them: the
    # number on the parcel, the number on the phone, or the customer's name.
    query = request.GET.get('q', '').strip()
    if query:
        found = (Q(order_no__icontains=query)
                 | Q(user__username__icontains=query)
                 | Q(user__first_name__icontains=query))
        # Phone numbers are stored canonically as "+998 90 122 00 07" — with
        # spaces — so a plain icontains on what somebody types matches almost
        # nothing: they read "901220007" off a parcel, or type it grouped their
        # own way. Both sides are reduced to digits before they are compared.
        digits = re.sub(r'\D', '', query)
        if digits:
            qs = qs.annotate(phone_digits=Replace(
                Replace(Replace('phone', Value(' '), Value('')),
                        Value('+'), Value('')),
                Value('-'), Value('')))
            found |= Q(phone_digits__contains=digits)
        qs = qs.filter(found)

    page = Paginator(qs, PER_PAGE).get_page(request.GET.get('page'))
    # The filters, minus the page, for the shared pager (the shop's, reused).
    kept = request.GET.copy()
    kept.pop('page', None)

    return render(request, 'boshqaruv/orders.html', {
        'screen': 'orders',
        'orders': page,
        'base_query': kept.urlencode(),
        'statuses': Order.Status.choices,
        'methods': Order.PaymentMethod.choices,
        'tiers': DeliveryOption.objects.all(),
        'settable': PANEL_CHOICES,
        'settable_values': PANEL_SETTABLE,
        'filters': {'status': status, 'method': method, 'tier': tier,
                    'since': since, 'until': until, 'q': query},
        'total': qs.count(),
    })


@staff_only
def order_detail(request, order_no):
    """One order: what is in it, who it is for, and where it is going.

    Keyed by ``order_no`` rather than by the primary key, because that is the
    number written on the parcel and read down the phone — the id is
    deliberately never shown to anyone (see ``Order.order_no``).
    """
    order = get_object_or_404(
        _order_list().prefetch_related('cart__cart_items__variant__product',
                                       'cart__cart_items__variant__size',
                                       'status_changes__changed_by'),
        order_no=order_no)
    return render(request, 'boshqaruv/order.html', {
        'screen': 'orders',
        'order': order,
        'items': order.cart.cart_items.all(),
        'settable': PANEL_CHOICES,
        'settable_values': PANEL_SETTABLE,
        'trail': order.status_changes.all(),
        'map_url': (f'https://www.google.com/maps/search/?api=1'
                    f'&query={order.latitude},{order.longitude}')
        if order.latitude is not None and order.longitude is not None else '',
    })


@staff_only
@require_POST
def order_status(request, order_no):
    """Move one order's status. Answers JSON to a fetch, a redirect to a form.

    Both, because the control is a real form that `panel.js` upgrades: with the
    script the row updates in place, without it the page reloads and the work
    still gets done. The service is what decides nothing silently — every
    change through here is recorded with who made it.
    """
    order = get_object_or_404(Order, order_no=order_no)
    wanted = request.POST.get('status', '')
    wants_json = request.headers.get('X-Requested-With') == 'fetch'

    if wanted not in PANEL_SETTABLE:
        if wants_json:
            return JsonResponse({'ok': False,
                                 'error': _('Bu holatni qoʻlda oʻrnatib boʻlmaydi.')},
                                status=400)
        messages.error(request, _('Bu holatni qoʻlda oʻrnatib boʻlmaydi.'))
        return redirect(request.POST.get('next') or 'panel_orders')

    try:
        change = set_status(order, wanted, by=request.user)
    except UnknownStatus:
        if wants_json:
            return JsonResponse({'ok': False, 'error': _('Notoʻgʻri holat.')}, status=400)
        messages.error(request, _('Notoʻgʻri holat.'))
        return redirect(request.POST.get('next') or 'panel_orders')

    if wants_json:
        order.refresh_from_db(fields=['status'])
        return JsonResponse({
            'ok': True,
            'status': order.status,
            'label': order.get_status_display(),
            'changed': change is not None,
        })

    if change is not None:
        messages.success(request, _('%(no)s — holat yangilandi.') % {'no': order.order_no})
    return redirect(request.POST.get('next') or 'panel_orders')
