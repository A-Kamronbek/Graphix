# `data/` — seed datasets

Input files for the `seed_*` management commands. Tracked in git so a fresh
deploy can populate reference tables without a database dump.

## `regions.csv`

The administrative divisions a customer picks from at checkout: 15 regions
(14 real plus one escape) and 221 districts, cities and escapes. Loaded by:

```
python manage.py seed_regions            # validates the whole file, then upserts
python manage.py seed_regions --dry-run
```

These two tables replaced the Uzpost branch table (plan §17 #84). There is no
public Uzpost branch list to own, but the administrative divisions **are**
published — and the customer supplies the one thing we could never obtain, the
postal index of their own branch.

### Columns

| Column | Applies to | Notes |
|---|---|---|
| `level` | all | `region` or `district`. |
| `code` | all | SOATO code. 4 digits for a region, 7 for a district or city. The upsert key. |
| `region_code` | district | The `code` of the region it sits under. |
| `name` | all | Uzbek — the base field, the source of truth. |
| `name_ru`, `name_en` | all | Blank falls back to `name`. |
| `kind` | district | `district` (tuman), `city` (viloyat ahamiyatiga ega shahar), or `other` (the escape). |
| `postal_prefix` | region | The leading digits of an index in this region. Empty **only** for the escape. |
| `sort_order` | all | Integer, default 0. |

Re-running is safe: rows are matched on `code`, and a row that disappears from
the CSV is **deactivated, not deleted** — an order points at a district through
a PROTECT foreign key, and its `location_snapshot` should stay explainable.

### Where the data came from, and how it was checked

This is the part worth reading before changing anything, because a wrong
`postal_prefix` silently rejects every valid index for that region — a lost sale
nobody hears about (§19 Q23).

**Source.** The National Statistics Committee's own SOATO classifier,
`https://stat.uz/images/soato-20_04_2022.xlsx`, linked from stat.uz's
"Statistik klassifikatorlar" page. It carries every unit's code and its name in
Uzbek Latin, Uzbek Cyrillic and Russian. The three SOATO compilations on GitHub
were **not** used as a source — one is GPL-3.0 and two carry no licence at all,
which is legally worse (§17 #90). The divisions themselves are government-
published facts and nobody owns them; a particular compilation of them may be.

**Generated, not typed.** `.git/build_regions_csv.py` reads the classifier and
writes this file, so the mapping from source to CSV is reproducible and
reviewable rather than a one-off act of transcription. It applies three things
by hand, each written out in that script:

1. **The postal prefixes** — the one table the classifier does not contain.
   Cross-checked against the UPU's addressing sheet for Uzbekistan and the
   published index ranges on goldenpages.uz, which agree: `100` Toshkent shahri,
   then `11` Toshkent viloyati, `12` Sirdaryo, `13` Jizzax, `14` Samarqand,
   `15` Fargʻona, `16` Namangan, `17` Andijon, `18` Qashqadaryo,
   `19` Surxondaryo, `20` Buxoro, `21` Navoiy, `22` Xorazm,
   `23` Qoraqalpogʻiston.
2. **English names**, which the classifier has no column for.
3. **Six spellings** where the 2022 classifier predates current orthography:
   Marxamat → Marhamat, Shaxrixon → Shahrixon, Shayxontoxur → Shayxontohur,
   Pskent → Piskent, Xazorasp → Hazorasp, Ellikkala → Ellikqala. The customer
   recognises the modern form; the SOATO code keeps the row tied to the
   classifier entry either way.

The Latin column is normalised to U+02BB (oʻ, gʻ) per §4, and a handful of Latin
homoglyphs typed into the Russian column ("Улугноpский" with a Latin p) are
mapped back to Cyrillic — they are invisible and would make those rows
unsearchable.

**Checked mechanically.** `.git/verify_regions_csv.py` asserts the district and
city counts per region against the classifier's own totals, that every code is
unique and sits under its region, that no name carries an ASCII apostrophe, that
no Russian name mixes scripts, that every prefix is 2–3 digits and unique, that
**no prefix is a prefix of another** (which would make the `startswith` check
ambiguous), and that every region has a `Boshqa` escape. Run it after any edit:

```
python .git\verify_regions_csv.py
```

### The escape

Region `0000` — `Boshqa` — and one `kind=other` district under every region
(§17 #87). The classifier is a snapshot and districts are created and renamed by
decree, so a customer whose address is not in it must still be able to order:
they pick `Boshqa` and type the name, which is stored in `Order.location_note`
and folded into `location_snapshot`.

The escape region has **no postal prefix**, and that is what switches the
region check off for it. The six-digit format check still applies — a
four-digit index is wrong no matter where it is.

### What is still outstanding

The classifier is dated **20 April 2022**. Any district created, merged or
renamed since is not in it. Nothing in the checkout breaks if that happens — the
customer uses the escape — but the file should be regenerated from a newer
classifier when one is published.
