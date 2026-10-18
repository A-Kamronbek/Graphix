# `data/` — seed datasets

Input files for the `seed_*` management commands. Tracked in git so a fresh
deploy can populate reference tables without a database dump.

## `uzpost-regions.csv`

What a customer picks from at checkout since Phase 22: Uzpost's 14 regions and
198 districts, each with Uzpost's id and, for a district, its centre, the pin
on the office map (plan §17 #378, #381). A shipment is addressed by Uzpost's
district id, so these are the places that can be sent to. Loaded on top of
`regions.csv` by:

```
python manage.py seed_regions                 # a fresh database: the official rows first
python manage.py sync_uzpost_regions          # then Uzpost's, checked whole before writing
python manage.py sync_uzpost_regions --dry-run
```

The load switches off every official row Uzpost has no district for, and
every `Boshqa`; it deletes nothing. Once it has run, `seed_regions` refuses
without `--force`, since it would bring the official rows back.

### Columns

| Column | Applies to | Notes |
|---|---|---|
| `level` | all | `region` or `district`. |
| `uzpost_id` | all | Uzpost's jurisdiction id. The key the load matches on first. |
| `parent_id` | district | The `uzpost_id` of its region. |
| `name` | all | Uzpost's name with the typography put right: `oʻ` and `gʻ` with U+02BB, the tutuq belgisi with U+02BC, Cyrillic look-alike letters made Latin, spaces trimmed, *tumani* and *shahri* in lower case. Nothing else is changed (§17 #378). A region keeps its own name; this column is only a record of Uzpost's. |
| `kind` | district | `district` or `city`: the official row's kind where it matched one, else what the name says. |
| `lat`, `lng` | district | The centre Uzpost gives, to six places, unless `note` says it was corrected. |
| `soato` | all | The official row this one takes over: its region, or its district, whose Russian and English names it keeps. Blank for a district with no official counterpart, which is created with the code `U` and its Uzpost id. |
| `note` | all | Written by hand. A district with a note keeps its `lat` and `lng` when the file is fetched again. |

### Where it came from

Fetched from Uzpost's API on 2026-10-18 with the owner's account (levels 2
and 3 of `v2/jurisdiction/choose/list`). To fetch again, on the server, where
the login is:

```
sudo -u graphix .venv/bin/python manage.py sync_uzpost_regions --fetch --file /tmp/uzpost-regions.csv
```

then copy the file over this one, read the diff and what the command printed,
and commit it. A fetch keeps every `soato` and `note` already in the file. A
new district gets a `soato` proposed by name within its region, and every
proposal that is not an exact match is printed as `check:` to be read.

The file is the authority at every load. A `soato` written in by hand (say,
Mirzachoʻl's for Uzpost's `Gagarin`) moves Uzpost's id to that official row,
which keeps its Russian and English; the `U` row left behind is switched off
and takes its code beside its name, since two districts of one region cannot
share a name. A `soato` from another region is refused. Only the Uzbek name
comes from the file: Russian and English written in the panel stay.

Of the 198 districts, 164 took over an official row: 150 by name and 14 by a
spelling a letter or two apart (`Chilanzar` for Chilonzor, `Honobod` for
Xonobod), each checked by eye. The other 34 have no official row by name.
Many are the district's centre town (`Gagarin` for Mirzachoʻl, `Galaosiyo` for
Buxoro tumani); they were not matched by hand, so they start with Russian and
English blank, to be written in the panel.

Two centres are corrected by hand, each with a note saying what Uzpost gave:
Romitan, which Uzpost puts in the Qizilqum, and Jizzax's `Uchtepa tumani`,
which it puts in Sirdaryo. The rest are Uzpost's and are not checked one by
one; some look like the middle of the district rather than its town.

## `regions.csv`

The official administrative divisions, from before Phase 22: 15 regions
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
