"""Storefront views: the shop listing (search / filter / sort), product detail,
and the heart."""
import json

from django.core.paginator import Paginator
from django.db.models import Exists, Min, OuterRef, Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles import finders
from django.http import JsonResponse
from django.templatetags.static import static
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from core.context_processors import SIZE_GUIDE_IMAGE
from core.ratelimit import is_rate_limited, RATE_LIMIT_MESSAGE
from . import services
from .models import Category, Colour, Product, ProductLike, Size, Tag, Variant


def annotate_cards(qs, user=None):
    """Add the values every product card renders: cheapest price, stock, heart.

    ``min_price`` is the lowest price among sellable variants, and ``in_stock``
    says whether anything is actually purchasable — which is what decides the
    "Tugadi" badge. Both as annotations rather than template queries, so a grid of
    twenty cards is still two queries.

    ``is_liked`` is added only for a signed-in visitor, because for anyone else
    the answer is always no and the subquery would be pure cost. A card rendered
    without the annotation reads ``p.is_liked`` as missing, which the template
    engine resolves to an empty string — falsy, which is the right answer.
    """
    sellable = Q(variants__available=True)
    qs = qs.annotate(
        min_price=Min('variants__price', filter=sellable),
        in_stock=Exists(
            Variant.objects.filter(product=OuterRef('pk'), available=True, stock__gt=0)
        ),
    )
    if user is not None and user.is_authenticated:
        qs = qs.annotate(
            is_liked=Exists(ProductLike.objects.filter(user=user, product=OuterRef('pk')))
        )
    return qs


def shop(request):
    """The full catalogue with filters, sort and paging."""
    return _listing(request)


def search(request):
    """Global search results at /qidiruv/.

    Same matching and the same template as the shop — a second implementation of
    the query would be a second thing to keep in step, and the shop page already
    knows how to render a result set. What differs is the entry point: the header
    field posts here, and the page introduces itself as a search rather than as
    the catalogue.
    """
    return _listing(request, search_page=True)


def _listing(request, search_page=False):
    """List products with search, filters, sort, and paging.

    Listing requires ``available``, not purchasability: a sold-out design stays
    browsable and keeps its page, and the cart is where stock is enforced
    (§17 #56). What does hide a product is ``is_active=False`` — the owner's
    explicit switch.
    """
    q = request.GET.get('q', '').strip()
    category = request.GET.get('category')
    size = request.GET.get('size')
    tags = [t for t in request.GET.getlist('tag') if t]
    sort = request.GET.get('sort', 'new')

    qs = annotate_cards(
        Product.objects
        .filter(is_active=True, variants__available=True)
        .prefetch_related('images', 'variants'),
        user=request.user,
    ).distinct()

    if q:
        # Every language of every searchable field. A Russian-speaking visitor
        # typing a Russian product name or a Russian tag has to find the design;
        # matching only the Uzbek columns made the other two languages decorative.
        qs = qs.filter(
            Q(name__icontains=q) | Q(name_ru__icontains=q) | Q(name_en__icontains=q)
            | Q(description__icontains=q) | Q(description_ru__icontains=q)
            | Q(description_en__icontains=q)
            | Q(tags__name__icontains=q) | Q(tags__name_ru__icontains=q)
            | Q(tags__name_en__icontains=q)
        ).distinct()
    if category:
        qs = qs.filter(category_id=category)
    if size:
        qs = qs.filter(variants__size_id=size, variants__available=True).distinct()
    if tags:
        # Any of the chosen tags, which is how a chip row reads to a shopper.
        qs = qs.filter(tags__slug__in=tags).distinct()

    # Both new sorts fall back to recency, so a catalogue with no likes and no
    # reviews yet still comes out in a sensible order rather than by primary key.
    if sort == 'price_asc':
        qs = qs.order_by('min_price')
    elif sort == 'price_desc':
        qs = qs.order_by('-min_price')
    elif sort == 'popular':
        qs = qs.order_by('-likes_count', '-created_at')
    elif sort == 'rating':
        qs = qs.order_by('-rating_avg', '-review_count', '-created_at')
    else:
        sort = 'new'
        qs = qs.order_by('-created_at')

    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page') or 1
    page_obj = paginator.get_page(page_number)

    # Preserve the current filters in pagination links (everything except page).
    qd = request.GET.copy()
    qd.pop('page', None)
    base_query = qd.urlencode()

    return render(request, 'product/shop.html', {
        'products': page_obj.object_list,
        'page_obj': page_obj,
        'paginator': paginator,
        'base_query': base_query,
        'total_count': paginator.count,
        'categories': Category.objects.all(),
        'sizes': Size.objects.all(),
        'tag_groups': [
            (kind_label, Tag.objects.filter(kind=kind_value))
            for kind_value, kind_label in Tag.Kind.choices
        ],
        'selected_category': category,
        'selected_size': size,
        'selected_tags': tags,
        'filter_count': len(tags) + (1 if category else 0) + (1 if size else 0),
        'q': q,
        'sort': sort,
        'search_page': search_page,
    })


@login_required
def liked(request):
    """The visitor's saved designs — the private half of the heart (§17 #3).

    Same grid and same card as the shop, because a saved design should look
    identical to a browsed one. Every card here is liked by definition, so the
    heart renders pressed without the annotation having to prove it — but the
    annotation is still asked for, because the card partial is one template and
    should not have to know which page it is on.
    """
    products = annotate_cards(
        Product.objects
        .filter(is_active=True, likes__user=request.user)
        .prefetch_related('images', 'variants'),
        user=request.user,
    ).order_by('-likes__created_at').distinct()

    return render(request, 'product/liked.html', {'products': products})


