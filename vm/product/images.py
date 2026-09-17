"""Make a customer's photo safe to put on a public page.

A review photo is a stranger's file, taken on a phone, going onto a page anyone
can read. Three things have to happen to it before it is stored, and the order
matters:

1. **Prove it is an image at all.** An upload named ``photo.jpg`` is a name, not
   a fact. Pillow is asked to decode it; anything it refuses is refused here.
2. **Shrink it.** A modern phone photograph is several thousand pixels wide and
   several megabytes. Nothing on the site displays one larger than a card.
3. **Strip the metadata — the reason this module exists.** A phone writes GPS
   coordinates into EXIF by default. Publishing a customer's review with the
   latitude and longitude of their home attached is a privacy breach committed
   by accident, and it is invisible: the page looks perfectly normal.

The stripping is done by *re-encoding* rather than by deleting tags. Deleting
the tags you know about leaves the ones you do not — EXIF, XMP, IPTC, maker
notes — and a new camera can invent a new one. Decoding to pixels and writing a
fresh file cannot carry any of it, because the pixels are all that survives.

Pillow only; it is already a dependency (``ImageField`` requires it) and §4
forbids new ones.
"""
import io
import logging

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

#: Long edge, in pixels. The largest a review photo is ever shown is a lightbox
#: on a laptop; 1600 covers that with room to spare and turns a 4 MB phone
#: photograph into something around 200 KB.
MAX_EDGE = 1600

#: Refused before decoding. A 20 MB upload is either a mistake or an attack,
#: and either way the answer is the same.
MAX_BYTES = 12 * 1024 * 1024

#: Refused before decoding, and the more important of the two limits.
#: ``MAX_BYTES`` bounds the *file*; this bounds the *picture*, and the two are
#: not related. A 12 000 x 12 000 PNG of one flat colour is 140 KB on the wire
#: and 432 MB of pixels once decoded — a decompression bomb that walks straight
#: past a size check. Pillow's own `MAX_IMAGE_PIXELS` does not stop it either:
#: it only *warns* at 89 Mpx and raises at twice that, so 144 Mpx of RAM per
#: upload was reachable by anyone with a delivered order. 50 Mpx is eight times
#: the largest phone sensor sold.
MAX_PIXELS = 50_000_000

#: What a phone or a laptop actually produces, restricted to what this Pillow
#: can actually decode — checked, not assumed. HEIC is what an iPhone stores
#: natively and it is *not* in this list, because Pillow has no HEIF codec
#: without `pillow-heif` and §4 forbids adding one; iOS transcodes to JPEG on
#: upload through a file input, which is the path a customer takes. Anything
#: not listed is refused rather than converted: SVG is scriptable, and a PDF is
#: not a photograph.
ALLOWED = {'JPEG', 'PNG', 'WEBP', 'AVIF', 'MPO'}

JPEG_QUALITY = 82


#: The long edge for a product photograph. Larger than a review's, because
#: this is the biggest thing on the product page — `--pdp-image-max` is
#: `min(76vh, 760px)`, which is about 1520 px on a 2× screen — and it is the
#: one image on the site that is meant to be looked at closely (§8).
PRODUCT_MAX_EDGE = 2000


