from .models import Cart


def cart_count(request):
    if not request.user.is_authenticated:
        return {'cart_count': 0}
    cart = Cart.objects.filter(user=request.user, status=True).first()
    if not cart:
        return {'cart_count': 0}
    count = sum(cart.cart_items.values_list('quantity', flat=True))
    return {'cart_count': count}
