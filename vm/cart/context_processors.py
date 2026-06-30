from django.db.models import Sum
from .models import Cart


def cart_count(request):
    if not request.user.is_authenticated:
        return {'cart_count': 0}
    total = (
        Cart.objects.filter(user=request.user, status=True)
        .aggregate(n=Sum('cart_items__quantity'))['n']
    )
    return {'cart_count': total or 0}
