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
from datetime import datetime, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, F, IntegerField, Q, Sum, Value
from django.db.models.functions import Replace
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError
from django.db import transaction

from django.db.models import ExpressionWrapper, Prefetch

from core.models import Msg
from payment.models import DeliveryOption, District, Order, Region
from product import images as image_pipeline
from product import services as product_services
from product.models import (Category, PrintMethod, Product, Review, Size,
                            SizeChart, Tag, TagKind, Variant)

from . import catalogue, reference
from .auth import staff_only
from .services import PANEL_CHOICES, PANEL_SETTABLE, UnknownStatus, set_status

#: Orders per page in the list. Twenty fills a laptop screen and is three
#: thumb-scrolls on a phone.
PER_PAGE = 20


def _int(raw, default=0):
    """Parse a number out of a POST field, or fall back. Never raises.

    A panel endpoint that 500s on a hand-edited form field is a panel endpoint
    that 500s, and none of the numbers arriving here are worth that.
    """
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


#: The ways the panel reads a date typed into a field. Day first, as the owner
#: writes one (§18 #38); the ISO form is still read, so a link or a bookmark
#: made before the change keeps working.
DATE_READ = ('%d/%m/%Y', '%d.%m.%Y', '%Y-%m-%d')


def _date(raw):
    """Parse a date out of the query string: a :class:`date`, or None.

    Never raises - the same rule as ``_int``, and for the reason this filter
    once broke: an unparseable string handed to ``created_at__date__gte``
    raises inside the query compiler, so a bookmark somebody had edited, or a
    stale link with a half-typed date in it, took the orders screen down with
    a 500 rather than showing an unfiltered list.
    """
    text = str(raw or '').strip()
    for pattern in DATE_READ:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def _shown(day):
    """A date as the panel's fields show it - dd/mm/yyyy - or '' for none."""
    return f'{day.day:02d}/{day.month:02d}/{day.year:04d}' if day else ''


