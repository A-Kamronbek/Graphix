"""Storefront views: the shop listing (search / filter / sort) and product detail."""
import json

from django.core.paginator import Paginator
from django.db.models import Exists, Min, OuterRef, Q
from django.shortcuts import get_object_or_404, redirect, render

from .models import Category, Colour, Product, Size, Tag, Variant


def annotate_cards(qs):
    """Add the two values every product card renders: cheapest price and stock.

    ``min_price`` is the lowest price among sellable variants, and ``in_stock``
    says whether anything is actually purchasable — which is what decides the
    "Tugadi" badge. Both as annotations rather than template queries, so a grid of
    twenty cards is still two queries.
    """
    sellable = Q(variants__available=True)
    return qs.annotate(
        min_price=Min('variants__price', filter=sellable),
        in_stock=Exists(
            Variant.objects.filter(product=OuterRef('pk'), available=True, stock__gt=0)
        ),
    )


def shop(request):
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
        .prefetch_related('images', 'variants')
    ).distinct()

    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(name_ru__icontains=q) | Q(name_en__icontains=q)
            | Q(description__icontains=q) | Q(tags__name__icontains=q)
        ).distinct()
    if category:
        qs = qs.filter(category_id=category)
    if size:
        qs = qs.filter(variants__size_id=size, variants__available=True).distinct()
    if tags:
        # Any of the chosen tags, which is how a chip row reads to a shopper.
        qs = qs.filter(tags__slug__in=tags).distinct()

    if sort == 'price_asc':
        qs = qs.order_by('min_price')
    elif sort == 'price_desc':
        qs = qs.order_by('-min_price')
    else:
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
    })


def item_legacy_redirect(request, pk):
    """301 the pre-Phase-4 ``/item/<pk>/`` URL to the product's slug URL."""
    product = get_object_or_404(Product, pk=pk)
    return redirect('item', slug=product.slug, permanent=True)


def item(request, slug):
    """Product detail: gallery, variants, a price map for JS, and related items."""
    product = get_object_or_404(
        Product.objects.prefetch_related(
            'images', 'tags', 'variants__size', 'variants__colour'
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
        .prefetch_related('images', 'variants')
    ).distinct()[:4]

    return render(request, 'product/item.html', {
        'product': product,
        'colours': colours,
        'sizes': sizes,
        'unavailable_sizes': unavailable_sizes,
        'selected_variant': selected_variant,
        'is_purchasable': is_purchasable,
        'variants_json': json.dumps(variants_map),
        'size_chart': product.resolve_size_chart(),
        'related': related,
    })
