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
    # A non-breaking space, so "185 000 soʻm" can never be split across two
    # lines by a narrow card or a footer column.
    return f"{n:,}".replace(",", "\u00a0")