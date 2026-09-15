# Product descriptions — how to write them

Plan §9 Phase 8 item 7. The owner writes every product himself, in three
languages, from the panel. This page is the shape those descriptions follow, so
the catalogue reads as one voice at two hundred designs as well as at eight.

The same shape is built into the panel: under each empty description box on
`/boshqaruv/mahsulotlar/…` a **Namunani qoʻyish** button puts the template in,
in that box's own language (`panel/catalogue.py`, `DESCRIPTION_TEMPLATE`).

## What the description is not for

The product page already prints these from their own fields, in the spec strip
above the description. **Do not repeat them in the text** — a fact written
twice is a fact that will one day disagree with itself (plan §17 #111):

- fabric (`Mato`) — e.g. *100% paxta*
- weight (`Zichligi, g/m²`) — e.g. *200*
- print method (`Bosma usuli`) — e.g. *DTF*, *shelkografiya*
- price, sizes and stock — the size grid
- the cut — a **tag** (*oversize*, *boxy*, …), not a sentence (§17 #172)

## The four parts

One short paragraph each, in this order. Two to four sentences in total is
usually enough; nobody reads a wall of text on a phone.

1. **Dizayn** — what the print shows and where it comes from. One or two
   sentences, in plain words. No "unique", "premium", "high quality": the
   photograph says that or nothing does.
2. **Bosma** — where the print sits (front, back, both) and roughly how big it
   is, in centimetres. This is the one thing a photo often does not make clear.
3. **Bichim** — how the shirt sits on the body, and one practical sizing tip
   ("between two sizes, take the larger one"). The size chart has the numbers;
   this is the advice.
4. **Parvarish** — care. The standard line below fits every printed tee we
   sell; change it only if a product really needs something different.

## The template, in each language

Uzbek — the source. Latin script, `oʻ`/`gʻ` with U+02BB.

```
Dizayn: [nima tasvirlangan va nimadan ilhomlangan — bir-ikki gap]

Bosma: [qayerda — old, orqa yoki ikkala tomonda; taxminiy oʻlchami, sm]

Bichim: [qanday oʻtiradi — oddiy yoki keng; oʻlcham tanlash boʻyicha maslahat]

Parvarish: 30 °C da, teskari tomonidan yuving. Bosma ustidan dazmollamang. Oqartiruvchi ishlatmang, mashinada quritmang.
```

Russian — written, not translated: natural shop register.

```
Дизайн: [что изображено и чем вдохновлено — одно-два предложения]

Печать: [где расположена — спереди, сзади или с обеих сторон; примерный размер, см]

Посадка: [как сидит — обычная или свободная; совет по выбору размера]

Уход: стирать при 30 °C, вывернув наизнанку. Не гладить по принту. Не отбеливать и не сушить в машине.
```

English — for a fluent reader.

```
Design: [what it shows and what inspired it — a sentence or two]

Print: [where it sits — front, back or both; roughly how big, in cm]

Fit: [how it sits — regular or relaxed; a tip for choosing a size]

Care: wash at 30 °C, inside out. Do not iron over the print. Do not bleach or tumble dry.
```

## A filled-in example

> **Dizayn:** Toʻlqinlar orasida suzayotgan qogʻoz qayiq — yozgi kechalarga
> bagʻishlangan qoʻlda chizilgan grafika.
>
> **Bosma:** Orqada, taxminan 28 × 30 sm; oldida koʻkrak ustida kichik belgi.
>
> **Bichim:** Keng, yelkasi tushgan. Ikki oʻlcham orasida ikkilansangiz,
> kichigini tanlang.
>
> **Parvarish:** 30 °C da, teskari tomonidan yuving. Bosma ustidan
> dazmollamang. Oqartiruvchi ishlatmang, mashinada quritmang.

## Before publishing

- All three languages filled. A blank Russian or English box falls back to
  the Uzbek, which is better than nothing and worse than a sentence (§17 #8).
- No claim the product page cannot back up — no "the softest cotton", no
  "ships today".
- Tags set: the cut, the theme, the collection. The recommender reads them
  (plan §9 Phase 13).
- Read it once on a phone.
