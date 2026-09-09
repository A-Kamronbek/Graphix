# Phase 2 — design directions

## What is here

| File | What it is |
|---|---|
| `directions.html` | **The three directions.** One self-contained file — open it in any browser, no server, no network. Switch between A / B / C and between 390 px and desktop. Each direction renders in an iframe at its true width, so the media queries really run. |
| `typeface-screening.md` | Which typefaces can actually set Uzbek, and the evidence. Read this before proposing a face. |
| `mockup/` | The garment-mockup generator. |

## The garment mockups are drawn, not photographed

There is no product photography yet (`media/products/` holds an AI-generated graphic, a paper
texture and a Minecraft thumbnail). Kamronbek chose to proceed with rendered mockups so the
directions could be judged on layout and typography now, rather than waiting.

**What that means when you look at them:** proportions, crop, hierarchy and type are real and
judgeable. "Does this shop look professional" is *not* — that question belongs to the photography,
and the plan is explicit that no CSS rescues bad photos (§8).

Every garment is replaced by a real photograph before launch. Phase 11 is gated on it.

## Regenerating the mockups

```bash
pip install pillow cairosvg fonttools
python build.py          # writes out/*.jpg and out/catalogue.json
```

`gen.py` draws the garment (silhouette, fabric shading, paper backdrop, 4:5 crop), `prints.py`
holds the eight print designs, `build.py` composes the catalogue. The prints are original work
made for this mockup — no real brands, marks or characters.

To swap in real photography, drop the shots in and skip `gen.py` entirely; only the 4:5 crop and
the consistent background matter to the directions.
