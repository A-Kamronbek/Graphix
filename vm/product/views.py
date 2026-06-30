"""Storefront views: the shop listing (search / filter / sort) and product detail."""
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Min, Q
import json
from .models import Product, Category, Size, Colour, Variant


def shop(request):
    """List purchasable products with search, category/size filters, sort, and paging."""
    q = request.GET.get('q', '').strip()
    category = request.GET.get('category')
    size = request.GET.get('size')
    sort = request.GET.get('sort', 'new')

    qs = (
        Product.objects
        .filter(variants__available=True)
        .annotate(min_price=Min('variants__price', filter=Q(variants__available=True)))
        .prefetch_related('images', 'variants')
        .distinct()
    )

    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if category:
        qs = qs.filter(category_id=category)
    if size:
        qs = qs.filter(variants__size_id=size, variants__available=True).distinct()

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
        'selected_category': category,
        'selected_size': size,
        'q': q,
        'sort': sort,
    })


def item(request, pk):
    """Product detail: variants, availability, a price map for JS, and related items."""
    product = get_object_or_404(
        Product.objects.prefetch_related('images', 'variants__size', 'variants__colour'),
        pk=pk,
    )

    colour_ids = product.variants.values_list('colour_id', flat=True).distinct()
    size_ids = product.variants.values_list('size_id', flat=True).distinct()
    colours = Colour.objects.filter(id__in=colour_ids)
    sizes = Size.objects.filter(id__in=size_ids)

    available_size_ids = set(
        product.variants.filter(available=True).values_list('size_id', flat=True)
    )
    unavailable_sizes = [s.id for s in sizes if s.id not in available_size_ids]

    selected_variant = product.variants.filter(available=True).first() or product.variants.first()

    is_purchasable = product.variants.filter(available=True).exists()

    # "colour_id:size_id" -> price/availability/id, consumed by the product-page JS
    # to update price and the add-to-cart state as the user picks options.
    variants_map = {}
    for v in product.variants.all():
        key = f"{v.colour_id or ''}:{v.size_id or ''}"
        variants_map[key] = {
            'price': float(v.price),
            'available': bool(v.available),
            'id': v.id,
        }

    related = (
        Product.objects.filter(category=product.category, variants__available=True)
        .exclude(id=product.id)
        .annotate(min_price=Min('variants__price', filter=Q(variants__available=True)))
        .prefetch_related('images', 'variants')
        .distinct()[:4]
    )

    return render(request, 'product/item.html', {
        'product': product,
        'colours': colours,
        'sizes': sizes,
        'unavailable_sizes': unavailable_sizes,
        'selected_variant': selected_variant,
        'is_purchasable': is_purchasable,
        'variants_json': json.dumps(variants_map),
        'related': related,
    })
