"""Compose the mockup catalogue: eight products, consistent 4:5 flat-lays."""
import os, json
from PIL import Image
import gen, prints

BLACK = (22, 22, 22)
BONE  = (238, 235, 228)

CATALOGUE = [
    # slug,        name,             print fn,        garment, price,   seed
    ("rampage",    "Rampage",        "rampage",       BLACK, 189000, 3),
    ("overdrive",  "Overdrive",      "overdrive",     BLACK, 165000, 5),
    ("asterisk",   "Asterisk",       "asterisk",      BONE,  155000, 7),
    ("signal",     "Noise / Signal", "noise_signal",  BLACK, 175000, 11),
    ("indeks",     "Indeks 100000",  "postal",        BONE,  165000, 13),
    ("quyosh",     "Quyosh",         "arcs",          BLACK, 179000, 17),
    ("halqa",      "Halqa",          "ring",          BONE,  169000, 19),
    ("fade",       "Fade",           "dissolve",      BLACK, 185000, 23),
]

def art_for(fn, garment):
    ink = (250, 250, 250, 255) if garment[0] < 128 else (18, 18, 18, 255)
    f = getattr(prints, fn)
    return f() if fn == "rampage" else f(ink)

def build():
    meta = []
    for slug, name, fn, garment, price, seed in CATALOGUE:
        g = gen.fabric(garment, seed=seed)
        g = gen.apply_print(g, art_for(fn, garment))
        shot = gen.on_paper(g)
        shot.resize((560, 700), Image.LANCZOS).save(f"out/{slug}.jpg", quality=74, optimize=True)
        meta.append(dict(slug=slug, name=name, price=price,
                         colour="Qora" if garment[0] < 128 else "Suyak"))
        if slug == "rampage":                       # hero product gallery
            shot.resize((900, 1125), Image.LANCZOS).save("out/hero-1.jpg", quality=80, optimize=True)
            back = gen.fabric(garment, seed=seed+1)
            back = gen.apply_print(back, prints.stacked((250,250,250,255)),
                                   box=(0.50, 0.21, 0.17, 0.11))
            gen.on_paper(back).resize((900, 1125), Image.LANCZOS).save(
                "out/hero-2.jpg", quality=80, optimize=True)
            w, h = shot.size
            # Crops computed from where the garment actually sits: the square is
            # inset 5.5% and the chest print occupies 42% of it from 23.5% down.
            def crop45(cx, cy, fw):
                cw, ch = w*fw, w*fw*1.25
                x, y = w*cx - cw/2, h*cy - ch/2
                x = max(0, min(x, w-cw)); y = max(0, min(y, h-ch))
                return shot.crop((int(x), int(y), int(x+cw), int(y+ch)))
            crop45(0.50, 0.46, 0.52).resize((900, 1125), Image.LANCZOS).save(
                "out/hero-3.jpg", quality=80, optimize=True)      # the print, close
            crop45(0.50, 0.235, 0.46).resize((900, 1125), Image.LANCZOS).save(
                "out/hero-4.jpg", quality=80, optimize=True)      # collar and shoulder
    json.dump(meta, open("out/catalogue.json", "w"), indent=1)
    return meta

if __name__ == "__main__":
    m = build()
    for f in sorted(os.listdir("out")):
        print(f, round(os.path.getsize("out/"+f)/1024), "KB")
