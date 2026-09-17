"""Storefront views: the shop listing (search / filter / sort), product detail,
and the heart."""
import json

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Exists, Min, OuterRef, Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from core import seo
from core.i18n import tfield
from core.ratelimit import is_rate_limited, RATE_LIMIT_MESSAGE
from . import images, services
from .models import (Category, Colour, Product, ProductLike, Review, Size, Tag,
                     TagKind, Variant)


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
        # Built from the rows rather than from a fixed list of choices, so an
        # axis the owner adds appears here on its own (§17, Phase 7 recheck).
        # An axis with no tags on it yet is left out: an empty filter group is
        # a heading with nothing under it.
        'tag_groups': [
            (kind, list(kind.tags.all()))
            for kind in TagKind.objects.prefetch_related('tags')
            if kind.tags.exists()
        ],
        'selected_category': category,
        'selected_size': size,
        'selected_tags': tags,
        'filter_count': len(tags) + (1 if category else 0) + (1 if size else 0),
        'q': q,
        'sort': sort,
        'search_page': search_page,
        # The catalogue's own trail. Not on the search page: a results page is
        # noindex, and structured data on a page nobody may index is markup
        # nothing will ever read.
        'jsonld': None if search_page else seo.payload(seo.breadcrumbs(request, [
            (_('Bosh sahifa'), reverse('home')),
            (_('Doʻkon'), None),
        ])),
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
        **_reviews(request, product),
        'jsonld': _product_jsonld(request, product),
        'colours': colours,
        'sizes': sizes,
        'unavailable_sizes': unavailable_sizes,
        'selected_variant': selected_variant,
        'is_purchasable': is_purchasable,
        'variants_json': json.dumps(variants_map),
        'size_chart': product.resolve_size_chart(),
        # The drawn chart comes from the context processor, which is also what
        # the standalone page and the footer link read - so the two pages can
        # never show different files (§17 #111).
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


# ------------------------------------------------------------------ reviews

#: Reviews per page on the product detail page.
REVIEWS_PER_PAGE = 5


def _reviews(request, product):
    """The approved reviews for the product page, and the numbers beside them.

    Approved only — a pending review is invisible to everyone including the
    person who wrote it, on the page. Paginated on its own query parameter so
    a link to page three of the reviews is still a link to the product.
    """
    approved = (Review.objects
                .filter(product=product, status=Review.Status.APPROVED)
                .select_related('user')
                .prefetch_related('images'))

    # The distribution bars. One grouped query rather than five counts, and
    # read from the same rows the list is drawn from.
    counts = dict(approved.values_list('rating').annotate(n=Count('id')))
    # The denominator is the sum of those rows, not `product.review_count`.
    # They are kept in step by `recompute_rating` and should always agree — but
    # if they ever did not, dividing live counts by a stale total would draw
    # bars that add up to more or less than the whole, which is the one thing a
    # distribution must never do.
    total = sum(counts.values())
    distribution = [
        {
            'stars': stars,
            'count': counts.get(stars, 0),
            # Width as a percentage, computed here because a template cannot
            # divide. Zero reviews means zero bars, not a division by zero.
            'percent': round(counts.get(stars, 0) * 100 / total) if total else 0,
        }
        for stars in (5, 4, 3, 2, 1)
    ]

    page = Paginator(approved, REVIEWS_PER_PAGE).get_page(request.GET.get('sharh'))
    return {'reviews': page, 'review_distribution': distribution}


def _money(amount):
    """A price as schema.org wants it: a number, as a string, no thousands mark."""
    return format(amount.normalize(), 'f') if amount == amount.to_integral() else str(amount)


