from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Min, Q
import json
from .models import Product, Category, Size, Colour, Variant


def shop(request):
    q = request.GET.get('q', '').strip()
    category = request.GET.get('category')
    size = request.GET.get('size')
    sort = request.GET.get('sort', 'new')

    qs = (
        Product.objects
        .filter(variants__available=True)   # only products with at least one available variant
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
        qs = qs.annotate(min_price=Min('variants__price')).order_by('min_price')
    elif sort == 'price_desc':
        qs = qs.annotate(min_price=Min('variants__price')).order_by('-min_price')
    else:
        qs = qs.order_by('-created_at')

    # 5 columns x 4 rows = 20 per page
    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page') or 1
    page_obj = paginator.get_page(page_number)

    # Rebuild querystring without 'page' so pagination links keep filters/sort/search
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
        'q': q,
        'sort': sort,
    })


def item(request, pk):
    product = get_object_or_404(
        Product.objects.prefetch_related('images', 'variants__size', 'variants__colour'),
        pk=pk,
    )

    # Build colour & size lists from this product's variants
    colour_ids = product.variants.values_list('colour_id', flat=True).distinct()
    size_ids = product.variants.values_list('size_id', flat=True).distinct()
    colours = Colour.objects.filter(id__in=colour_ids)
    sizes = Size.objects.filter(id__in=size_ids)

    # Sizes that have NO available variant for this product
    available_size_ids = set(
        product.variants.filter(available=True).values_list('size_id', flat=True)
    )
    unavailable_sizes = [s.id for s in sizes if s.id not in available_size_ids]

    # Default selected variant: first available, or first of all
    selected_variant = product.variants.filter(available=True).first() or product.variants.first()

    # True only if there's at least one purchasable variant
    is_purchasable = product.variants.filter(available=True).exists()

    # Build a JS-friendly map: { "<colour_id>:<size_id>": {price, available} }
    # plus a per-colour list of available sizes, so the front-end can:
    #   1. cross out sizes that are unavailable for the chosen colour
    #   2. update the price when colour/size changes
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