def sanitise(upload, name_hint='review', max_edge=None):
    """Return ``upload`` as a clean JPEG :class:`ContentFile`.

    ``max_edge`` defaults to :data:`MAX_EDGE`, which suits a review photo; the
    panel passes :data:`PRODUCT_MAX_EDGE` for catalogue photography. Everything
    else — the size and pixel limits, the format check, and the re-encode that
    strips the metadata — is the same either way, which is the point: one
    pipeline, so a photograph uploaded by the owner is cleaned exactly like one
    uploaded by a customer.

    Raises :class:`~django.core.exceptions.ValidationError` with a translated,
    customer-facing message if the file is not an image we accept.
    """
    edge = max_edge or MAX_EDGE
    size = getattr(upload, 'size', None)
    if size is not None and size > MAX_BYTES:
        raise ValidationError(
            _('Rasm hajmi 12 MB dan oshmasligi kerak.'), code='too_big')

    data = upload.read()
    upload.seek(0)

    # Decode twice, deliberately. `verify()` checks the file is intact but
    # leaves the image unusable afterwards, which is documented Pillow
    # behaviour, so the real work reopens it from the same bytes.
    try:
        probe = Image.open(io.BytesIO(data))
        # Read the dimensions from the header *before* verify(), which leaves
        # the object unusable, and before anything decodes a pixel.
        pixels = probe.size[0] * probe.size[1]
        probe.verify()
        fmt = probe.format
    except Image.DecompressionBombError:
        # Pillow's own ceiling, hit before ours. Same answer, said properly:
        # the file is a real image, it is just an absurd one.
        raise ValidationError(
            _('Rasm juda katta. Kichikroq rasm yuboring.'), code='too_many_pixels')
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError(
            _('Faylni rasm sifatida oʻqib boʻlmadi.'), code='not_an_image')

    if fmt not in ALLOWED:
        raise ValidationError(
            _('Bu rasm turi qoʻllab-quvvatlanmaydi. JPEG yoki PNG yuboring.'),
            code='bad_format')

    # The header is a claim, but it is a claim that has to be true for the file
    # to decode — so refusing on it costs nothing and spends no memory.
    if pixels > MAX_PIXELS:
        raise ValidationError(
            _('Rasm juda katta. Kichikroq rasm yuboring.'), code='too_many_pixels')

    try:
        image = Image.open(io.BytesIO(data))
        # Honour the orientation tag before discarding it, or a photograph taken
        # sideways is stored sideways: the tag is the only thing that was
        # holding it upright.
        image = _apply_orientation(image)
        # Flatten transparency onto white rather than letting RGBA fail to save
        # as JPEG. A review photo with an alpha channel is a screenshot.
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGBA')
            flat = Image.new('RGB', image.size, (255, 255, 255))
            flat.paste(image, mask=image.split()[-1])
            image = flat
        elif image.mode != 'RGB':
            image = image.convert('RGB')

        image.thumbnail((edge, edge), Image.LANCZOS)

        out = io.BytesIO()
        # No `exif=` argument and no `icc_profile`: what is not passed is not
        # written, which is the entire mechanism.
        image.save(out, format='JPEG', quality=JPEG_QUALITY, optimize=True,
                   progressive=True)
    except (OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError(
            _('Rasmni qayta ishlab boʻlmadi. Boshqa rasm yuboring.'),
            code='unprocessable')

    return ContentFile(out.getvalue(), name=f'{name_hint}.jpg')


# --------------------------------------------------------------- renditions
# Phase 9. A photograph is stored once, at full size, and delivered as WebP at
# the width the screen in front of it actually needs. The originals in
# `media/products/` run to 3.8 MB, which is fifteen times the whole budget for
# one image (§5), and the owner and his customers both upload straight from
# phones - so this is not a nicety, it is the difference between a catalogue
# that loads on mobile data and one that does not.

#: The widths written for every photograph, smallest first. A card is never
#: wider than 300 px and the product page's frame is 608 px, so 400 and 800
#: cover ordinary screens at 1x and 2x; 1600 is what a 3x phone asks for and
#: what the full-screen viewer opens.
RENDITION_WIDTHS = (400, 800, 1600)

#: Renditions live one folder below the originals - `products/a.jpg` becomes
#: `products/w/a-800.webp`. `upload_to` writes originals straight into
#: `products/` and `reviews/`, so nothing else can land in here and a derived
#: name can never collide with a file somebody uploaded.
RENDITION_DIR = 'w'

#: Encoder effort, 0-6. Pillow's default; 6 is about 5 % smaller and several
#: times slower, and this runs while the owner waits for an upload to finish.
WEBP_METHOD = 4

#: §5 caps the largest image delivered at 250 KB. Quality is stepped down until
#: the file fits rather than left at one number and hoped for: a dense design at
#: 1600 px does not fit at 82, and a flat one wastes bytes below it.
RENDITION_BUDGET = 250 * 1024
#: 48 is the floor, not a target. Below it a photograph starts to look like a
#: photograph of a photograph, and a picture nobody wants to look at is not a
#: saving. A source detailed enough to miss the budget even here keeps the
#: smallest file rather than being refused.
QUALITY_STEPS = (80, 72, 64, 56, 48)


def rendition_name(original, width):
    """The stored name of one rendition of the stored file ``original``."""
    head, _, tail = original.rpartition('/')
    stem = tail.rsplit('.', 1)[0]
    leaf = f'{RENDITION_DIR}/{stem}-{width}.webp'
    return f'{head}/{leaf}' if head else leaf


def rendition_widths(source_width):
    """Which widths to write for a photograph this wide.

    Never upscales: a 900 px photograph is written at 400, 800 and 900, not at
    1600, because the extra pixels would be invented ones that cost bytes.
    """
    return sorted({min(width, source_width) for width in RENDITION_WIDTHS})


def build_renditions(fieldfile):
    """Measure a stored photograph, write its renditions, and describe them.

    Returns ``(width, height, {'src': name, 'w': [[width, name], ...]})``, or
    ``None`` if the file could not be read at all.

    Never raises. It runs after an upload has already been accepted and after
    its row has been committed: a photograph that cannot be re-encoded is a
    photograph served at full size, which is slow, and not an error page, which
    is broken. The one caller that wants to know is the backfill command, and a
    ``None`` tells it.
    """
    name = getattr(fieldfile, 'name', '') or ''
    if not name:
        return None
    storage = fieldfile.storage
    try:
        with storage.open(name, 'rb') as handle:
            data = handle.read()
        with Image.open(io.BytesIO(data)) as opened:
            # Everything happens inside the `with`: `exif_transpose` may hand
            # back the same object, and using it after the file is closed is an
            # error that only shows up on some formats.
            source = _apply_orientation(opened)
            if source.mode in ('RGBA', 'LA', 'P'):
                # Alpha survives into WebP rather than being flattened: the page
                # ground is dark and a white box behind a cut-out would show.
                source = source.convert('RGBA')
            elif source.mode != 'RGB':
                source = source.convert('RGB')
            width, height = source.size
            written = []
            for target in rendition_widths(width):
                if target == width:
                    frame = source
                else:
                    frame = source.resize(
                        (target, max(1, round(height * target / width))), Image.LANCZOS)
                written.append([target, _store(storage, rendition_name(name, target),
                                               _encode_webp(frame))])
    except Exception:
        logger.exception('could not build the renditions of %s', name)
        return None
    return width, height, {'src': name, 'w': written}


def measure(fieldfile):
    """``(width, height)`` of a stored image, or ``None``. Never raises.

    Header only - Pillow reads the size without decoding a pixel - so this is
    cheap enough to run on every save of a row that holds an image.
    """
    name = getattr(fieldfile, 'name', '') or ''
    if not name:
        return None
    try:
        with fieldfile.storage.open(name, 'rb') as handle:
            with Image.open(handle) as opened:
                return opened.size
    except Exception:
        logger.exception('could not measure %s', name)
        return None


def measure_path(path):
    """``(width, height)`` of an image on disk, or ``None``. Never raises.

    For the files that are not in storage at all - the drawn size guide is a
    static asset the owner replaces by hand.
    """
    try:
        with Image.open(path) as opened:
            return opened.size
    except Exception:
        logger.exception('could not measure %s', path)
        return None


def _encode_webp(image):
    """``image`` as WebP bytes, at the highest quality that fits the budget."""
    blob = b''
    for quality in QUALITY_STEPS:
        out = io.BytesIO()
        image.save(out, format='WEBP', quality=quality, method=WEBP_METHOD)
        blob = out.getvalue()
        if len(blob) <= RENDITION_BUDGET:
            break
    return blob


def _store(storage, name, blob):
    """Write ``blob`` at exactly ``name`` and return the name it went to.

    Not ``storage.save`` alone: that renames around a name already taken, and
    these names are derived from the original's rather than chosen - so the
    second build of the same photograph would write `a-800_Xk3d1.webp` and
    leave the page pointing at a file nothing refreshes.
    """
    if storage.exists(name):
        storage.delete(name)
    return storage.save(name, ContentFile(blob))


def _apply_orientation(image):
    """Rotate by the EXIF orientation tag, if there is one.

    Pillow ships ``ImageOps.exif_transpose`` for this; it is called through a
    guard because a corrupt EXIF block should cost the orientation, not the
    upload.
    """
    try:
        from PIL import ImageOps
        return ImageOps.exif_transpose(image) or image
    except Exception:
        return image


def has_metadata(path_or_file):
    """True if the file still carries EXIF. Used by the tests, not by the site.

    The guarantee this module exists to provide is worth asserting directly
    rather than inferring from the absence of a crash.
    """
    with Image.open(path_or_file) as image:
        exif = image.getexif()
        return bool(exif) or bool(image.info.get('exif'))