def _safe_next(request, fallback):
    """Where to send a plain form post back to. Never off this site.

    ``next`` arrives in the POST body, and ``redirect()`` will happily send a
    browser to any absolute URL it is handed. Nothing here is reachable without
    a staff session and a CSRF token, but an unchecked redirect is an unchecked
    redirect, and the rule the rest of the project follows is Django's own.
    """
    target = request.POST.get('next') or ''
    if target and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()},
            require_https=request.is_secure()):
        return target
    return fallback


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
        # One definition of "running low", on the model, used by the tile, by
        # the list below it and by the list the tile links to. A size the owner
        # has taken off sale is not stock waiting to be sold, and neither is
        # anything belonging to a withdrawn product (§17 #179).
        'low_stock': (Variant.objects.running_low()
                      .select_related('product', 'size')
                      .order_by('stock')[:8]),
        'low_stock_count': Variant.objects.running_low().count(),
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

    # One status, or several separated by commas. The comma is there because
    # the dashboard's "to pack" tile counts `paid` and `processing` together —
    # a parcel is a parcel either way — and a tile whose number does not match
    # the list it lands on is a tile nobody trusts twice.
    status = request.GET.get('status', '')
    wanted = [s for s in status.split(',') if s in Order.Status.values]
    if wanted:
        qs = qs.filter(status__in=wanted)

    method = request.GET.get('method', '')
    if method in Order.PaymentMethod.values:
        qs = qs.filter(payment_method=method)

    tier = request.GET.get('tier', '')
    if tier.isdigit():
        qs = qs.filter(delivery_option_id=int(tier))

    # A date range, either end optional. Typed day first - the fields are
    # text, because a native date input draws the browser's own format, which
    # is mm/dd/yyyy in an English browser (§18 #38) - and parsed before it
    # reaches the query, because anything else is a 500 (see `_date`).
    since = _date(request.GET.get('since', ''))
    until = _date(request.GET.get('until', ''))
    if since:
        qs = qs.filter(created_at__date__gte=since)
    if until:
        qs = qs.filter(created_at__date__lte=until)

    # One box for the three things a staff member has in front of them: the
    # number on the parcel, the number on the phone, or the customer's name.
    query = request.GET.get('q', '').strip()
    if query:
        found = (Q(order_no__icontains=query)
                 | Q(recipient_name__icontains=query)
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
                    'since': _shown(since), 'until': _shown(until), 'q': query},
        # The select marks every status the list is actually showing, so a
        # two-status filter does not leave the control reading "all statuses".
        'chosen_statuses': wanted,
        'date_fields': [('since', _shown(since), _('Sanadan')),
                        ('until', _shown(until), _('Sanagacha'))],
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
        _order_list().prefetch_related('status_changes__changed_by'),
        order_no=order_no)
    return render(request, 'boshqaruv/order.html', {
        'screen': 'orders',
        'order': order,
        # `price_stat` is the price of ONE, frozen at the moment it went into
        # the cart, and the order's total is the sum of price x quantity. The
        # page was printing the unit price beside "x 2" and the total below,
        # so the three numbers on screen did not add up and no arithmetic a
        # staff member could do would make them.
        'items': (order.cart.cart_items
                  .select_related('variant__product', 'variant__size')
                  .annotate(line_total=ExpressionWrapper(
                      F('price_stat') * F('quantity'),
                      output_field=IntegerField()))),
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
        return redirect(_safe_next(request, 'panel_orders'))

    try:
        change = set_status(order, wanted, by=request.user)
    except UnknownStatus:
        if wants_json:
            return JsonResponse({'ok': False, 'error': _('Notoʻgʻri holat.')}, status=400)
        messages.error(request, _('Notoʻgʻri holat.'))
        return redirect(_safe_next(request, 'panel_orders'))

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
    return redirect(_safe_next(request, 'panel_orders'))


# ---------------------------------------------------------------- products
# The screen the plan calls the most important one in the phase: the owner adds
# every product himself, with photographs, from a phone. So it gets the same
# care as the storefront's own product page — and the logic lives in
# `panel.catalogue`, because four things have to change together and a
# half-saved product is one that is live and unbuyable.

@staff_only
def products(request):
    """The catalogue, with the two things that change daily editable in place.

    Availability and stock are what somebody actually changes between parcels;
    everything else is a trip to the edit screen. The list carries both.
    """
    qs = (Product.objects.prefetch_related('images', 'variants__size')
          .order_by('-created_at'))

    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(name_ru__icontains=query)
                       | Q(name_en__icontains=query) | Q(slug__icontains=query))

    category = request.GET.get('category', '')
    if category.isdigit():
        qs = qs.filter(category_id=int(category))

    active = request.GET.get('active', '')
    if active in ('1', '0'):
        qs = qs.filter(is_active=(active == '1'))

    # The dashboard's "running low" tile counts variants; this is where it
    # lands. Without it the tile said "6" and opened the whole catalogue, which
    # is the same as saying nothing. Through the same queryset the tile counts,
    # so the two cannot drift: a product is here when one of its sizes is a row
    # in that count (§17 #179).
    low = request.GET.get('low', '') == '1'
    if low:
        qs = qs.filter(pk__in=Variant.objects.running_low().values('product'))

    page = Paginator(qs, PER_PAGE).get_page(request.GET.get('page'))
    kept = request.GET.copy()
    kept.pop('page', None)
    return render(request, 'boshqaruv/products.html', {
        'screen': 'products',
        'products': page,
        'base_query': kept.urlencode(),
        'categories': Category.objects.all(),
        'filters': {'q': query, 'category': category, 'active': active,
                    'low': '1' if low else ''},
        'total': qs.count(),
    })


#: Every text field on the product form, so a refused save and a fresh edit
#: can be rendered from the same dictionary.
PRODUCT_FIELDS = ('name', 'name_ru', 'name_en', 'description', 'description_ru',
                  'description_en', 'gsm', 'material', 'material_ru', 'material_en')


def _saved_values(product):
    """The product as the form's boxes want it: a flat dict of strings."""
    if product is None:
        # A new product starts on sale; everything else starts empty.
        return {'is_active': '1'}
    values = {name: (getattr(product, name) or '') for name in PRODUCT_FIELDS}
    values['category'] = product.category_id or ''
    values['size_chart'] = product.size_chart_id or ''
    values['print_method'] = product.print_method_id or ''
    values['is_active'] = '1' if product.is_active else ''
    return values


@staff_only
def product_form(request, slug=None):
    """Create a product, or edit one. One screen, because it is one job.

    A new product is saved before its photographs are, because an ``ImageP``
    needs a product to belong to — so "create" writes the row and then lands on
    the same screen in edit mode, where the gallery and the grid are waiting.
    That is also why the DoD's "in one sitting" is achievable on a phone: the
    text goes in, it saves, and the photographs go on afterwards without
    losing anything.
    """
    product = get_object_or_404(Product, slug=slug) if slug else None
    posted = None

    if request.method == 'POST':
        try:
            # One transaction around *both*, not one around each. They are
            # separately atomic so either can be called on its own, and that is
            # exactly what made this wrong first time: the product committed,
            # the grid was refused, and the catalogue was left holding a
            # product with no sizes — live, and unbuyable.
            with transaction.atomic():
                product = catalogue.save_product(request.POST, product)
                catalogue.save_grid(product, request.POST)
        except ValidationError as exc:
            product = Product.objects.filter(slug=slug).first() if slug else None
            # What was typed comes back with the refusal. Re-reading the row
            # instead throws away everything on the screen because one price
            # was wrong, which is §17 #133 on a form ten times longer than the
            # review box that finding came from.
            posted = request.POST
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, _('Saqlandi.'))
            return redirect('panel_product', slug=product.slug)

    # Chips grouped under the axis they belong to. A flat list of every tag is
    # readable at eight and unreadable at forty, and the axis is the thing the
    # owner is thinking in when they pick one.
    tag_groups = [(kind, list(kind.tags.all()))
                  for kind in TagKind.objects.prefetch_related('tags')]
    loose = list(Tag.objects.filter(kind__isnull=True))
    if loose:
        tag_groups.append((None, loose))

    sizes = Size.objects.all()
    # The grid, as rows the template can render without looking anything up:
    # every size the shop sells, carrying this product's numbers where it has
    # them and blanks where it does not.
    by_size = {v.size_id: v for v in product.variants.all()} if product else {}
    grid = []
    for size in sizes:
        variant = by_size.get(size.pk)
        if posted is None:
            row = {'price': variant.price if variant else '',
                   'stock': variant.stock if variant else '',
                   'available': bool(variant and variant.available)}
        else:
            row = {'price': posted.get('price_%s' % size.pk, ''),
                   'stock': posted.get('stock_%s' % size.pk, ''),
                   'available': bool(posted.get('available_%s' % size.pk))}
        row['size'] = size
        grid.append(row)

    return render(request, 'boshqaruv/product_form.html', {
        'screen': 'products',
        'product': product,
        # What to put in every box: the row as saved, or what was typed and
        # refused. `field` reads one or the other so the template does not have
        # to ask twice on every line.
        'form': posted if posted is not None else _saved_values(product),
        'grid': grid,
        'categories': Category.objects.all(),
        'charts': SizeChart.objects.all(),
        'tag_groups': tag_groups,
        'chosen_tags': (set(_int(t) for t in posted.getlist('tags')) if posted is not None
                        else set(product.tags.values_list('pk', flat=True)) if product
                        else set()),
        'print_methods': PrintMethod.objects.all(),
        'max_images': catalogue.MAX_IMAGES,
        'copy_templates': catalogue.description_templates(),
        'max_bytes': image_pipeline.MAX_BYTES,
        'max_pixels': image_pipeline.MAX_PIXELS,
    })


