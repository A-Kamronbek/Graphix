"""Render one stored photograph as the attributes of a responsive ``<img>``.

Every image on the site went through the same four lines of template - an
``{% if %}`` for the missing file, the URL, a lazy flag and a fallback
``onerror`` - and Phase 9 adds three more: ``srcset``, ``sizes`` and the
intrinsic size. Seven repeated in nine templates is seven places to get wrong,
so they are written once here.

The tag deliberately does NOT emit ``alt``, ``loading`` or ``fetchpriority``.
Those are decisions about the page - what the picture means, whether it is
above the fold - and they belong where that is known.
"""
from django import template
from django.templatetags.static import static
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()

#: ``sizes`` for each place a photograph appears, mirroring the CSS that lays
#: it out. It has to be stated in the markup: the browser chooses which file to
#: fetch before a stylesheet has been parsed, so it cannot read the grid.
#: Keep in step with components.css (.card__media), pages.css (.pdp__frame,
#: .pdp__rail, .home__hero-art, .cartline__thumb) and panel.css.
SIZES = {
    # Two cards to a row, then three at 720, then four at 860, capped by the
    # 1280 container.
    'card': '(min-width: 1280px) 300px, (min-width: 860px) 23vw, (min-width: 720px) 31vw, 46vw',
    # The product page's frame: min(76vh, 760px) tall at 4:5, so 608 px wide at
    # most, and the page's own width below that.
    'pdp': '(min-width: 660px) 608px, 92vw',
    # The hero is hidden below 860 px, where it is also lazy - so a phone never
    # fetches it at all.
    'hero': '460px',
    'rail': '64px',
    'thumb': '84px',
    'review': '72px',
    'panel': '96px',
}

#: Shown when a row has no file, or when the file 404s. Its real size - the
#: drawn placeholder is square and the frame it sits in is 4:5, which
#: `object-fit: cover` handles; claiming 4:5 here would be claiming a shape the
#: file does not have.
FALLBACK = 'img/no-image.jpg'
FALLBACK_WIDTH = 360
FALLBACK_HEIGHT = 360


def _attr(name, value):
    """One HTML attribute, with its value escaped."""
    return '%s="%s"' % (name, conditional_escape(value))


@register.simple_tag
def photo_attrs(photo, where='card'):
    """``src``, ``srcset``, ``sizes``, ``width``, ``height`` and the fallback.

    ``photo`` is any row with an image on it - a product photograph, a review
    photograph, a size chart - or ``None``. A missing row and a row whose file
    is missing render the placeholder at its own size, which is why no template
    has to ask ``{% if img and img.picture %}`` any more.

    ``where`` names the place on the page, and picks the ``sizes`` for it.
    """
    placeholder = static(FALLBACK)
    if photo is None or not getattr(photo, 'has_photo', False):
        return mark_safe(' '.join([
            _attr('src', placeholder),
            _attr('width', FALLBACK_WIDTH), _attr('height', FALLBACK_HEIGHT),
        ]))

    parts = [_attr('src', photo.display_url())]
    srcset = photo.srcset()
    if srcset:
        parts.append(_attr('srcset', srcset))
        parts.append(_attr('sizes', SIZES.get(where, where)))
    if photo.width and photo.height:
        parts.append(_attr('width', photo.width))
        parts.append(_attr('height', photo.height))
    # The file can go missing - a restored database against an old media folder,
    # a half-copied deploy - and an empty frame says nothing. `srcset` has to go
    # with it: a browser that has one ignores `src` entirely, so setting the
    # source alone would leave the broken picture on the screen.
    parts.append(
        "onerror=\"this.onerror=null;this.removeAttribute('srcset');this.src='%s'\""
        % conditional_escape(placeholder))
    return mark_safe(' '.join(parts))


@register.simple_tag
def photo_zoom(photo):
    """The URL the full-screen viewer should open for this photograph."""
    if photo is None or not getattr(photo, 'has_photo', False):
        return static(FALLBACK)
    return photo.zoom_url()


@register.simple_tag
def photo_srcset(photo, where='card'):
    """``srcset`` and ``sizes`` alone, for the gallery's thumbnails.

    The rail carries the values the main image will need when a thumbnail is
    tapped, so gallery.js swaps a whole source set rather than one URL - which
    is what made the swapped-in photograph arrive at full size.
    """
    if photo is None or not getattr(photo, 'has_photo', False):
        return ''
    return photo.srcset()
