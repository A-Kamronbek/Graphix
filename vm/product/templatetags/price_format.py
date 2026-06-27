from django import template

register = template.Library()


@register.filter(name="price")
def price(value):
    """
    Format a number with a space every 3 digits from the right.
        12000      -> "12 000"
        1234567    -> "1 234 567"
        None / ""  -> ""
    """
    if value in (None, ""):
        return ""
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return value
    return f"{n:,}".replace(",", " ")