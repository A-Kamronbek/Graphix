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

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _
from PIL import Image, UnidentifiedImageError

#: Long edge, in pixels. The largest a review photo is ever shown is a lightbox
#: on a laptop; 1600 covers that with room to spare and turns a 4 MB phone
#: photograph into something around 200 KB.
MAX_EDGE = 1600

#: Refused before decoding. A 20 MB upload is either a mistake or an attack,
#: and either way the answer is the same.
MAX_BYTES = 12 * 1024 * 1024

#: What a phone or a laptop actually produces. Anything else is refused rather
#: than converted: SVG is scriptable, and a PDF is not a photograph.
ALLOWED = {'JPEG', 'PNG', 'WEBP', 'HEIF', 'HEIC', 'MPO'}

JPEG_QUALITY = 82


def sanitise(upload, name_hint='review'):
    """Return ``upload`` as a clean JPEG :class:`ContentFile`.

    Raises :class:`~django.core.exceptions.ValidationError` with a translated,
    customer-facing message if the file is not an image we accept.
    """
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
        probe.verify()
        fmt = probe.format
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError(
            _('Faylni rasm sifatida oʻqib boʻlmadi.'), code='not_an_image')

    if fmt not in ALLOWED:
        raise ValidationError(
            _('Bu rasm turi qoʻllab-quvvatlanmaydi. JPEG yoki PNG yuboring.'),
            code='bad_format')

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

        image.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)

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