def _offers(request, product, url):
    """The `offers` node: what this product costs and whether it can be bought.

    One `Offer` when every size is the same price, which is the ordinary case
    here, and an `AggregateOffer` when they are not - a range is the honest
    answer, and a single price picked out of several is the kind of mismatch
    between markup and page that earns a manual action (§18 #22).

    Availability is purchasability, not the owner's switch: a size still listed
    but out of stock cannot be bought, and that is what a shopping result is
    telling somebody when it says "in stock".
    """
    variants = list(product.variants.all())
    prices = sorted({v.price for v in variants if v.available})
    if not prices:
        return None
    common = {
        'priceCurrency': 'UZS',
        'availability': ('https://schema.org/InStock'
                         if any(v.is_purchasable for v in variants)
                         else 'https://schema.org/OutOfStock'),
        'itemCondition': 'https://schema.org/NewCondition',
        'url': url,
        'seller': {'@id': seo.absolute(request, '/') + '#shop'},
    }
    if len(prices) > 1:
        return {'@type': 'AggregateOffer', 'lowPrice': _money(prices[0]),
                'highPrice': _money(prices[-1]),
                'offerCount': len([v for v in variants if v.available]), **common}
    return {'@type': 'Offer', 'price': _money(prices[0]), **common}


def _review_nodes(product):
    """`aggregateRating` and `review`, or nothing at all.

    What puts star ratings in a Google result, which is why the plan calls it an
    acquisition win rather than a nicety (§9 Phase 12 item 7). Emitted only when
    there is something true to say: schema.org requires `aggregateRating` to
    describe at least one real review, and a product with none must not claim
    one.
    """
    if not product.review_count:
        return {}
    approved = (Review.objects
                .filter(product=product, status=Review.Status.APPROVED)
                .select_related('user')[:20])
    return {
        'aggregateRating': {
            '@type': 'AggregateRating',
            'ratingValue': str(product.rating_avg),
            'reviewCount': product.review_count,
            'bestRating': '5',
            'worstRating': '1',
        },
        'review': [
            {
                '@type': 'Review',
                'reviewRating': {'@type': 'Rating', 'ratingValue': str(r.rating),
                                 'bestRating': '5', 'worstRating': '1'},
                'author': {'@type': 'Person', 'name': r.user.get_short_name()
                           or r.user.username},
                'datePublished': r.created_at.date().isoformat(),
                **({'reviewBody': r.text} if r.text else {}),
            }
            for r in approved
        ],
    }


def _product_jsonld(request, product):
    """The whole of what this page says to a search engine, in one graph.

    Phase 12 shipped the rating and the reviews, which is everything a review
    snippet needs; Google also wants `offers` on a `Product` node and reports a
    warning on every page without one (§18 #22). The trail comes with it: the
    breadcrumb in a result is the shop's own navigation, and it is already on
    the page for a reader.
    """
    url = seo.absolute(request, product.get_absolute_url())
    description = tfield(product, 'description') or ''
    node = {
        '@type': 'Product',
        'name': tfield(product, 'name'),
        'url': url,
        # The slug, not the id: it is the stable public name of this design,
        # and it is what a purchase order or a support message would quote.
        'sku': product.slug,
        'brand': {'@type': 'Brand', 'name': 'GRAPHIX'},
        'image': [seo.absolute(request, image.zoom_url())
                  for image in product.images.all()[:4] if image.has_photo],
    }
    if description:
        node['description'] = description
    offers = _offers(request, product, url)
    if offers:
        node['offers'] = offers
    node.update(_review_nodes(product))

    trail = [(_('Bosh sahifa'), reverse('home')), (_('Doʻkon'), reverse('shop'))]
    if product.category:
        trail.append((tfield(product.category, 'name'),
                      '%s?category=%d' % (reverse('shop'), product.category_id)))
    trail.append((tfield(product, 'name'), None))
    return seo.payload(node, seo.breadcrumbs(request, trail))


