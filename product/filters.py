"""The owner's filter groups, on the shop (§17 #404).

Phase 23 part G. What the shop shows beside the size, and how a choice in the
address narrows the list, decided here and nowhere else, so the shop, its
tests and the panel's hints cannot disagree:

* a group is shown when it is switched on, with its items that are switched
  on and that at least one product on sale carries. An item no design on sale
  has would answer "nothing found", which is a filter that only ever empties
  the page;
* the address carries a group's choices under the group's slug,
  ``?rang=qora&rang=oq&turkum=futbolka``. Within a group the items are
  alternatives; across groups they narrow each other;
* a choice the shop does not show (a switched-off item, a mistyped slug) is
  ignored rather than emptying the list.
"""
from django.utils.text import slugify

from .models import RESERVED_FILTER_SLUGS, FilterGroup, FilterItem, Product


def shown():
    """The groups the shop shows, in order, each with its items: ``[(group, [item])]``."""
    on_sale = Product.objects.filter(is_active=True, variants__available=True)
    items = (FilterItem.objects
             .filter(is_active=True, group__is_active=True, products__in=on_sale)
             .select_related('group').distinct()
             .order_by('group__sort_order', 'group__pk', 'sort_order', 'pk'))
    groups = []
    for item in items:
        if not groups or groups[-1][0].pk != item.group_id:
            groups.append((item.group, []))
        groups[-1][1].append(item)
    return groups


def chosen(groups, query):
    """What the address chooses, among what is shown: ``[(group, [item])]``.

    ``query`` is the request's GET. A group with nothing chosen is left out.
    """
    picked = []
    for group, items in groups:
        wanted = set(query.getlist(group.slug))
        mine = [item for item in items if item.slug in wanted]
        if mine:
            picked.append((group, mine))
    return picked


def narrow(products, choice):
    """``products`` narrowed by ``choice``: any item of a group, every group.

    One ``filter`` per group, which joins the items once for each group: the
    product must carry one of this group's items *and* one of that group's.
    """
    for _group, items in choice:
        products = products.filter(filter_items__in=items)
    return products.distinct() if choice else products


def free_slug(name, taken, fallback):
    """A slug from the Uzbek name, never one already ``taken`` or reserved.

    ``slugify`` drops the Uzbek modifier letters (oʻ, gʻ), which is the address
    we want. ``taken`` is the set of slugs in use where this one must be
    unique: every group's, or the items' of one group.
    """
    base = (slugify(name, allow_unicode=False) or fallback)[:55]
    slug, n = base, 1
    while slug in taken or slug in RESERVED_FILTER_SLUGS:
        n += 1
        slug = '%s-%d' % (base[:50], n)
    return slug


def new_group(name, name_ru='', name_en=''):
    """Make a group, switched off, its slug made once from its name."""
    taken = set(FilterGroup.objects.values_list('slug', flat=True))
    last = FilterGroup.objects.order_by('-sort_order').values_list('sort_order', flat=True).first()
    return FilterGroup.objects.create(
        name=name, name_ru=name_ru, name_en=name_en,
        slug=free_slug(name, taken, 'filtr'), sort_order=(last or 0) + 1)


def new_item(group, name, name_ru='', name_en='', colour=''):
    """Make an item in ``group``, switched on, its slug unique within the group."""
    taken = set(group.items.values_list('slug', flat=True))
    last = group.items.order_by('-sort_order').values_list('sort_order', flat=True).first()
    return FilterItem.objects.create(
        group=group, name=name, name_ru=name_ru, name_en=name_en, colour=colour,
        slug=free_slug(name, taken, 'element'), sort_order=(last or 0) + 1)
