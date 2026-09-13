"""Draw the GRAPHIX size chart and render it to a PNG.

The chart has to be set in the brand's own typefaces, and those ship as
subsetted WOFF2 — which Pillow cannot read. So the chart is authored as HTML
against the real design tokens, with the fonts embedded as data URIs, and a
headless Chromium takes the picture. That also means the diagram, the table and
the type are all one document rather than three things kept in step by hand.

Output: size_guide.png (2x, so it stays sharp on a phone).
"""
import asyncio
import base64
import pathlib

HERE = pathlib.Path(__file__).parent
PLAYFAIR = (HERE / 'playfair-display-var.b64').read_text()
ONEST = (HERE / 'onest-var.b64').read_text()

ROWS = {
    'Oddiy / Regular': [
        ('S', 48, 69, 43, 19),
        ('M', 51, 71, 46, 20),
        ('L', 54, 73, 49, 21),
        ('XL', 57, 75, 52, 22),
    ],
    'Oversize': [
        ('S', 54, 70, 52, 21),
        ('M', 57, 72, 55, 22),
        ('L', 60, 74, 58, 23),
        ('XL', 63, 76, 61, 24),
    ],
}

# A tee drawn as one closed outline, in the proportions the catalogue actually
# sells: dropped shoulder, straight body, short sleeve. Traced anticlockwise
# from the left shoulder so the body and the sleeves are one piece rather than
# three shapes that happen to overlap. Viewbox 0 0 400 500.
TEE = """
<path class="tee" d="M146 92
  L66 146 L98 196 L130 170
  L126 292 Q126 300 134 300
  L266 300 Q274 300 274 292
  L270 170 L302 196 L334 146 L254 92
  Q200 128 146 92 Z"/>
<path class="tee-collar" d="M146 92 Q200 128 254 92"/>
<path class="tee-seam" d="M130 170 L136 162 M270 170 L264 162"/>
"""

# The four measured lines. Each one sits on the garment rather than beside it,
# with end caps rather than dots, so it reads as a measurement and not as
# decoration.
LINES = """
<g class="dim">
  <line x1="127" y1="182" x2="273" y2="182"/>
  <line x1="127" y1="172" x2="127" y2="192"/>
  <line x1="273" y1="172" x2="273" y2="192"/>
  <text x="200" y="176" text-anchor="middle">A</text>

  <line x1="200" y1="96" x2="200" y2="300"/>
  <line x1="190" y1="96"  x2="210" y2="96"/>
  <line x1="190" y1="300" x2="210" y2="300"/>
  <text x="211" y="240">B</text>

  <line x1="146" y1="76" x2="254" y2="76"/>
  <line x1="146" y1="66" x2="146" y2="86"/>
  <line x1="254" y1="66" x2="254" y2="86"/>
  <text x="200" y="60" text-anchor="middle">C</text>

  <line x1="258" y1="98" x2="316" y2="168"/>
  <line x1="250" y1="104" x2="266" y2="92"/>
  <line x1="308" y1="174" x2="324" y2="162"/>
  <text x="330" y="140">D</text>
</g>
"""

KEYS = [
    ('A', 'Koʻkrak', 'Грудь', 'Chest'),
    ('B', 'Uzunlik', 'Длина', 'Length'),
    ('C', 'Yelka', 'Плечо', 'Shoulder'),
    ('D', 'Yeng', 'Рукав', 'Sleeve'),
]


def table(title, rows):
    body = '\n'.join(
        f'<tr><th>{s}</th><td>{c}</td><td>{l}</td><td>{sh}</td><td>{sl}</td></tr>'
        for s, c, l, sh, sl in rows
    )
    return f"""
    <section class="chart">
      <h2>{title}</h2>
      <table>
        <thead><tr><th>Oʻlcham</th><th>A</th><th>B</th><th>C</th><th>D</th></tr></thead>
        <tbody>{body}</tbody>
      </table>
    </section>"""


