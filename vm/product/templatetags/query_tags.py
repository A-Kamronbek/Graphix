from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def query_transform(context, **kwargs):
    """
    Merge the given key/value pairs into the CURRENT querystring instead of
    replacing it, so sidebar filters/search/sort compose together.

        <a href="{% query_transform category=c.id %}">      # keep size/sort/q, set category
        <a href="{% query_transform size=s.id %}">          # keep category/sort/q, set size
        <a href="{% query_transform sort='price_asc' %}">   # keep category/size/q, set sort
        <a href="{% query_transform size=None %}">          # remove the size param

    Passing a value of None or '' removes that key.
    'page' is always dropped, since changing a filter should return to page 1.
    """
    request = context.get('request')
    params = request.GET.copy() if request else QueryDictFallback()

    for key, value in kwargs.items():
        if value in (None, ''):
            params.pop(key, None)
        else:
            params[key] = value

    # Any filter change resets pagination.
    params.pop('page', None)

    encoded = params.urlencode()
    if encoded:
        return '?' + encoded
    # Nothing left -> point back at the bare shop URL.
    return request.path if request else '?'


class QueryDictFallback(dict):
    """Minimal stand-in if request is somehow missing from context."""
    def urlencode(self):
        from urllib.parse import urlencode
        return urlencode(self)