@staff_only
@require_POST
def product_inline(request, slug):
    """One inline edit from the list: availability, a price, or one size's stock.

    Deliberately narrow. This endpoint can change three things and nothing
    else, so a stray POST cannot rewrite a product's copy or its category — the
    edit screen is where a product is edited, and this is where a number is
    corrected between parcels.
    """
    product = get_object_or_404(Product, slug=slug)
    field = request.POST.get('field', '')
    raw = request.POST.get('value', '')

    if field == 'is_active':
        product.is_active = raw in ('1', 'true', 'on')
        product.save(update_fields=['is_active'])
        return JsonResponse({'ok': True, 'value': product.is_active})

    if field == 'price':
        try:
            price = catalogue.price_of(raw)
        except ValidationError as exc:
            return JsonResponse({'ok': False, 'error': exc.messages[0]}, status=400)
        # One price per design is how this catalogue works, so the list edits
        # all of a product's sizes at once. A size that needs its own price is
        # the edit screen's job.
        product.variants.update(price=price)
        return JsonResponse({'ok': True, 'value': str(price)})

    if field == 'stock':
        variant = get_object_or_404(Variant, product=product,
                                    size_id=_int(request.POST.get('size')))
        # Refused, not rounded down to zero: "sa" in a stock box used to take
        # the size off sale silently, which is the one outcome nobody wants.
        if not str(raw).strip().isdigit():
            return JsonResponse({'ok': False, 'error': _('Faqat raqam kiriting.')},
                                status=400)
        variant.stock = _int(raw)
        variant.save(update_fields=['stock'])
        # Both facts, so the pill can recolour itself the moment the number is
        # typed rather than at the next page load. The server decides which it
        # is; the script only paints it (§17 #180).
        return JsonResponse({'ok': True, 'value': variant.stock,
                             'purchasable': variant.is_purchasable,
                             'low': variant.is_running_low})

    return JsonResponse({'ok': False, 'error': _('Notoʻgʻri maydon.')}, status=400)