HTML = f"""<!doctype html>
<html lang="uz"><head><meta charset="utf-8"><style>
@font-face {{ font-family: "Playfair Display"; font-weight: 400 900;
  src: url(data:font/woff2;base64,{PLAYFAIR}) format("woff2"); }}
@font-face {{ font-family: "Onest"; font-weight: 300 800;
  src: url(data:font/woff2;base64,{ONEST}) format("woff2"); }}

:root {{
  --c-bg: #100E0C; --c-surface: #17140F; --c-surface-2: #211C15;
  --c-fg: #EFE9DE; --c-fg-muted: #B0A697; --c-fg-hint: #958A79;
  --c-line: #2C2620; --c-line-strong: #453D31; --c-brand: #C6A44E;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ width: 1200px; background: var(--c-bg); color: var(--c-fg);
  font-family: "Onest", sans-serif; font-weight: 500; padding: 56px 56px 44px; }}

header {{ display: flex; align-items: baseline; justify-content: space-between;
  gap: 24px; padding-bottom: 20px; border-bottom: 1px solid var(--c-line-strong); }}
h1 {{ font-family: "Playfair Display", serif; font-weight: 700; font-size: 40px;
  letter-spacing: -.02em; }}
header .brand {{ font-family: "Playfair Display", serif; font-weight: 700;
  font-size: 20px; letter-spacing: .055em; color: var(--c-brand); }}

.body {{ display: grid; grid-template-columns: 420px 1fr; gap: 48px;
  padding-top: 36px; align-items: start; }}

svg {{ width: 400px; height: 270px; display: block; }}
.tee {{ fill: var(--c-surface-2); stroke: var(--c-line-strong); stroke-width: 2; }}
.tee-collar {{ fill: none; stroke: var(--c-line-strong); stroke-width: 2; }}
.tee-seam {{ fill: none; stroke: var(--c-line-strong); stroke-width: 2; }}
.dim line {{ stroke: var(--c-brand); stroke-width: 1.5; stroke-dasharray: 5 5; }}
.dim circle {{ fill: var(--c-brand); }}
.dim text {{ fill: var(--c-brand); font-family: "Onest", sans-serif;
  font-weight: 700; font-size: 17px; }}

.key {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px 20px;
  margin-top: 20px; }}
.key div {{ display: flex; gap: 10px; align-items: baseline; font-size: 15px;
  color: var(--c-fg-muted); }}
.key b {{ color: var(--c-brand); font-weight: 700; width: 14px; }}

.charts {{ display: flex; flex-direction: column; gap: 32px; }}
.chart h2 {{ font-family: "Playfair Display", serif; font-weight: 600;
  font-size: 24px; margin-bottom: 12px; }}
table {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }}
thead th {{ font-size: 12px; letter-spacing: .16em; text-transform: uppercase;
  color: var(--c-fg-hint); font-weight: 600; text-align: right;
  padding: 0 0 10px; border-bottom: 1px solid var(--c-line-strong); }}
thead th:first-child {{ text-align: left; }}
tbody th {{ text-align: left; font-weight: 700; font-size: 17px; }}
tbody td {{ text-align: right; font-size: 17px; color: var(--c-fg); }}
tbody th, tbody td {{ padding: 12px 0; border-bottom: 1px solid var(--c-line); }}
tbody tr:last-child th, tbody tr:last-child td {{ border-bottom: 0; }}

footer {{ margin-top: 36px; padding-top: 18px;
  border-top: 1px solid var(--c-line-strong); color: var(--c-fg-hint);
  font-size: 14px; line-height: 1.55; }}
</style></head><body>

<header>
  <h1>Oʻlcham jadvali</h1>
  <span class="brand">GRAPHIX</span>
</header>

<div class="body">
  <div>
    <svg viewBox="0 50 400 270" xmlns="http://www.w3.org/2000/svg">{TEE}{LINES}</svg>
    <div class="key">
      {''.join(f'<div><b>{k}</b><span>{uz} · {ru} · {en}</span></div>' for k, uz, ru, en in KEYS)}
    </div>
  </div>
  <div class="charts">
    {''.join(table(t, r) for t, r in ROWS.items())}
  </div>
</div>

<footer>
  Oʻlchamlar kiyim tekis yotqizilgan holda, santimetrda olingan · ±1 sm farq boʻlishi mumkin<br>
  Замеры сняты с изделия на плоскости, в сантиметрах · допуск ±1 см<br>
  Measured flat, in centimetres · allow ±1 cm
</footer>
</body></html>"""


async def main():
    from playwright.async_api import async_playwright

    page_file = HERE / 'chart.html'
    page_file.write_text(HTML, encoding='utf-8')

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={'width': 1200, 'height': 900},
                                      device_scale_factor=2)
        await page.goto(page_file.as_uri())
        await page.wait_for_timeout(500)
        await page.locator('body').screenshot(path=str(HERE / 'size_guide.png'))
        await browser.close()
    print('wrote', HERE / 'size_guide.png')


asyncio.run(main())
