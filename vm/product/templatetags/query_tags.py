from django import template

register = template.Library()


class QueryDictFallback(dict):
    def urlencode(self):
        from urllib.parse import urlencode
        return urlencode(self)


@register.simple_tag(takes_context=True)
def query_transform(context, **kwargs):
    request = context.get('request')
    params = request.GET.copy() if request else QueryDictFallback()

    for key, value in kwargs.items():
        if value in (None, ''):
            params.pop(key, None)
        else:
            params[key] = value

    params.pop('page', None)

    encoded = params.urlencode()
    if encoded:
        return '?' + encoded
    return request.path if request else '?'