@staff_only
@require_POST
def product_images(request, slug):
    """Add, reorder or remove this product's photographs.

    Uploading answers with the rendered gallery so the page does not have to
    guess what happened — the server resized and re-encoded the file, so only
    it knows the URL the photograph ended up at.
    """
    product = get_object_or_404(Product, slug=slug)
    action = request.POST.get('action', 'add')

    if action == 'add':
        try:
            catalogue.add_images(product, request.FILES.getlist('images'))
        except ValidationError as exc:
            return JsonResponse({'ok': False, 'error': exc.messages[0]}, status=400)

    elif action == 'order':
        catalogue.reorder_images(product, request.POST.getlist('ids'))

    elif action == 'delete':
        product.images.filter(pk=_int(request.POST.get('id'))).delete()
        catalogue.reorder_images(product, [])

    else:
        return JsonResponse({'ok': False, 'error': _('Notoʻgʻri amal.')}, status=400)

    return JsonResponse({'ok': True, 'images': [
        {'id': image.pk, 'url': image.picture.url}
        for image in product.images.all()
    ]})


# ----------------------------------------------------------------- reviews
# The queue is the whole reason customer photographs are safe on a public page
# (§17 #25). What it needs above everything else is to show those photographs
# at a size somebody can actually judge — a moderation screen with 72 px
# thumbnails is a screen where everything gets approved.

@staff_only
def reviews(request):
    """Reviews waiting for a decision, oldest first."""
    status = request.GET.get('status', Review.Status.PENDING)
    if status not in Review.Status.values:
        status = Review.Status.PENDING

    qs = (Review.objects.filter(status=status)
          .select_related('user', 'product', 'order')
          .prefetch_related('images')
          .order_by('created_at'))

    page = Paginator(qs, PER_PAGE).get_page(request.GET.get('page'))
    kept = request.GET.copy()
    kept.pop('page', None)
    return render(request, 'boshqaruv/reviews.html', {
        'screen': 'reviews',
        'reviews': page,
        'base_query': kept.urlencode(),
        'status': status,
        'statuses': Review.Status.choices,
        'pending': Review.objects.filter(status=Review.Status.PENDING).count(),
        'total': qs.count(),
    })


