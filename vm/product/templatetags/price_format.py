from django import template

register = template.Library()

@register.filter(name="price")
def price(value):
    if value in (None, ""):
        return ""
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return value
    return f"{n:,}".replace(",", " ")