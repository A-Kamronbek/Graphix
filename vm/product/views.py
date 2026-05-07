from django.shortcuts import render, get_object_or_404
from django.db.models import Min, Q
from .models import Product, Category, Size, Colour, Variant


def shop(request):
    q = request.GET.get('q', '').strip()
    category = request.GET.get('category')
    size = request.GET.get('size')
    sort = request.GET.get('sort', 'new')

    qs = Product.objects.prefetch_related('images', 'variants').all()

    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if category:
        qs = qs.filter(category_id=category)
    if size:
        qs = qs.filter(variants__size_id=size).distinct()

    if sort == 'price_asc':
        qs = qs.annotate(min_price=Min('variants__price')).order_by('min_price')
    elif sort == 'price_desc':
        qs = qs.annotate(min_price=Min('variants__price')).order_by('-min_price')
    else:
        qs = qs.order_by('-created_at')

    return render(request, 'product/shop.html', {
        'products': qs,
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

    related = (
        Product.objects.filter(category=product.category)
        .exclude(id=product.id)
        .prefetch_related('images', 'variants')[:4]
    )

    return render(request, 'product/item.html', {
        'product': product,
        'colours': colours,
        'sizes': sizes,
        'unavailable_sizes': unavailable_sizes,
        'selected_variant': selected_variant,
        'related': related,
    })