@require_POST
def like_toggle(request, slug):
    """Save or unsave a design, and move its public count with it.

    Two callers, one view. ``main.js`` posts with ``Accept: application/json``
    and gets the new state back to swap in place; the same button with
    JavaScript off is an ordinary form POST that redirects to where it came
    from. Neither path is special-cased in the service — they differ only in
    what this function returns.

    An anonymous visitor is sent to login rather than refused: the heart is the
    one control on a product card that needs an account, and being told to sign
    in is a better answer than a disabled button.
    """
    product = get_object_or_404(Product, slug=slug, is_active=True)
    wants_json = 'application/json' in request.headers.get('Accept', '')
    # `next` comes from the page the heart was tapped on, which is user input:
    # only an internal URL is honoured, or this becomes an open redirect.
    back = request.POST.get('next') or ''
    if not back or not url_has_allowed_host_and_scheme(
        back, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        back = reverse('item', kwargs={'slug': product.slug})

    if not request.user.is_authenticated:
        login_url = f"{reverse('login')}?next={back}"
        if wants_json:
            return JsonResponse({'login_url': login_url}, status=401)
        return redirect(login_url)

    # Sixty toggles in five minutes is far past anything a person does with a
    # heart, and the endpoint writes on every call.
    if is_rate_limited(request, 'like', 60, 300, ident=f"u{request.user.pk}"):
        if wants_json:
            return JsonResponse({'error': str(RATE_LIMIT_MESSAGE)}, status=429)
        messages.error(request, RATE_LIMIT_MESSAGE)
        return redirect(back)

    liked, count = services.toggle_like(request.user, product)
    if wants_json:
        return JsonResponse({'liked': liked, 'count': count})
    messages.success(request, _("Saqlandi.") if liked else _("Saqlanganlardan olib tashlandi."))
    return redirect(back)


def item_legacy_redirect(request, pk):
    """301 the pre-Phase-4 ``/item/<pk>/`` URL to the product's slug URL."""
    product = get_object_or_404(Product, pk=pk)
    return redirect('item', slug=product.slug, permanent=True)


def item(request, slug):
    """Product detail: gallery, variants, a price map for JS, and related items."""
    product = get_object_or_404(
        Product.objects.prefetch_related(
            'images', 'tags', 'variants__size', 'variants__colour',
            # The chart's rows render in the hidden block the viewer clones, so
            # they are fetched with the product rather than one query per row.
            'size_chart__rows__size', 'category__size_chart__rows__size',
        ).select_related('category', 'size_chart', 'category__size_chart'),
        slug=slug,
        is_active=True,
    )

    colour_ids = product.variants.values_list('colour_id', flat=True).distinct()
    size_ids = product.variants.values_list('size_id', flat=True).distinct()
    colours = Colour.objects.filter(id__in=colour_ids)
    sizes = Size.objects.filter(id__in=size_ids)

    # Purchasable, not merely available: a size the owner still sells but has run
    # out of has to read as unpickable, or the customer hits an error on submit.
    purchasable = product.variants.filter(available=True, stock__gt=0)
    available_size_ids = set(purchasable.values_list('size_id', flat=True))
    unavailable_sizes = [s.id for s in sizes if s.id not in available_size_ids]

    selected_variant = purchasable.first() or product.variants.first()
    is_purchasable = purchasable.exists()

    # "colour_id:size_id" -> price/availability/id/stock, consumed by variant.js to
    # update the price and the add-to-cart state as the customer picks options. The
    # key stays 'available' so the existing picker contract holds (§17 #23); it now
    # carries purchasability, which is what the button actually depends on.
    variants_map = {}
    for v in product.variants.all():
        key = f"{v.colour_id or ''}:{v.size_id or ''}"
        variants_map[key] = {
            'price': float(v.price),
            'available': bool(v.is_purchasable),
            'id': v.id,
            'stock': v.stock,
        }

    related = annotate_cards(
        Product.objects
        .filter(is_active=True, category=product.category, variants__available=True)
        .exclude(id=product.id)
        .prefetch_related('images', 'variants'),
        user=request.user,
    ).distinct()[:4]

    is_liked = (request.user.is_authenticated
                and ProductLike.objects.filter(user=request.user, product=product).exists())

    return render(request, 'product/item.html', {
        'product': product,
        'is_liked': is_liked,
        'colours': colours,
        'sizes': sizes,
        'unavailable_sizes': unavailable_sizes,
        'selected_variant': selected_variant,
        'is_purchasable': is_purchasable,
        'variants_json': json.dumps(variants_map),
        'size_chart': product.resolve_size_chart(),
        # The drawn chart, if the owner has not replaced it with his own. Same
        # lookup the standalone page uses, so the two never show different files.
        'size_guide_image': finders.find(SIZE_GUIDE_IMAGE) and static(SIZE_GUIDE_IMAGE),
        # The delivery line reads from the rows, so the page and the checkout can
        # never quote different prices (§18 #18). Imported here rather than at
        # module scope to keep product from taking a startup import on payment.
        'delivery_options': _delivery_options(),
        'related': related,
    })


def _delivery_options():
    """The active delivery tiers, for the product page's delivery line."""
    from payment.models import DeliveryOption
    return list(DeliveryOption.objects.filter(is_active=True))
