"""Generate flat-lay garment mockups for the Phase 2 design directions.

Drawn, not photographed. The point is to give the three directions a real garment
silhouette, a consistent 4:5 crop and a consistent background, so layout and
typography can be judged properly. Real photography replaces all of it (§8).
"""
import math, random, io, os
import cairosvg
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

S = 1400                      # working square
FONTS = "/tmp/fonts"
PAPER = "/mnt/user-data/uploads/ValleyMade/vm/media/products/photo-1601662528567-526cd06f6582.avif"

SHIRT = (
 "M 402,114 C 402,86 444,70 500,70 C 556,70 598,86 598,114 "
 "C 652,120 706,136 754,162 L 934,268 "
 "C 946,275 948,288 940,299 L 872,392 "
 "C 863,404 849,406 838,398 L 770,348 "
 "C 756,338 746,344 746,362 L 746,874 "
 "C 746,898 730,912 704,912 L 296,912 "
 "C 270,912 254,898 254,874 L 254,362 "
 "C 254,344 244,338 230,348 L 162,398 "
 "C 151,406 137,404 128,392 L 60,299 "
 "C 52,288 54,275 66,268 L 246,162 "
 "C 294,136 348,120 402,114 Z"
)
COLLAR = ("M 402,114 C 402,86 444,70 500,70 C 556,70 598,86 598,114 "
          "C 598,158 554,184 500,184 C 446,184 402,158 402,114 Z")


def _svg(markup, w=S):
    png = cairosvg.svg2png(bytestring=markup.encode(), output_width=w, output_height=w)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def shirt_mask():
    return _svg(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">'
                f'<path d="{SHIRT}" fill="#fff"/></svg>').split()[3]


def fabric(colour, seed=0):
    """Flat colour + soft folds + edge shading, clipped to the garment.

    Shading is applied as a *signed offset* on top of the base colour, not a
    multiply: a near-black garment has no headroom downwards, so multiplying just
    produces a flat silhouette. Adding and subtracting light works on both a black
    and an off-white tee with the same numbers.
    """
    import numpy as np
    rnd = random.Random(seed)
    mask = shirt_mask()

    shade = Image.new("L", (S, S), 128)
    d = ImageDraw.Draw(shade)
    d.ellipse([S*0.16, S*0.08, S*0.88, S*0.74], fill=150)
    d.ellipse([S*0.28, S*0.14, S*0.74, S*0.54], fill=168)
    d.rectangle([0, S*0.78, S, S], fill=104)
    d.ellipse([S*0.00, S*0.12, S*0.32, S*0.36], fill=108)
    d.ellipse([S*0.68, S*0.12, S*1.00, S*0.36], fill=108)
    for _ in range(9):
        x = rnd.uniform(S*0.22, S*0.78)
        w = rnd.uniform(S*0.010, S*0.032)
        v = rnd.choice([100, 108, 150, 160])
        d.polygon([(x, S*0.14), (x+w, S*0.14),
                   (x+w*rnd.uniform(.3,2.0), S*0.92), (x, S*0.92)], fill=v)
    shade = shade.filter(ImageFilter.GaussianBlur(S*0.026))

    lum = np.asarray(shade, dtype=np.float32) - 128.0
    strength = 0.62 if colour[0] < 128 else 0.42
    rgb = np.zeros((S, S, 3), dtype=np.float32)
    for i, c in enumerate(colour):
        rgb[..., i] = np.clip(c + lum*strength, 0, 255)

    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(Image.fromarray(rgb.astype("uint8")), (0, 0), mask)

    col = _svg(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">'
               f'<path d="{COLLAR}" fill="none" stroke="#fff" stroke-width="12"/></svg>')
    tint = Image.new("RGBA", (S, S), (255, 255, 255, 40) if colour[0] < 128 else (0, 0, 0, 30))
    out.alpha_composite(Image.composite(tint, Image.new("RGBA", (S, S), (0,0,0,0)), col.split()[3]))
    return out


def apply_print(garment, art, box=(0.50, 0.235, 0.42, 0.42)):
    """Drop artwork onto the chest, softened so it sits in the cloth.

    `box` is (centre-x, top-y, max-width, max-height) as fractions of the canvas.
    The garment body spans x 25.4%-74.6%, so a 36%-wide print centred at 50% clears
    both side seams.
    """
    cx, top, w, h = box
    art = art.copy()
    art.thumbnail((int(S*w), int(S*h)), Image.LANCZOS)
    art = art.filter(ImageFilter.GaussianBlur(0.6))
    art.putalpha(art.split()[3].point(lambda v: int(v*0.93)))

    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    layer.alpha_composite(art, (int(S*cx - art.width/2), int(S*top)))
    layer.putalpha(ImageChops.multiply(layer.split()[3], garment.split()[3]))
    out = garment.copy(); out.alpha_composite(layer)
    return out


def on_paper(garment, ratio=(4, 5), pad=0.055):
    """Place the garment on the paper backdrop in a consistent 4:5 crop."""
    h = int(S*1.18); w = int(h*ratio[0]/ratio[1])
    paper = Image.open(PAPER).convert("RGB").resize((w, h), Image.LANCZOS)
    paper = ImageChops.multiply(paper, Image.new("RGB", (w, h), (247, 245, 241)))
    bg = paper

    g = garment.copy()
    gw = int(w*(1 - pad*2)); g = g.resize((gw, gw), Image.LANCZOS)
    ox, oy = (w - gw)//2, (h - gw)//2

    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh.paste(Image.new("RGBA", (gw, gw), (60, 55, 48, 62)), (ox+int(gw*0.012), oy+int(gw*0.020)), g.split()[3])
    sh = sh.filter(ImageFilter.GaussianBlur(gw*0.020))
    out = bg.convert("RGBA"); out.alpha_composite(sh); out.alpha_composite(g, (ox, oy))
    return out.convert("RGB")
