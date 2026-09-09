# Phase 2 — typeface screening

**Date:** 2026-09-09 · **Method:** downloaded each family's font binary from `google/fonts` and
read its `cmap` directly with fontTools. Not from documentation or memory — from the files.

## Why this ran before anything else

Uzbek Latin spells **oʻ** and **gʻ** with **U+02BB MODIFIER LETTER TURNED COMMA**. It is not an
apostrophe (U+0027), not a right single quote (U+2019), and not U+02BC. A face that lacks it renders
`Oʻzbekiston` — the country's own name — as tofu. Phase 1a hit this with Poppins while building the
OG card, which is what prompted the screen (risk #23).

Russian needs Cyrillic. So the site's real requirement is **U+02BB *and* Cyrillic in one family**,
and that turns out to eliminate most of the modern sans catalogue.

## Result: 22 of 31 families are disqualified

| Family | U+02BB `ʻ` | Cyrillic | Latin Ext | Variable | TTF |
|---|:--:|:--:|:--:|:--:|--:|
| Commissioner | ✅ | ✅ | ✅ | ✅ | 725 KB |
| IBMPlexMono | ✅ | ✅ | ✅ | ❌ | 132 KB |
| IBMPlexSans | ✅ | ✅ | ✅ | ✅ | 525 KB |
| Inter | ✅ | ✅ | ✅ | ✅ | 856 KB |
| Mulish | ✅ | ✅ | ✅ | ✅ | 207 KB |
| NotoSans | ✅ | ✅ | ✅ | ✅ | 2001 KB |
| Onest | ✅ | ✅ | ✅ | ✅ | 189 KB |
| Oswald | ✅ | ✅ | ✅ | ✅ | 168 KB |
| Unbounded | ✅ | ✅ | ✅ | ✅ | 760 KB |
| Anton | ✅ | ❌ | ✅ | ❌ | 167 KB |
| PublicSans | ✅ | ❌ | ✅ | ✅ | 101 KB |
| SpaceGrotesk | ✅ | ❌ | ✅ | ✅ | 133 KB |
| Geologica | ❌ | ✅ | ✅ | ✅ | 340 KB |
| GolosText | ❌ | ✅ | ✅ | ✅ | 180 KB |
| JetBrainsMono | ❌ | ✅ | ✅ | ✅ | 183 KB |
| Jost | ❌ | ✅ | ✅ | ✅ | 132 KB |
| Manrope | ❌ | ✅ | ✅ | ✅ | 162 KB |
| MartianMono | ❌ | ✅ | ✅ | ✅ | 145 KB |
| Rubik | ❌ | ✅ | ✅ | ✅ | 351 KB |
| WixMadeforDisplay | ❌ | ✅ | ✅ | ✅ | 156 KB |
| WixMadeforText | ❌ | ✅ | ✅ | ✅ | 155 KB |
| Archivo | ❌ | ❌ | ✅ | ✅ | 643 KB |
| BebasNeue | ❌ | ❌ | ✅ | ❌ | 60 KB |
| BricolageGrotesque | ❌ | ❌ | ✅ | ✅ | 399 KB |
| Chivo | ❌ | ❌ | ✅ | ✅ | 157 KB |
| Figtree | ❌ | ❌ | ✅ | ✅ | 61 KB |
| InstrumentSans | ❌ | ❌ | ✅ | ✅ | 190 KB |
| Outfit | ❌ | ❌ | ✅ | ✅ | 108 KB |
| PlusJakartaSans | ❌ | ❌ | ✅ | ✅ | 172 KB |
| Sora | ❌ | ❌ | ✅ | ✅ | 109 KB |
| SpaceMono | ❌ | ❌ | ✅ | ❌ | 97 KB |

## The nine that pass

| Family | Role it could play | Note |
|---|---|---|
| **Unbounded** | Display | Geometric, wide, Cyrillic-native (Latinotype/Google). Distinctive — reads as a brand, not a template. 760 KB variable, so subset hard. |
| **Oswald** | Display, condensed | Strong vertical rhythm, very economical horizontally. Narrow enough to feel like signage. |
| **Onest** | Text **and** display | Cyrillic-first, modern, tight U+02BB spacing, 189 KB. The strongest all-rounder here. |
| **Inter** | Text | What the site already loads (from `rsms.me`). Safe, extremely legible, and completely generic — it is the default choice, which is the argument against it for a brand. |
| **IBM Plex Sans** | Text | Characterful, slightly technical. **Spacing defect:** renders `O ʻzbekiston` with a visible gap before the turned comma. |
| **Commissioner** | Text | Low-contrast humanist, wide weight range, 725 KB. |
| **Mulish** | Text | Clean, light. **Same U+02BB spacing gap as IBM Plex Sans.** |
| **Noto Sans** | Fallback | The safety net, not a choice. 2 MB. |
| **IBM Plex Mono** | Mono | **The only monospace that passes.** JetBrains Mono, Space Mono and Martian Mono all fail. This effectively settles `--f-mono`. |

## Second filter — spacing, not just coverage

Having the glyph is not the same as setting it well. Rendered at 25 px, **IBM Plex Sans** and
**Mulish** both put a visible space before the turned comma (`O ʻzbekiston`), because the glyph
carries side bearings meant for a standalone modifier letter. **Onest, Unbounded, Commissioner,
Inter, Oswald and Noto Sans** set it tight, the way Uzbek expects.

That drops the practical shortlist to **Onest, Unbounded, Oswald, Commissioner, Inter**, plus
**IBM Plex Mono** for mono.

## Notable casualties

Every one of these is a common 2025-era choice, and none can set Uzbek:

**Manrope · Figtree · Outfit · Plus Jakarta Sans · Sora · Space Grotesk · Bricolage Grotesque ·
Archivo · Chivo · Instrument Sans · Jost · Rubik · Geologica · Wix Madefor · Bebas Neue**

Two deserve special mention because they look like safe bets and are not:

- **Golos Text** — a Cyrillic-first family by Paratype, built for Russian. Still no U+02BB.
- **Rubik** — ships Latin, Cyrillic *and* Hebrew. Still no U+02BB.

The lesson for the rest of the project: **check the cmap, don't trust the family's reputation.**

## Second batch — editorial and fashion faces

Round one of the design was rejected as *"thin and sharp, looks like hand made cheap design"*. The
cause was upstream of the design: **every family in the first batch was a modern grotesque**, so all
three directions inherited one voice. A shortlist drawn from a single register cannot produce three
different answers.

So a second batch of 35 editorial, serif and fashion faces was screened the same way. **18 pass.**

| Family | Role | Note |
|---|---|---|
| **Playfair Display** | **Display — chosen** | High-contrast fashion serif, Cyrillic, 294 KB variable. The one face that delivers a premium editorial voice *and* sets Uzbek. |
| Cormorant / Cormorant Garamond | Display | Beautiful, but very high-contrast and light — it would reintroduce the "thin" problem. |
| EB Garamond, Spectral, Literata, Lora, Source Serif 4, Alegreya, Bona Nova, Merriweather, Noto Serif | Text serif | Available if a reading face is ever needed. |
| Montserrat, Raleway, Nunito, Fira Sans, Exo 2, Comfortaa | Sans | Montserrat is the sturdiest, and the most over-used. |

### Failing — and this is the useful part

**Every conventional Cyrillic fashion display face fails:** **Prata, Forum, Tenor Sans, Bodoni Moda,
Marcellus.** These are the faces a designer reaches for when asked for "premium" on a Russian- or
Uzbek-language site, and not one of them can spell `Oʻzbekiston`.

Also failing: PT Serif, PT Sans, Philosopher, Oranienbaum, Arsenal, Cuprum, Jura, Play, Russo One,
Alumni Sans, Fraunces, Unna.

**There is very little premium display type that can set Uzbek.** That is the finding, and it is why
the check has to come before a face is proposed rather than after it is chosen.

## Reproducing this

```python
from fontTools.ttLib import TTFont
cmap = TTFont("Family[wght].ttf").getBestCmap()
0x02BB in cmap   # the only question that matters first
```

Font binaries live at `https://raw.githubusercontent.com/google/fonts/main/ofl/<family>/`.
