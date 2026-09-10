# `data/` — seed datasets

Input files for the `seed_*` management commands. Tracked in git so a fresh
deploy can populate reference tables without a database dump.

## `pickup_points.csv`

The Uzbekiston pochtasi branches a customer can collect an order from. Loaded by:

```
python manage.py seed_pickup_points          # validates, then upserts
python manage.py seed_pickup_points --dry-run
```

**This file currently has only a header row. The real branch list has to come
from the shop owner** (plan §19, Q3/Q4). Branch addresses and coordinates are
not guessable — a wrong row sends a real parcel to the wrong place — so nothing
here is invented.

### Columns

| Column | Required | Notes |
|---|---|---|
| `code` | yes | Postal index, e.g. `100007`. The upsert key. |
| `name` | yes | Uzbek — the base field, the source of truth. |
| `name_ru`, `name_en` | no | Blank falls back to `name`. |
| `region` | yes | `Toshkent shahri`, `Samarqand viloyati`, … |
| `district` | yes | |
| `address` | yes | Uzbek. |
| `address_ru`, `address_en` | no | Blank falls back to `address`. |
| `latitude`, `longitude` | yes | Decimal degrees. Validated against Uzbekistan's bounding box, which catches the two being swapped. |
| `working_hours` | no | Free text, e.g. `Du–Sh 9:00–18:00`. |
| `phone` | no | |
| `sort_order` | no | Integer, default 0. |

Re-running is safe: rows are matched on `code`, and a branch that disappears
from the CSV is **deactivated, not deleted** — an order may reference it through
a PROTECT foreign key, and its `pickup_snapshot` should stay explainable.