@staff_only
@require_POST
def review_moderate(request, pk):
    """Approve or reject one review, through the service that moves the rating.

    Not a bare ``update()``: a bulk update fires no signals, and approving a
    review used to leave the product's rating exactly as it was (§17, Phase 12).
    ``product.services.moderate`` recomputes it explicitly, so this endpoint
    calls that and nothing else.
    """
    review = get_object_or_404(Review, pk=pk)
    decision = request.POST.get('status', '')
    if decision not in (Review.Status.APPROVED, Review.Status.REJECTED):
        return JsonResponse({'ok': False, 'error': _('Notoʻgʻri qaror.')}, status=400)

    product_services.moderate(Review.objects.filter(pk=review.pk), decision,
                              by=request.user)
    review.product.refresh_from_db(fields=['rating_avg', 'review_count'])
    review.status = decision
    # The label and the rating line are rendered here rather than assembled in
    # the script: a badge says what the review now IS, and the script had been
    # copying the button's own text into it, so approving a review left a badge
    # reading "Tasdiqlash" — approve — where "Tasdiqlangan" belongs. The rating
    # line uses the template's own sentence, so it reads the same either side
    # of the decision, in whichever language the panel is being read in.
    return JsonResponse({
        'ok': True,
        'status': decision,
        'label': review.get_status_display(),
        'rating': str(review.product.rating_avg),
        'count': review.product.review_count,
        'rating_line': _('%(avg)s — %(n)s ta') % {
            'avg': review.product.rating_avg, 'n': review.product.review_count},
    })


# ---------------------------------------------------------------- messages

@staff_only
def messages_inbox(request):
    """The contact form's inbox. Unread first is wrong; newest first is right.

    An inbox sorted by unread reshuffles itself as you read it, which is
    disorienting on a phone. Newest first stays still, and the unread ones are
    marked.
    """
    show = request.GET.get('show', '')
    qs = Msg.objects.select_related('user').order_by('-created_at')
    if show == 'unread':
        qs = qs.filter(is_read=False)

    page = Paginator(qs, PER_PAGE).get_page(request.GET.get('page'))
    kept = request.GET.copy()
    kept.pop('page', None)
    return render(request, 'boshqaruv/messages.html', {
        'screen': 'messages',
        'msgs': page,
        'base_query': kept.urlencode(),
        'show': show,
        'unread': Msg.objects.filter(is_read=False).count(),
        'total': qs.count(),
    })


@staff_only
@require_POST
def message_read(request, pk):
    """Mark one message read or unread. Both ways, because people misclick."""
    msg = get_object_or_404(Msg, pk=pk)
    msg.is_read = request.POST.get('value', '1') in ('1', 'true', 'on')
    msg.save(update_fields=['is_read'])
    return JsonResponse({'ok': True, 'value': msg.is_read,
                         'unread': Msg.objects.filter(is_read=False).count()})


# --------------------------------------------------------------- reference

@staff_only
def settings_screen(request):
    """Delivery tiers, tags and size charts: the rows that are edited rarely.

    One screen rather than three, because three nav items for things touched
    twice a year is three things to scroll past every day. Regions get their
    own screen — there are two hundred districts and they need a search.
    """
    return render(request, 'boshqaruv/settings.html', {
        'screen': 'settings',
        'tiers': DeliveryOption.objects.all(),
        'tags': Tag.objects.select_related('kind'),
        'charts': SizeChart.objects.all(),
        'kinds': TagKind.objects.all(),
        'methods': PrintMethod.objects.all(),
        'categories': Category.objects.all(),
    })


@staff_only
def regions(request):
    """Regions and their districts, searchable.

    The postal prefix is editable because it is the thing that decides whether
    a customer's typed index is accepted, and it is the field most likely to
    need correcting — the classifier is right today and administrative
    divisions are not permanent (§17 #86).
    """
    query = request.GET.get('q', '').strip()
    districts = District.objects.select_related('region')
    if query:
        districts = districts.filter(Q(name__icontains=query)
                                     | Q(name_ru__icontains=query)
                                     | Q(name_en__icontains=query)
                                     | Q(code__icontains=query))
    return render(request, 'boshqaruv/regions.html', {
        'screen': 'settings',
        'regions': Region.objects.prefetch_related(
            Prefetch('districts', queryset=districts)),
        'query': query,
        'kinds': District.Kind.choices,
    })


