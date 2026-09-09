"""Original print artwork for the mockup catalogue.

All designs are invented for this mockup: typographic lockups and geometric
compositions, no real brands, marks or characters. `RAMPAGE` reuses Kamronbek's
own existing graphic from media/products/.
"""
import io, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import cairosvg

F = "/tmp/fonts"
A = 1200
MARK = ("M2.3 10.75H21.7V13.25H2.3ZM5.26 2.83H8.15L18.74 21.17H15.85Z"
        "M15.85 2.83H18.74L8.15 21.17H5.26Z")


def _f(name, size, wght=None):
    f = ImageFont.truetype(f"{F}/{name}.ttf", size)
    if wght:
        try: f.set_variation_by_axes([wght])
        except Exception: pass
    return f


def _canvas():
    return Image.new("RGBA", (A, A), (0, 0, 0, 0))


def _centre(d, y, text, font, fill, track=0):
    w = sum(d.textlength(c, font=font) for c in text) + track*(len(text)-1)
    x = (A - w)/2
    for c in text:
        d.text((x, y), c, font=font, fill=fill)
        x += d.textlength(c, font=font) + track
    return w


def _hex(c):
    return "#%02x%02x%02x" % tuple(c[:3])


def mark_svg(colour, size):
    png = cairosvg.svg2png(
        bytestring=(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
                    f'<path d="{MARK}" fill="{_hex(colour)}"/></svg>').encode(),
        output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


# ---------------------------------------------------------------- designs ----

def overdrive(ink):
    im = _canvas(); d = ImageDraw.Draw(im)
    big = _f("Unbounded", 205, 800)
    _centre(d, 300, "OVER", big, ink, -6)
    _centre(d, 500, "DRIVE", big, ink, -6)
    d.rectangle([300, 745, 900, 763], fill=ink)
    _centre(d, 800, "TOSHKENT · 2026", _f("IBMPlexMono", 46), ink, 10)
    return im


def asterisk(ink):
    im = _canvas()
    m = mark_svg(ink, 620)
    im.alpha_composite(m, ((A-620)//2, 210))
    d = ImageDraw.Draw(im)
    _centre(d, 880, "GRAPHIX", _f("Unbounded", 92, 700), ink, 16)
    return im


def noise_signal(ink):
    im = _canvas(); d = ImageDraw.Draw(im)
    f = _f("Oswald", 250, 700)
    _centre(d, 250, "NOISE", f, ink, 4)
    d.rectangle([200, 560, 1000, 578], fill=ink)
    _centre(d, 620, "SIGNAL", f, ink, 4)
    return im


def postal(ink):
    im = _canvas(); d = ImageDraw.Draw(im)
    _centre(d, 250, "100000", _f("Oswald", 330, 700), ink, -4)
    _centre(d, 660, "TOSHKENT SHAHRI", _f("IBMPlexMono", 58), ink, 6)
    for i in range(6):
        x = 210 + i*136
        d.rectangle([x, 800, x+96, 816], fill=ink)
    return im


def arcs(ink):
    im = _canvas(); d = ImageDraw.Draw(im)
    for i, r in enumerate(range(120, 470, 58)):
        d.arc([A/2-r, 470-r, A/2+r, 470+r], 182, 358, fill=ink, width=20 if i % 2 else 9)
    _centre(d, 700, "QUYOSH", _f("Unbounded", 118, 700), ink, 12)
    _centre(d, 850, "GRAFIK BOSMA", _f("IBMPlexMono", 44), ink, 8)
    return im


def ring(ink):
    im = Image.new("RGBA", (A, A), (0, 0, 0, 0))
    txt = "GRAPHIX · PREMIUM · TOSHKENT · GRAPHIX · PREMIUM · TOSHKENT · "
    f = _f("Onest", 74, 700)
    R = 380
    for i, ch in enumerate(txt):
        ang = (i/len(txt))*360 - 90
        layer = Image.new("RGBA", (A, A), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((A/2, A/2 - R), ch, font=f, fill=ink, anchor="mm")
        im.alpha_composite(layer.rotate(-ang, resample=Image.BICUBIC, center=(A/2, A/2)))
    im.alpha_composite(mark_svg(ink, 300), ((A-300)//2, (A-300)//2))
    return im


def dissolve(ink):
    im = _canvas(); d = ImageDraw.Draw(im)
    import random; rnd = random.Random(11)
    cols, rows, cell = 9, 9, 96
    ox, oy = (A - cols*cell)//2, 220
    for r in range(rows):
        for c in range(cols):
            if rnd.random() < (r/rows)*0.95:
                continue
            d.rectangle([ox+c*cell, oy+r*cell, ox+c*cell+cell-12, oy+r*cell+cell-12], fill=ink)
    _centre(d, 1050, "FADE", _f("Unbounded", 96, 800), ink, 18)
    return im


def stacked(ink):
    im = _canvas(); d = ImageDraw.Draw(im)
    f = _f("Unbounded", 150, 800)
    for i, w in enumerate(["PAXTA", "200", "GSM"]):
        _centre(d, 300 + i*190, w, f, ink, 2)
    d.rectangle([340, 880, 860, 896], fill=ink)
    return im


def rampage():
    """Kamronbek's own existing graphic, cut out of its black background."""
    src = Image.open("/mnt/user-data/uploads/ValleyMade/vm/media/products/"
                     "ChatGPT_Image_Nov_20_2025_01_58_21_PM.png").convert("RGB")
    src = src.crop((150, 300, 1400, 720)).resize((A, int(A*420/1250)), Image.LANCZOS)
    lum = src.convert("L").point(lambda v: 0 if v < 26 else min(255, int((v-26)*1.9)))
    out = Image.new("RGBA", src.size); out.paste(src, (0, 0)); out.putalpha(lum)
    canvas = _canvas(); canvas.alpha_composite(out, (0, (A-out.height)//2))
    return canvas