@login_required
def review_create(request, order_id):
    """Write a review for something in a delivered order.

    One page per order rather than per product, because that is how a customer
    thinks about it: the parcel arrived, and it had things in it. An order with
    three products shows three forms; the common case shows one.

    Eligibility is decided by ``services.check_may_review`` and nothing here
    duplicates it — this view only chooses what to render and what to say.
    """
    from payment.models import Order
    order = get_object_or_404(Order, pk=order_id, user=request.user)

    #: What the customer typed, ready to go back onto the page if the
    #: submission is refused. A redirect would throw it away, and a rejected
    #: photograph must not cost somebody the paragraph they just wrote — §17
    #: #118 says a form re-rendered after an error is put back into the state
    #: it was in. The one thing that cannot come back is the file input: no
    #: browser lets a page refill one, for good reasons.
    submitted = {}

    if request.method == 'POST':
        product = get_object_or_404(Product, pk=_int(request.POST.get('product')),
                                    is_active=True)
        rating = _int(request.POST.get('rating'))
        text = (request.POST.get('text') or '').strip()
        submitted = {'product': product.pk, 'rating': rating, 'text': text}

        error, photos = None, []
        # First, and before anything reads a file. Every other write on the
        # site is rate limited (the heart, the OTPs, the password reset); this
        # one accepts four uploads of up to 12 MB each and re-encodes them, so
        # a refused submission retried in a loop is the expensive case.
        if is_rate_limited(request, 'review', 10, 3600, ident=f"u{request.user.pk}"):
            error = RATE_LIMIT_MESSAGE
        elif rating not in (1, 2, 3, 4, 5):
            error = _("Bahoni tanlang.")
        elif len(text) > MAX_TEXT:
            # The textarea carries `maxlength` too, but that is a convenience
            # in a browser and not a limit: the field behind it is a TextField
            # and the POST does not have to come from our page.
            error = _("Fikringiz %(n)d belgidan oshmasligi kerak.") % {'n': MAX_TEXT}
        else:
            try:
                services.check_may_review(request.user, order, product)
                photos = _clean_photos(request.FILES.getlist('photos'))
            except services.NotEligible:
                error = _("Bu mahsulotga sharh qoldirib boʻlmaydi.")
            except ValidationError as exc:
                error = exc.messages[0]

        if error is None:
            services.create_review(request.user, order, product, rating,
                                   text=text, photos=photos)
            messages.success(
                request,
                _("Sharhingiz uchun rahmat. U koʻrib chiqilgandan keyin "
                  "sahifada paydo boʻladi."))
            return redirect('order_detail', pk=order.pk)
        messages.error(request, error)

    return render(request, 'product/review_form.html', {
        'order': order,
        # Read after the POST, so a refusal re-renders against the current
        # state rather than against a list built before anything happened.
        'rows': services.reviewable(request.user, order),
        'can_review': order.status == order.Status.DONE,
        'max_photos': MAX_PHOTOS,
        'max_text': MAX_TEXT,
        # Integers, 5 first — the CSS reverses the row so 1 sits on the left.
        # From here rather than from a string in the template, because the
        # label beside each star is a plural and a plural needs a number.
        'rating_choices': (5, 4, 3, 2, 1),
        'submitted': submitted,
    })


#: Four is the plan's number (§9 Phase 12 item 1). Enforced server-side; the
#: file input's `multiple` attribute is a convenience, not a limit.
MAX_PHOTOS = 4

#: Characters of free text. Long enough for anything a customer wants to say
#: about a t-shirt and short enough that a card stays a card. The template
#: reads this rather than repeating it, because a number written down twice is
#: a number that will eventually disagree with itself (§17 #111).
MAX_TEXT = 2000


def _clean_photos(uploads):
    """Sanitise every uploaded photo, or refuse the lot.

    Refusing the lot rather than silently dropping the bad one: a customer who
    attached four photographs and got three published would have no way of
    knowing which one went missing or why.
    """
    if len(uploads) > MAX_PHOTOS:
        raise ValidationError(
            _("Koʻpi bilan %(n)d ta rasm yuborish mumkin.") % {'n': MAX_PHOTOS})
    return [images.sanitise(upload, name_hint=f'review-{i + 1}')
            for i, upload in enumerate(uploads)]


def _int(raw):
    """Parse an id or a rating from a form field, or None."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