@staff_only
@require_POST
def reference_inline(request, kind, pk):
    """One field on one reference row, through the allowlist in `reference.py`."""
    try:
        value = reference.set_field(kind, pk, request.POST.get('field', ''),
                                    request.POST.get('value', ''))
    except ValidationError as exc:
        return JsonResponse({'ok': False, 'error': exc.messages[0]}, status=400)
    return JsonResponse({'ok': True, 'value': value})


def _free_slug(model, name, fallback):
    """A slug from the Uzbek name, with a -2 suffix until it is free.

    ``slugify`` drops the Uzbek modifier letters (oʻ, gʻ), which is the URL we
    want; a name that slugifies to nothing falls back to a fixed stem.
    """
    from django.utils.text import slugify
    base = slugify(name, allow_unicode=False) or fallback
    slug, n = base[:55], 1
    while model.objects.filter(slug=slug).exists():
        n += 1
        slug = '%s-%d' % (base[:50], n)
    return slug


@staff_only
@require_POST
def tag_new(request):
    """Create a tag. Its slug comes from the Uzbek name, like everything else."""
    name = (request.POST.get('name') or '').strip()
    if not name:
        messages.error(request, _('Nomi kerak.'))
        return redirect('panel_settings')

    kind_id = request.POST.get('kind', '')
    Tag.objects.create(
        slug=_free_slug(Tag, name, 'teg'), name=name[:60],
        name_ru=(request.POST.get('name_ru') or '').strip()[:60],
        name_en=(request.POST.get('name_en') or '').strip()[:60],
        kind=TagKind.objects.filter(pk=kind_id).first() if kind_id.isdigit() else None,
    )
    messages.success(request, _('Teg qoʻshildi.'))
    return redirect('panel_settings')


@staff_only
@require_POST
def lookup_new(request, kind):
    """Create a tag kind, a print method or a category.

    Three tables, one endpoint, because they are the same shape: a name in
    three languages and nothing else the owner has to think about. `kind` is
    matched against the allowlist, so this cannot reach a fourth table.
    """
    models = {'tagkind': (TagKind, 'tur', _('Teg turi qoʻshildi.')),
              'method': (PrintMethod, 'usul', _('Bosma usuli qoʻshildi.')),
              'category': (Category, 'turkum', _('Turkum qoʻshildi.'))}
    if kind not in models:
        messages.error(request, _('Notoʻgʻri jadval.'))
        return redirect('panel_settings')

    model, stem, done = models[kind]
    name = (request.POST.get('name') or '').strip()
    if not name:
        messages.error(request, _('Nomi kerak.'))
        return redirect('panel_settings')

    limit = model._meta.get_field('name').max_length
    row = model(name=name[:limit],
                name_ru=(request.POST.get('name_ru') or '').strip()[:limit],
                name_en=(request.POST.get('name_en') or '').strip()[:limit])
    row.slug = _free_slug(model, name, stem)
    row.save()
    messages.success(request, done)
    return redirect('panel_settings')


@staff_only
@require_POST
def reference_delete(request, kind, pk):
    """Remove one reference row, when nothing is holding on to it."""
    try:
        name = reference.delete_row(kind, pk)
    except ValidationError as exc:
        return JsonResponse({'ok': False, 'error': exc.messages[0]}, status=400)
    return JsonResponse({'ok': True, 'name': name})


@staff_only
@require_POST
def chart_new(request):
    """Upload a size chart. The image is the chart; the rows are optional (§17 #15)."""
    name = (request.POST.get('name') or '').strip()
    upload = request.FILES.get('image')
    if not name or not upload:
        messages.error(request, _('Nomi va rasm kerak.'))
        return redirect('panel_settings')

    try:
        clean = image_pipeline.sanitise(upload, name_hint='chart',
                                        max_edge=image_pipeline.PRODUCT_MAX_EDGE)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect('panel_settings')

    SizeChart.objects.create(name=name, image=clean)
    messages.success(request, _('Jadval qoʻshildi.'))
    return redirect('panel_settings')
