# GRAPHIX — Rebuild Plan

**Project:** ValleyMade → **GRAPHIX** — online graphic t-shirt store for Uzbekistan
**Repo:** `D:\phyton\ValleyMade\` (Django project package `vm/`)
**Production:** **graphix.uz** (domain secured, not yet deployed). valleymade.uz is abandoned — see §17 #35.
**Owner / developer:** Kamronbek
**Plan version:** 1.6 · created 2026-09-08 · last amended 2026-09-09
**Status:** Phases 0 and 1a complete · Phase 1b parked (no VPS yet) · **Phase 2 in progress — a direction needs choosing (§19 Q18)**

---

## 0. How to use this document

This file is the **single source of truth** for the rebuild. It lives at `docs/PLAN.md` in the repo
and as `claude/PLAN.md` in the Claude project.

### Working across chats

Planning happens in the planning chat. **Implementation happens in other chats inside the same
project**, opened as and when convenient. A chat may cover a single phase, several phases, or part of
one — that is a practical matter. What matters is that every chat produces work consistent with every
other chat's, as though one person built the whole thing:

1. **Every chat reads this plan before doing anything.** It is the shared memory between chats. A
   chat that hasn't read the plan will re-litigate settled decisions and invent its own conventions.
2. **Work follows the execution order in §13**, and a phase's Definition of Done passes before the
   next one starts — even when both happen in the same chat.
3. **Every chat ends by updating §15 (Progress tracker) and §16 (Session log).** If it made a
   decision that shapes future work, it adds a row to §17 (Decision log). This is not optional —
   it is how the next chat knows where things stand. A long chat updates them as it goes, not only
   at the end.
4. **No chat changes a locked decision** (§3) or a convention (§4) on its own. If one needs to
   change, it stops and raises it with Kamronbek, and the change is recorded in §17 before any code
   depends on it.

### Three rules that keep the work consistent

1. **Nothing is built that isn't in this plan.** New ideas go into the plan first (§10), then get
   built.
2. **The plan is amended, not abandoned.** When reality contradicts the plan, edit the plan in the
   same session and log the change in §17.
3. **A phase is not finished until its Definition of Done passes.** No moving on with "I'll come
   back to it."

### Phase numbers are identifiers, not running order

Phases are numbered in the order they were *added to the plan*, and are **never renumbered** — so a
reference to "Phase 6" means the same thing in three months as it does today. Execution order is
stated separately in §13 and is the order that actually matters.

---

## 1. Where the project stands today

An honest baseline, from a full read of every Python file, template, `main.css` and `main.js`, plus
an inspection of the live site.

### What is genuinely good and must be preserved

- **Sound domain modelling.** `Product → Variant(size, colour, price)` with `price_stat` snapshotted
  onto `CartItem` is correct e-commerce design. A catalogue price change can never mutate an
  existing cart or order.
- **Correct concurrency handling at checkout.** `create_order_from_cart` locks the cart row with
  `select_for_update` and computes the total *from the locked lines*. This is the kind of thing that
  is expensive to learn the hard way. Do not touch it.
- **One-open-cart-per-user** enforced by a partial `UniqueConstraint` at the database level, not in
  application code.
- **A complete, well-thought-out phone-OTP auth system.** Signup OTP and password reset share an
  identical, deliberately duplicated policy (5 min TTL, 60 s resend cooldown, 7 attempts).
  `expire_verification` is server-verified so a forged POST cannot delete a live account.
- **Dependency-free rate limiting** that fails open, applied consistently across every sensitive
  endpoint, with matching disabled-button UI.
- **Phone normalisation in `User.save()`**, not only in the form — the uniqueness constraint cannot
  be bypassed by differently-spaced input.
- **Genuinely good code documentation.** Nearly every module, class and function has a docstring
  that explains *why*, not just *what*. This standard continues.

### What has to change

| Area | Problem |
|---|---|
| Visual design | Single 35 KB stylesheet, one black brutalist theme. Not competitive, not inviting, weak on mobile. |
| Brand | Name, favicon, domain, all copy still say ValleyMade. |
| Language | Uzbek only, hardcoded in templates. No i18n infrastructure at all. |
| Product depth | No size guide, no stock, no likes, no reviews, no tags, no specs, no SEO slugs. |
| Conversion | Login is required just to add to cart — the biggest drop-off point on the site. |
| Checkout | Free-text address only. No map, no pickup points, no delivery cost, cash disabled. |
| Admin | Raw Django admin only. Not usable from a phone, not shaped around the daily job. |
| Legal | No privacy policy. Terms page exists but is thin. |
| Media | Product images are unoptimised PNGs — 1.9 MB and 3.8 MB files sit in `media/products/`. |
| Tests | Zero. All five `tests.py` files are empty stubs. |
| Inventory | The live shop is empty — 0 purchasable products. |

### Immediate defects found during the audit

1. ✅ **`vm/vm/settings.py` is broken in the working copy.** An uncommitted edit deleted seven lines:
   `STATIC_URL`, `STATICFILES_DIRS`, `STATIC_ROOT`, `MEDIA_URL`, `MEDIA_ROOT`, `DEFAULT_AUTO_FIELD`.
   `vm/urls.py` references `settings.MEDIA_URL` and `settings.STATIC_URL`, so `runserver` fails at
   startup locally. Production is unaffected (it runs the committed version). → *Fixed in Phase 0.*
2. ✅ **Footer category links are dead.** `_footer.html` links to `?category=tops|bottoms|outer`, but
   `shop()` filters on `category_id` (an integer). Those three links silently return everything.
   → *Fixed in Phase 0 (§17 #33).*
3. ✅ **`.pyc` files are tracked in git** and permanently dirty. The audit counted 33; the actual
   number at Phase 0 was **48**, plus the whole `.idea/` directory. → *Untracked in Phase 0.*
4. ✅ **Stale TODO block** in `payment/payment.html` claims Click is not connected. It is.
   → *Removed in Phase 0; no `TODO` remains anywhere in the codebase.*
5. ✅ **Unused dependencies**: `djangorestframework_simplejwt`, `django-cors-headers`.
   (`djangorestframework` must stay — `click_up` imports `rest_framework.views` and
   `rest_framework.exceptions` even though its package metadata doesn't declare it.)
   → *Removed in Phase 0, along with `PyJWT`, which existed only for simplejwt.*
6. ✅ **Contact details are inconsistent** — the contact page shows two different email addresses (one
   a placeholder) and a Telegram handle that no longer matches the canonical one.
   → *Fixed in Phase 1a; the phone and email are now `tel:` / `mailto:` links too.*

Found during Phase 0, not in the original audit:

7. ✅ **`requirements.txt` was UTF-16 encoded**, which `pip install -r` cannot read on every
   platform. → *Rewritten as UTF-8 in Phase 0.*
8. **`django-environ` is pinned but never imported** — the project reads its `.env` through
   `python-dotenv`. Left in place pending Kamronbek's confirmation (§18 #4).

---

## 2. Product vision

> **GRAPHIX** — the place in Uzbekistan to buy a graphic t-shirt you actually want to wear.

**Positioning line:** *premium quality · 100+ designs · delivery within Uzbekistan*

The design has one job: **make the print the hero.** Every other element on the page exists to get
out of the artwork's way. A customer should be able to land from an Instagram or Telegram link,
understand what they're looking at within two seconds, know their size without leaving the page, and
finish checkout in under a minute on a mid-range Android phone over 4G.

**Design principles** (the tie-breakers when a decision is unclear):

1. **The product image is the largest, sharpest thing on screen.** Chrome shrinks to make room.
2. **Mobile is the design surface, not the adaptation.** Most Uzbek e-commerce traffic is phone
   traffic arriving from Telegram and Instagram. Design at 390 px first, then let it breathe.
3. **Show the shop immediately.** The home page is a shop, not a poster. On a 390 × 844 viewport at
   least one row of real products must be partially visible without scrolling.
4. **One decision per screen.** The item page asks for size; checkout asks for address; payment asks
   for payment. Never two at once.
5. **Speed is a feature.** A page that loads in 1.5 s beats a prettier page that loads in 4 s.
6. **Uzbek first, and written like a person.** Not machine translation, in any of the three
   languages.
7. **Restraint over decoration.** No gradient blobs, no stock 3D shapes, no "AI landing page" glow.
   Confidence comes from typography, spacing and photography — not effects.

---

## 3. Locked technical decisions

Settled during planning. Changing any of these requires a §17 decision-log entry made in the
**planning chat**, not a task chat.

| Decision | Choice | Why |
|---|---|---|
| Frontend approach | **Django templates + hand-written CSS/JS. No build step.** | Ships the same way it does today. Nothing new to install on the VPS, nothing to break in the gunicorn/nginx pipeline. |
| Map provider | **Yandex Maps — paid commercial licence** | Best Uzbek street data and the best Uzbek/Russian reverse-geocoding by a clear margin. The free tier is *not* licensed for commercial sites, so this is a budgeted cost (§19 Q1). |
| Map abstraction | **All map code sits behind one thin internal wrapper** | The licence cost is not yet known. If it turns out unacceptable, swapping to Leaflet, Google or 2GIS must be a one-file change, not a rewrite. |
| Saved items | **One "like" — public count and private saved list in a single action** | One heart, one model. Matches how every fashion store and social app works, and how the customer describes it. Feeds the popularity sort and the recommender. |
| Guest browsing | **Anonymous cart; login required at checkout** | Guests browse and fill a cart freely; the login wall moves from "add to cart" to "checkout". Captures most of the conversion benefit without reworking the most sensitive code in the project. |
| Rebuild strategy | **Evolve in place, one branch per phase** | Same repo, same database. The site stays live and improving throughout. |
| New Python dependencies | **None.** | Everything needed is already installed or is in the standard library. |
| Language strategy | **Uzbek default (no URL prefix), `/ru/` and `/en/` prefixed** | Best for SEO and for the majority audience. |
| Internal package name | **`vm/` stays** for now | Renaming touches wsgi, systemd, nginx and the venv. Deferred to an optional Phase 11 task. |
| Brand mark | **The existing six-point asterisk carries over** | Already vector, already distinctive. It needs a clean geometric redraw, not a redesign. |
| Delivery | **Two tiers, no free threshold: 15 000 UZS to an Uzpost office · 30 000 UZS to the door. All shipping via Uzpost, Tashkent and regions alike.** | Simple, predictable, and each tier reflects real cost. |
| Pickup points | **We own the branch dataset in our own `PickupPoint` table** | No public Uzpost branch API exists (§ research below). Owning it is the only way checkout can be reliable. |
| Colour | **Removed from the product-page UI; kept in the data model** | Every design ships in one colourway, so the picker is noise. Deleting the model would be a destructive migration with no benefit. |
| Reviews | **Verified purchase only, with moderation** | Only a customer with a delivered order containing that product can review it. Photos are queued for approval before they appear publicly. |
| Recommendations | **Tag-overlap, not machine learning. Data collected from day one, algorithm built after launch.** | A recommender needs like data and product tags to be worth anything. Tags land in Phase 4; the algorithm is Phase 13. |
| Telegram notifications | **Committed deliverable, not optional** | A push to the owner's phone within seconds of an order is worth more than any dashboard. |
| Legal documents | **Written in-project** | Drafted to a real standard against Uzbek law. Independent review recommended, not blocking. |

### Research finding: Uzpost branch data

Investigated before committing to pickup-point delivery.

- **No public Uzpost branch API exists.** [uz.post](https://uz.post/uz/xizmat/15) publishes no
  developer documentation and no machine-readable branch list. What is available through third
  parties ([TrackingMore](https://www.trackingmore.com/uzbekistan-post-tracking-api),
  [PostTracking](https://posttracking.org/carriers/uzpost/)) is *parcel tracking*, not branch
  locations — a different problem.
- **Open data:** Uzbekistan's [open data portal](https://data.gov.uz/uz/pages/about) exists but no
  postal-branch dataset surfaced. Worth one direct check before seeding.
- **OpenStreetMap has real, indexed Uzbek post offices** — nodes carry names and ZIP codes
  (e.g. "Post office #7 (ZIP 100007)", "Pochta №93" in Tashkent). ODbL-licensed, free to store with
  attribution. Good seeding aid; needs manual verification.
- **Commercial directories** ([2GIS Places API](https://docs.2gis.com/en/api/search/places/overview),
  Yandex Organization Search) have strong Tashkent coverage but return inconsistent names — the
  customer's own screenshot shows "Post Office 43", "Pochta", "Uzpost pocht" as separate entries —
  and their terms generally restrict storing results. Useful for cross-checking, not as a live
  dependency in the checkout path.

**Conclusion:** seed a `PickupPoint` table once from OSM plus (ideally) an official list requested
directly from Uzpost, verify by hand, and maintain it in the admin panel. Branch locations are
slow-moving data; a live third-party lookup inside checkout would add a failure mode for no benefit.

---

## 4. Constraints and conventions

### Dependencies

The rebuild adds **zero** new Python packages. Verified: Redis caching is built into Django 6;
Pillow handles thumbnails; `django.utils.text.slugify` handles slugs; Django's own `gettext` handles
i18n; `requests` (already installed) handles Telegram and any Uzpost seeding; Django's built-in
runner handles tests; Yandex Maps is browser-side JavaScript.

To **remove** in Phase 0: `djangorestframework_simplejwt`, `django-cors-headers`.

### File operations

All file operations on `D:\phyton\ValleyMade\` go through the filesystem MCP or the device shell —
never the cloud container's bash, which cannot see the D: drive.

- Read before editing. Batch reads with `read_multiple_files` for cross-file context.
- Prefer **full-file replacements** over partial edits for anything non-trivial. `edit_file` is
  fragile with Django template syntax and regex-special characters.
- Split unrelated edits into separate calls — a batched edit can silently no-op if one `oldText`
  fails to match.
- Read back after writing to confirm.

### Code conventions

- **Docstrings**: brief and simple, explaining *why*. Match the existing style exactly.
- **CSS**: BEM (`.block__element--modifier`).
- **No hardcoded design values.** Every colour, space, radius, font size and duration comes from a
  token in `tokens.css`.
- **No hardcoded user-facing strings** after Phase 3. Everything goes through `{% trans %}`.
- **Every model change ships with its migration in the same commit.**
- **URL *names* never change.** Paths may change (with a 301); `{% url 'shop' %}` must keep working.
- **External calls never break a request.** Every outbound integration (Eskiz, Telegram, Yandex,
  Click) follows the pattern in `core/sms.py`: module logger, catch everything, log, return falsy.
  An outage degrades the feature — it never 500s the page.
- **Commits**: `<phase>: <imperative summary>` — e.g. `P5: rebuild item page on the new design system`.

### Branches

`main` is the integration branch (§17 #32). One branch per phase, cut from `main`:
`phase-0-stabilise`, `phase-1-rebrand`, … Merged back into `main` when the phase's Definition of
Done passes. Deploy after each merge.

### Non-negotiables

- Auth, OTP, rate limiting and the checkout row-lock keep their exact current behaviour. Refactors
  allowed; behaviour changes are not, unless a phase explicitly calls for one.
- No secret ever enters the repo. Everything stays in `.env`.
- No destructive database operation on production without a fresh verified `pg_dump` first.

---

## 5. Quality targets

**Performance** (Lighthouse mobile, throttled 4G, Moto G4 class):

| Metric | Target |
|---|---|
| Performance score | ≥ 90 |
| Largest Contentful Paint | ≤ 2.5 s |
| Cumulative Layout Shift | < 0.1 |
| Interaction to Next Paint | < 200 ms |
| Total CSS (gzipped) | ≤ 60 KB |
| Total JS (gzipped) | ≤ 30 KB |
| Largest product image delivered | ≤ 250 KB (WebP) |

**Accessibility** — WCAG 2.1 AA: contrast ≥ 4.5:1 (≥ 3:1 large text and UI boundaries); everything
keyboard-operable with a visible focus ring; tap targets ≥ 44 × 44 px; meaningful `alt` on every
image; real `<label>`s and announced errors, never colour alone; `prefers-reduced-motion` honoured.

**Responsive** — verified at **360, 390, 768, 1024, 1440, 1920 px** on every page. No horizontal
scroll at any width.

**Browsers** — last two versions of Chrome, Safari, Firefox and Samsung Internet; iOS Safari 16+.

---

## 6. Target information architecture

```
/                          Home
/shop/                     Catalogue — search, filter, sort
/mahsulot/<slug>/          Product detail  (301 from /item/<pk>/)
/qidiruv/                  Global search results          ← new
/saqlanganlar/             Liked / saved items            ← new
/cart/                     Cart  (anonymous allowed)
/checkout/                 Checkout — login required, delivery + pickup point
/payment/<id>/             Payment (Click)
/order/<id>/               Order detail
/order/<id>/status/        Order status timeline
/order/<id>/sharh/         Leave a review                 ← new
/account/                  Account home
/account/orders/           Order history
/account/settings/         Account settings
/about/                    About
/contact/                  Contact
/terms/                    Terms of use
/privacy/                  Privacy policy                 ← new
/yetkazib-berish/          Delivery & returns             ← new
/size-guide/               General sizing guide           ← new
/boshqaruv/                Custom admin panel             ← new (staff only)
/admin/                    Django admin (kept)

/ru/…  /en/…               Same tree, prefixed
```

**Must stay outside `i18n_patterns()`** — called by machines, and a language prefix would break them:

- `/payment/click/update/` — the Click webhook. **Breaking this breaks payments.**
- `/admin/`, `/sitemap.xml`, `/robots.txt`, `/media/`, `/static/`

---

## 7. Target data model

All changes are additive except where noted. No existing column is dropped or renamed.

### `product`

```python
class Tag(Model):                       # NEW — powers filtering and recommendations
    slug          SlugField(60, unique)
    name_uz/ru/en CharField(60)
    kind          CharField(20, choices=['style','theme','collection'])
    Meta: ordering = ['kind', 'slug']
    # e.g. style: oversize, boxy · theme: anime, streetwear, music, sport, minimal, vintage

class SizeChart(Model):                 # NEW
    name          CharField(120)
    image         ImageField('size-charts/', null, blank)   # PRIMARY: a photo/graphic chart
    note_uz/ru/en TextField(blank)

class SizeChartRow(Model):              # NEW — OPTIONAL structured data
    chart         FK(SizeChart, related_name='rows')
    size          FK(Size, PROTECT)
    chest_cm, length_cm            DecimalField(4,1)
    shoulder_cm, sleeve_cm         DecimalField(4,1, null)
    order         PositiveSmallIntegerField
    Meta: ordering = ['order'], unique_together = ('chart', 'size')

class ProductLike(Model):               # NEW — ONE model: public count + private saved list
    user, product, created_at
    Meta: unique_together = ('user', 'product')

class Review(Model):                    # NEW
    user      FK(User)
    product   FK(Product, related_name='reviews')
    order     FK(Order, PROTECT)        # proves the purchase
    rating    PositiveSmallIntegerField(choices 1..5)
    text      TextField(blank)
    status    CharField(choices=['pending','approved','rejected'], default='pending', db_index)
    moderated_by  FK(User, null, SET_NULL)
    moderated_at  DateTimeField(null)
    created_at
    Meta: unique_together = ('user', 'product'), ordering = ['-created_at']

class ReviewImage(Model):               # NEW
    review    FK(Review, related_name='images')
    picture   ImageField('reviews/')
    order     PositiveSmallIntegerField

Product      + slug            SlugField(255, unique, db_index)
             + name_ru, name_en, description_ru, description_en
             + tags            M2M(Tag, blank, related_name='products')
             + likes_count     PositiveIntegerField(0, db_index)   # denormalised
             + rating_avg      DecimalField(2,1, default=0, db_index)
             + review_count    PositiveIntegerField(0)
             + size_chart      FK(SizeChart, null, blank, SET_NULL)
             + is_active       BooleanField(True)
             # spec strip — structured, not buried in the description
             + gsm             PositiveSmallIntegerField(null, blank)      # 200
             + material_uz/ru/en  CharField(60, blank)                     # "100% paxta"
             + print_method    CharField(20, choices=['dtf','dtg','silkscreen','embroidery'], blank)
             + fit             CharField(20, choices=['regular','oversize','boxy'], blank)

Category     + slug, name_ru, name_en
             + size_chart      FK(SizeChart, null, blank, SET_NULL)   # default for its products

Colour       + colour_ru, colour_en          # model KEPT, hidden from the storefront UI

Variant      + stock           PositiveIntegerField(0)
             # `available` stays. Purchasable = available AND stock > 0.
```

**Likes are one concept.** A heart both saves the product to `/saqlanganlar/` and increments the
public `likes_count`. There is no separate favourite model. `likes_count` is maintained with
`F('likes_count') ± 1` inside a transaction, never a Python-side read-modify-write.

**Colour is hidden, not deleted.** The product page renders no colour picker. The admin auto-assigns
a single default colour on product creation so the owner never thinks about it. The existing JS
variant picker keys on `"colour_id:size_id"` and keeps working unchanged. If a design ever ships in
two colourways, the picker is re-enabled by configuration, not by a migration.

**Size guide is image-first.** The uploaded chart image is the primary content and the only required
field; `SizeChartRow` is optional structured data that, when present, renders as a responsive table
*in addition to* the image — better for accessibility and SEO. Resolution:
`product.size_chart or product.category.size_chart or None`.

**Reviews are verified-purchase only.** A review can only be created by a user who has an order with
status `done` containing that product, and `Review.order` records which one. Photos are `pending`
until a staff member approves them. `rating_avg` and `review_count` are recomputed from **approved**
reviews only.

### `cart`

```python
Cart         ~ user         FK(User, null=True, blank=True)     # CHANGED: now nullable
             + session_key  CharField(40, null, blank, db_index)

# The single partial unique constraint is replaced by two:
#   unique open cart per user      WHERE status AND user IS NOT NULL
#   unique open cart per session   WHERE status AND user IS NULL
```

**Anonymous carts.** A guest gets a cart keyed to their session. On login, the guest cart is merged
into the user's open cart line by line — quantities summed and capped at `min(99, stock)`, and the
guest cart is deleted. If the user has no open cart, the guest cart is simply claimed by setting
`user`. The merge runs inside a transaction with both carts locked. Checkout still requires login.

### `payment`

```python
class DeliveryOption(Model):            # NEW
    code             CharField(20, unique)        # 'uzpost_office' | 'uzpost_door'
    name_uz/ru/en    CharField(120)
    note_uz/ru/en    TextField(blank)
    price            DecimalField(15,0)
    free_from_items  PositiveSmallIntegerField(0) # 0 = never free (current policy)
    requires_pickup_point  BooleanField(False)
    is_active        BooleanField(True)
    sort_order       PositiveSmallIntegerField(0)

class PickupPoint(Model):               # NEW — our own Uzpost branch dataset
    code             CharField(20, unique)        # postal index, e.g. "100007"
    name_uz/ru/en    CharField(160)
    region           CharField(80, db_index)      # Toshkent shahri, Samarqand viloyati…
    district         CharField(80, db_index)
    address_uz/ru/en CharField(255)
    latitude         DecimalField(9,6)
    longitude        DecimalField(9,6)
    working_hours    CharField(120, blank)
    phone            CharField(30, blank)
    is_active        BooleanField(True, db_index)
    sort_order       PositiveSmallIntegerField(0)
    Meta: ordering = ['region', 'district', 'name_uz']

Order        + order_no        CharField(20, unique, db_index)   # "GX-260908-0042"
             + latitude, longitude   DecimalField(9,6, null, blank)   # door delivery only
             + delivery_option FK(DeliveryOption, null, blank, PROTECT)
             + delivery_price  DecimalField(15,0, default=0)     # SNAPSHOT at checkout
             + pickup_point    FK(PickupPoint, null, blank, PROTECT)
             + pickup_snapshot TextField(blank)   # frozen name+address of the branch at order time
```

**Seeded delivery options:**

| code | Uzbek name | Price | Pickup point | Note shown |
|---|---|---|---|---|
| `uzpost_office` | Uzbekiston pochtasi bo'limiga | 15 000 | **required** | Collect from your chosen branch |
| `uzpost_door` | Eshikkacha yetkazib berish | 30 000 | — | Courier to your address |

Both tiers ship via Uzpost, in Tashkent and every region alike. There is currently **no free-delivery
threshold** — `free_from_items` stays 0. The field exists so a promotion can be switched on later
without a deploy.

**Two snapshots, for the same reason `CartItem.price_stat` exists:** `delivery_price` freezes the fee
at checkout, and `pickup_snapshot` freezes the branch's name and address as text. If a branch is
renamed, moved or deactivated a year later, the order still says where it was sent.

Validation: an order with a `requires_pickup_point` option **must** have a `pickup_point`; an order
with a door option must not. Enforced in the checkout view and in `Order.clean()`.

`order_no` is what the customer and courier see. The integer PK is never shown again — it leaks how
many orders the shop has taken. `total_price` keeps its exact current meaning (whole so'm, the value
Click validates against) — **do not change how it is computed.**

### Translation access

No `django-modeltranslation` dependency. A single helper:

```python
# core/i18n.py
def tfield(obj, field):
    """Return obj.<field>_<active lang>, falling back to the Uzbek base field."""
```

Exposed to templates as `{{ product|t:"name" }}`. Uzbek lives in the base field, so every existing
row keeps working with no backfill.

---

## 8. Design system specification

Built once in Phase 2, then never re-invented. Lives in `static/css/tokens.css`.

### Structure (no build step; HTTP/2 makes multiple files free)

```
static/css/   tokens.css · base.css · components.css · pages.css · panel.css
static/js/    main.js · gallery.js · variant.js · map.js · panel.js
```

`map.js` talks only to a thin internal wrapper (`GX.map`) exposing `init`, `addMarkers`,
`onMarkerSelect`, `setPin`, `getPin`, `reverseGeocode`. No page ever calls a Yandex global directly —
that is what makes a provider swap a one-file change.

### Token set (values decided in Phase 2, shape decided now)

```
Colour     --c-bg, --c-surface, --c-surface-2, --c-fg, --c-fg-muted, --c-fg-subtle,
           --c-line, --c-line-strong, --c-brand, --c-brand-fg, --c-brand-hover,
           --c-success, --c-warning, --c-danger, --c-info  (+ their -bg pairs)
Space      --s-1 4 · 2 8 · 3 12 · 4 16 · 5 24 · 6 32 · 7 48 · 8 64 · 9 96 · 10 128 (px)
Type       --f-display, --f-body, --f-mono
           --fs-xs 12 · sm 14 · base 16 · lg 18 · xl 20 · 2xl 24 · 3xl 32 · 4xl 40 · 5xl 56 · 6xl 72
           --lh-tight 1.1 · snug 1.3 · normal 1.55 · loose 1.75
           --fw-regular 400 · medium 500 · semibold 600 · bold 700 · black 900
Radius     --r-sm 4 · md 8 · lg 16 · full 999px
Shadow     --sh-sm, --sh-md, --sh-lg
Motion     --t-fast 120ms · base 200ms · slow 320ms · --ease-out cubic-bezier(.16,1,.3,1)
Layout     --container 1280px · --container-wide 1600px · --pad-x clamp(16px, 5vw, 48px)
Z-index    --z-drawer 100 · --z-modal 200 · --z-toast 300
Break-     360 · 480 · 768 · 1024 · 1280 · 1600  (min-width, mobile-first)
points
```

**Base body font size moves from 14 px to 16 px.** 14 px body text is the single biggest reason the
current site reads as cramped and amateur on mobile.

### Brand mark

The six-point asterisk carries over. It is a good mark — geometric, distinctive, reads at 16 px, and
works as a logo, a bullet, a loading spinner and a section divider.

Current state: `static/img/favicon.svg` is a **traced** path with a 3125 pt viewBox and hundreds of
nodes (1.9 KB). Phase 1 **redraws it geometrically** — three rotated bars on a `0 0 24 24` viewBox,
roughly 300 bytes, exact at every size, recolourable via `currentColor`. Same mark, correctly built.

Deliverables: `logo-mark.svg`, `logo-full.svg` (mark + GRAPHIX wordmark), `logo-stacked.svg`, each in
light and dark lockups. Source PNG archived at `docs/brand/logo-mark-source.png`.

### Component inventory

Buttons (primary / secondary / ghost / danger; three sizes; loading and disabled) · Text input,
textarea, select, checkbox, radio, quantity stepper, OTP cells · **Search field (header)** · Product
card (image, name, price, heart with count) · Product gallery with thumbnails, swipe and zoom · Size
selector with out-of-stock state · **Spec strip** (GSM / material · print method · fit) · **Star
rating** (display + input) · **Review card** (rating, text, photos, verified badge) · Heart button
with count · **Share button** · Badge / pill (order status, "Yangi", "Ommabop", "Tugadi") · Modal /
sheet (mobile sheet, desktop dialog) · Toast · Breadcrumb · Pagination · Empty state · Skeleton
loader · Responsive table (stacks on mobile) · Filter panel (sidebar desktop, bottom sheet mobile) ·
**Pickup-point picker** (region/district selects + scrollable branch list + map) · Tabs · Accordion ·
Language switcher · Nav (desktop bar + mobile drawer) · Footer.

### Visual direction — how it gets chosen

The current site's problem is not that it's dark. It's that it's *only* shouting typographic
gestures with no hierarchy, no warmth, and no room for the product. Phase 2 does not begin by writing
CSS. It begins by producing **three complete static HTML mockups of the same product page**, each a
different, deliberate direction — and one is chosen before a line of production CSS is written.

Each is delivered as a working responsive page at 390 px and 1440 px, using real product photography,
not placeholder grey boxes.

Rejected on sight: purple/blue gradient meshes, glassmorphism, floating 3D shapes, generic hero +
three-feature-icons layout, decorative emoji, stock lifestyle imagery that isn't the actual product.

### Photography and imagery standard

- Every product: minimum 4 images — flat-lay front, flat-lay back, a detail crop of the print, and
  one on-body shot.
- Consistent background, lighting and crop across the whole catalogue.
- Square (1:1) or portrait (4:5) — one ratio for the entire catalogue, chosen in Phase 2, never mixed.
- Delivered as WebP at 400 / 800 / 1600 px via `srcset`, ≤ 250 KB each.

*If the product photos are inconsistent, no amount of CSS will make the shop look professional.*

---

## 9. The phases

---

### Phase 0 — Stabilise and prepare

*Goal: a clean, trustworthy starting point. No user-visible change.*

1. ✅ Restore the seven deleted lines in `vm/vm/settings.py`; confirm `runserver` starts.
2. ✅ Untrack the committed `.pyc` files (48, not 33) and `.idea/`; rewrite `.gitignore`.
3. ✅ Remove `djangorestframework_simplejwt`, `django-cors-headers` and `PyJWT`; verify nothing
   imports them; rewrite `requirements.txt` as UTF-8.
4. ✅ Fix the three dead footer category links — rendered from a `nav_categories` context processor
   (§17 #33).
5. ✅ Delete the stale Click TODO block from `payment/payment.html`.
6. ✅ Add `CSRF_TRUSTED_ORIGINS` to settings, read from the environment; document it in
   `.env.example`.
7. ⏩ **Moved to Phase 1** — Redis is installed while provisioning the new VPS. `settings.py`
   already reads `REDIS_URL` and falls back to LocMemCache, so no code change is pending (§17 #31).
8. ✅ Create `docs/` and place this plan at `docs/PLAN.md`. Set up the branch convention.
9. ⏩ **Moved to Phase 1** — the old VPS is being replaced and its database holds no data worth
   migrating, so there is nothing yet to restore. The backup *and a verified restore* are set up on
   the new VPS, before it carries real orders (§17 #31).
10. ✅ Write four smoke tests: home renders, shop renders, login works, checkout creates an order.
    They live in `vm/core/tests.py` because they cross app boundaries; Phase 10 grows the suite
    per-app around them.

**Definition of Done:** `runserver` starts cleanly · `git status` empty after a build ·
`manage.py check --deploy` reports no new issues · four smoke tests pass.
*(The restore criterion moved to Phase 1 with item 9.)*

**Verified 2026-09-08:** `runserver` starts with no warnings and serves `/` with 200 ·
`git status` clean after a test run and a `collectstatic` · `check --deploy` reports 0 issues with
`DEBUG=False` (the 5 warnings under local `DEBUG=True` are all settings the production block sets) ·
`makemigrations --check` reports no changes · 4 tests pass in 0.9 s.

---

### Phase 1 — Rebrand to GRAPHIX

*Goal: the site is called GRAPHIX everywhere, on its own domain, with nothing broken.*

Domain secured. Eskiz sender approved under the GRAPHIX name.

**Phase 1 is split (§17 #36).** Everything that can be done locally is **1a**; everything that needs
a running server is **1b**. Kamronbek is buying a new VPS (Ubuntu 24.04, 2 vCPU / 4 GB / 40 GB SSD)
and will not deploy until the site is worth deploying, so 1b is deliberately parked. The rest of the
plan does **not** wait for it: Phase 2 starts as soon as 1a is done.

---

#### Phase 1a — brand and code *(complete, 2026-09-09)*

1. ✅ **Redraw the brand mark geometrically** (§8) → `static/img/logo-mark.svg`, **225 bytes**,
   `0 0 24 24`, `currentColor`, down from a 1.9 KB traced path with hundreds of nodes.
   The lockups (`logo-full.svg`, `logo-stacked.svg`) **move to Phase 2** — they need the display
   typeface, which Phase 2 chooses (§17 #38).
2. ✅ **Icon set**, all one identity — a white mark on a black tile (§17 #40): `favicon.svg` (271 B),
   `favicon.ico` (16/32/48), `apple-touch-icon.png` (180), `icon-192.png`, `icon-512.png`,
   OG share image (1200 × 630). `site.webmanifest` is rendered as a **template** through
   `{% static %}`, like `robots.txt`, so the icon paths survive Phase 9's hashed static files.
3. ✅ Replace every user-facing "ValleyMade" / "Valleymade" / "VM" string: templates, `<title>`, meta
   description, footer, admin site header, SMS bodies in `user/otp.py` and `user/password_reset.py`,
   `contact.html`, `robots.txt`, `README.md`, the wsgi/asgi/settings docstrings, and two migration
   comments. The signup-OTP SMS typo `ro'yhatdan` → `ro'yxatdan` was fixed in passing.
4. ✅ **Set the canonical contact details** everywhere, replacing the inconsistent pair:
   - Email — `abdurahmonboboyev.magic@gmail.com`
   - Phone — `+998 50 788 84 36`
   - Telegram — [@greatestamal](https://t.me/greatestamal)

   *Recommended alongside this: a branded `info@graphix.uz` forwarding to the Gmail address. It costs
   nothing with the domain and reads considerably more credible on a store's contact page (§18 #2).*
5. ✅ Home hero and tagline: `Valley/Made` → `GRAPHIX`, and the sub-line
   `Futbolkalar · Arzon · Dastavka` → **"Premium sifat · 100+ dizayn · O'zbekiston bo'ylab yetkazib
   berish"**. *"Arzon" (cheap) directly contradicted the §2 positioning and is gone.*
   **The design count is hardcoded and is not yet true** — Kamronbek's call (§17 #39).
   Risk #14 stays open and **Phase 11 item 2 is now a hard launch gate.**
6. ✅ **Social meta** in `base.html` — `og:site_name/type/title/description/url/image`,
   `og:image:width/height`, and `twitter:card`, each overridable per page by a template block.
   Phase 9 adds the per-page and per-product values; this is the sitewide default.
7. ✅ Dead footer links removed — "Yetkazib berish" and "Qaytarish" pointed at `#` (their pages
   arrive in Phase 8), as did Instagram and TikTok (§18 #7). The footer now carries the real
   Telegram, phone and email.

**Phase 1a Definition of Done:** zero occurrences of "ValleyMade" in `templates/`, `static/` or any
`.py` · one canonical email, phone and Telegram handle sitewide · every icon and the manifest serve
200 · the smoke tests still pass · `manage.py check` clean.

**Verified 2026-09-09:** the only remaining "ValleyMade" strings are four deliberate ones in
`README.md` (the repository name and the rebrand note) · all nine assets serve 200 ·
`logo-mark.svg` 225 B, `favicon.svg` 271 B · manifest serves as `application/manifest+json` ·
4 smoke tests pass · `manage.py check` reports no issues.

---

#### Phase 1b — deployment *(blocked: the VPS has not been bought yet)*

Do **not** start this until there is a server. Nothing else in the plan depends on it, and the site
is not worth deploying until Phases 2–6 have run.

8. **Provision the new VPS** (Ubuntu 24.04, 2 vCPU / 4 GB / 40 GB SSD) and deploy to it as a fresh
   install — there is nothing to migrate (§17 #34): nginx `server_name`, certbot for graphix.uz +
   www, gunicorn + systemd, PostgreSQL, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, the `.env`.
   Two items moved here from Phase 0 (§17 #31):
   - **Redis** — install it, set `REDIS_URL`, and confirm the rate limiter counts correctly across
     more than one gunicorn worker. Without it, risk #15 is live from the first day of traffic.
   - **Backups** — nightly `pg_dump` plus a `media/` copy, both off-server, and a **verified
     restore** into a scratch database with row counts checked, before the site takes a real order.
     An untested backup is not a backup.
9. **Register the Click webhook** at `https://graphix.uz/payment/click/update/`; verify with a real
   1 000 so'm payment end to end. *The single highest-risk step in the project — a wrong webhook URL
   means silent payment failures.*
10. Confirm an OTP SMS arrives with the GRAPHIX sender name.
11. Google Search Console: add graphix.uz, verify, submit the sitemap. *No Change of Address — there
    is no old property to move from (§17 #35).*

**Phase 1b Definition of Done:** graphix.uz serves over HTTPS · a real Click payment completes and
the order flips to `paid` · an OTP SMS arrives branded GRAPHIX · the OG image renders correctly when
pasted into Telegram · **Redis is live and the rate limiter counts correctly across multiple gunicorn
workers** · **a `pg_dump` + `media/` backup has been restored off-server with row counts checked.**

---

### Phase 2 — Design system and visual direction

*Goal: one agreed visual language, expressed as tokens and components, before any page is rebuilt.*

1. ✅ **Three directions**, reviewed at 390 px and 1440 px. **Built — awaiting Kamronbek's choice
   (§19 Q18).** They live in `docs/design/directions.html`: one self-contained file, no server, no
   network. Each renders in an iframe at its true width so the media queries actually run.
   - **A · Galereya** — the shop as a gallery. Bone ground, one ink, no accent, a lot of air;
     Unbounded very large for the product name, Onest for everything else, sizes as underlined
     text rather than boxes.
   - **B · Bosma** — the page as a print shop's spec sheet. Ruled rows, every value labelled,
     Oswald condensed uppercase for display, IBM Plex Mono for all data, one signal red used
     *only* for stock state.
   - **C · Tungi** — evolves the current darkness. Near-black ground, garment lit as a panel,
     Unbounded 800, and a single amber accent carrying price, stock and every CTA.

   Each is the *same* product page — gallery, title, price, size row with a sold-out state, size-guide
   link, spec strip, heart and share, delivery lines, description, related row, and a mobile sticky
   add-to-cart — so the comparison is treatment, not content.
2. Fill in every token value in `tokens.css`. **Blocked on item 1.**
3. Self-host the typefaces. Subset to Latin + Latin Extended (Uzbek needs `oʻ` and `gʻ`) + Cyrillic.

   > **Check U+02BB before choosing a face — it is a real elimination criterion.** Uzbek Latin
   > spells `oʻ` and `gʻ` with U+02BB MODIFIER LETTER TURNED COMMA. Phase 1a found that **Poppins
   > does not contain it** (it has U+02BC but not U+02BB), so every `Oʻzbekiston` set in Poppins
   > renders as tofu. Verify the cmap of every candidate — display face, body face and mono — for
   > U+02BB, U+02BC and U+00B7 before shortlisting it, not after. Also produce the wordmark
   > lockups here, once the display face is settled (§17 #38): `logo-full.svg` and
   > `logo-stacked.svg`, light and dark.

   ✅ **The screening has run** — `docs/design/typeface-screening.md`. 31 families tested by reading
   their `cmap` directly, **22 failed**. Only these can set Uzbek *and* Russian: **Unbounded, Oswald,
   Onest, Inter, IBM Plex Sans, Commissioner, Mulish, Noto Sans, IBM Plex Mono.** A second filter on
   spacing drops IBM Plex Sans and Mulish, which both render a visible gap as `O ʻzbekiston`.
   **IBM Plex Mono is the only monospace that passes, so `--f-mono` is settled** (§17 #43).
   The three directions each commit to a different pairing from this set; choosing a direction
   chooses the type.

   WOFF2 only, `font-display: swap`, preload the display face. *The current site pulls Inter from
   `rsms.me` — a third-party render-blocking request on every page load.*
4. Build `base.css` — reset, typography scale, layout primitives, utilities.
5. Build `components.css` — the full §8 inventory, every state (default, hover, focus-visible,
   active, disabled, loading, error).
6. Build a **living style guide** at `/boshqaruv/style/` (staff-only) rendering every component in
   every state. The reference for every later phase and the fastest way to catch drift.
7. Motion: standard transitions; the `prefers-reduced-motion` guard wired once, globally.
8. Icons: one consistent set as an inline SVG sprite. No icon fonts.
9. **Verify the above-the-fold rule**: on a 390 × 844 viewport the home hero must leave at least one
   partially visible row of product cards. This is a measured check, not a judgement call.

> **Photography note.** The directions are built on **drawn garment mockups**, not photographs —
> there is no product photography yet, and Kamronbek chose to proceed rather than wait (§17 #42).
> Layout, crop, hierarchy and type are judgeable from them. *Whether the shop looks professional*
> is not — that question belongs to the photography, and §8 is explicit that no CSS rescues bad
> photos. The generator lives in `docs/design/mockup/`; real shots drop straight in.

**Definition of Done:** a direction is chosen and recorded in §17 · `tokens.css` has no `TODO` ·
every component exists in the style guide with all states · contrast passes on every token pairing ·
fonts self-hosted and preloaded · CSS under budget · the style guide renders at all six breakpoints.

---

### Phase 3 — Internationalisation foundation

*Goal: uz / ru / en infrastructure in place, so every template built afterwards is translatable from
the first line.* **Deliberately before the page rebuild** — adding i18n afterwards means editing
every template twice.

1. Settings: `LANGUAGES = [('uz', "O'zbekcha"), ('ru', 'Русский'), ('en', 'English')]`,
   `LANGUAGE_CODE = 'uz'`, `LOCALE_PATHS`. `LocaleMiddleware` **after** `SessionMiddleware`, **before**
   `CommonMiddleware`.
2. Wrap the public URL tree in `i18n_patterns(..., prefix_default_language=False)`. Keep the webhook,
   admin, sitemap, robots, media and static routes **outside** it (§6). Verify the Click webhook still
   resolves at exactly `/payment/click/update/`.
3. Add `set_language` and the language switcher (POST, preserves the current page).
4. `<html lang>` and `hreflang` alternates in `base.html`; sitemap emits all three language URLs.
5. Translation model fields and the `tfield` helper + `|t` filter (§7).
6. Django admin groups translation fields clearly per language.
7. `locale/uz|ru|en/LC_MESSAGES/`; `makemessages`; wire `compilemessages` into deployment.

**Translation quality standard** — this decides whether the site reads professional or machine-made:

- **Uzbek** is the source of truth. Latin script. Correct `oʻ` / `gʻ` (U+02BB) — never a plain ASCII
  apostrophe in body copy. **Phase 3 converts the whole codebase in one pass.** Phase 1a deliberately
  kept ASCII apostrophes in the templates rather than half-converting them: the existing ~40 Uzbek
  strings all use `'`, and a file with both conventions is worse than a file with one. The strings
  move into `.po` files here anyway, which is the moment to fix them all at once. The only place the
  correct character is already in use is the OG image, which is a rendered asset, not sweepable text.
- **Russian** written in natural commercial register, *not* word-for-word from the Uzbek. The two
  languages differ enough structurally that literal translation reads as broken.
- **English** written for a fluent reader, not translated.
- **Never** bulk-machine-translate into `.po` files. Every string reviewed before `compilemessages`.
- Translator comments on any string ambiguous out of context.

**Definition of Done:** all three languages resolve and render · switching preserves the current page
· the Click webhook resolves and completes a test payment · sitemap emits three URLs per page with
correct `hreflang` · translation fields editable in the admin · every existing string translated to
native quality.

---

### Phase 4 — Data model expansion

*Goal: every schema change landed and migrated, so the UI phases build against a final model.*

1. Write all migrations from §7 — product (slug, translations, tags, `likes_count`, rating denorm,
   spec fields, `size_chart`, `is_active`), `Tag`, category, colour, variant stock, `SizeChart` +
   `SizeChartRow`, `ProductLike`, `Review` + `ReviewImage`, `DeliveryOption`, `PickupPoint`, order
   (`order_no`, lat/lng, delivery option + price, pickup point + snapshot), and the cart changes
   (nullable `user`, `session_key`, replaced unique constraints).
2. **Data migration: generate slugs** for every existing product from the Uzbek name, numeric suffix
   on collision.
3. **Data migration: generate `order_no`** for every existing order (`GX-<YYMMDD>-<seq>`).
4. Set `Variant.stock`: 10 where `available` is true, 0 otherwise — nothing accidentally leaves sale.
5. **Seed the two `DeliveryOption` rows** from the §7 table.
6. **Seed `PickupPoint`** — see the seeding note below.
7. **Seed the initial `Tag` taxonomy** (§19 Q6).
8. Extend `add_variant` in `cart/services.py` to respect stock. **Preserve the existing
   `Least(F('quantity') + qty, 99)` behaviour**, capping at `min(99, stock)`.
9. Decrement stock on successful payment (in `apply_successful_payment`), inside the existing
   transaction. Restore on cancellation.
10. Product URL moves to `/mahsulot/<slug>/`, with a permanent 301 at `/item/<pk>/`.
11. Seed the size charts, using the owner's uploaded chart images.
12. Admin auto-assigns a default colour on product creation, so colour never surfaces in the workflow.

**Pickup-point seeding** — a management command, `seed_pickup_points`, that:

- Reads a CSV at `data/pickup_points.csv` (code, name, region, district, address, lat, lng, hours,
  phone) — the authoritative input, committed to the repo so the dataset is version-controlled and
  reviewable.
- Is idempotent: upserts on `code`, never duplicates, never silently deletes.
- Deactivates rather than deletes branches that disappear from the CSV, so historical orders keep
  their foreign key.

The CSV is assembled from an official Uzpost list if one can be obtained (§19 Q3), cross-checked
against OpenStreetMap, and **verified by hand**. Launch scope is a decision (§19 Q4) — Tashkent plus
regional capitals is a sane starting set; nationwide can follow.

**Definition of Done:** `makemigrations --check` clean · every product has a unique slug, every order
an `order_no` · `/item/<pk>/` 301s to the slug URL · a stock-exhausted variant cannot be over-ordered
· a paid order decrements stock, a cancelled one restores it · both delivery options exist · the
pickup-point seed runs twice with no duplicates · full test suite passes.

---

### Phase 5 — Frontend rebuild

*Goal: every page rebuilt on the design system. The visible transformation.*

Highest commercial impact first. Each page is finished (all breakpoints, all states, all three
languages) before the next begins.

1. **`base.html`, nav, footer, drawer** — the shell. Includes the **global search field**, language
   switcher, **heart count**, cart count, and the mobile drawer.
2. **Product detail (`/mahsulot/<slug>/`)** — the most important page on the site:
   - Gallery with thumbnails, swipe, pinch-zoom
   - Title, price, **star rating + review count** (hidden entirely until the first approved review —
     an empty rating looks worse than no rating)
   - Size selection with clear out-of-stock states; **no colour picker**
   - **Size-guide link** beside the sizes
   - **Spec strip** — GSM / material · print method · fit
   - **Heart** (saves + counts) and **share** buttons
   - Description, **reviews section**, related products
   - Delivery line: "15 000 so'm pochta bo'limiga · 30 000 so'm eshikkacha"
   - Sticky add-to-cart bar on mobile
3. **Shop (`/shop/`)** — responsive grid; filters as sidebar on desktop, bottom sheet on mobile;
   **tag filters**; sort including **"Ommabop"** (by `likes_count`) and **"Reyting bo'yicha"**;
   pagination; skeleton loading; a real empty state.
4. **Home (`/`)** — hero that shows actual product and **obeys the above-the-fold rule**; tagline;
   a **"Siz uchun" (For you) row** — filled with most-liked initially, swapped for the real
   recommender in Phase 13; new arrivals; category entry points; brand statement.
5. **Search results (`/qidiruv/`)** — global search across name, description and tags.
6. **Cart** — **works for anonymous visitors**; line items with thumbnails, quantity steppers, totals;
   the checkout button prompts login for guests, stating plainly that the cart is kept.
7. **Liked items (`/saqlanganlar/`)** — same grid as shop, with remove and "add to cart" actions.
8. **Auth pages** — login, signup, OTP, the three password-reset steps. Behaviour unchanged; only
   presentation.
9. **Account** — home, order history, settings. History uses the table that stacks into cards on
   mobile, with a "leave a review" action on delivered orders.
10. **Checkout, payment, order detail, order status** — presentation only here; map, pickup points and
    delivery tiers arrive in Phase 6.
11. **About, contact, delivery & returns, size guide, 404, 500, 403.**

**Per-page checklist — none optional:**

- [ ] Renders at 360 / 390 / 768 / 1024 / 1440 / 1920 px
- [ ] No horizontal scroll at any width
- [ ] All three languages, including the longest string in each (Russian runs ~20 % longer)
- [ ] Keyboard navigable, visible focus ring on every interactive element
- [ ] Loading, empty, error and success states designed
- [ ] Images have `alt`, `width`, `height` and `srcset` (no layout shift)
- [ ] No hardcoded colour, spacing or font-size value
- [ ] Lighthouse mobile ≥ 90

**Definition of Done:** every page passes its full checklist · the old `main.css` is deleted · CSS and
JS under budget · nothing in `templates/` references a removed class.

---

### Phase 6 — Product and checkout features

*Goal: the features that make the shop genuinely better to use.*

**6a — Size guide.** Modal (desktop dialog / mobile bottom sheet) from a "O'lcham jadvali" link beside
the size selector. Renders the chart image full width, pinch-zoomable, with a descriptive `alt`. Where
`SizeChartRow` entries exist, a responsive table below it with the selected size highlighted. Shows
the chart note in the active language. Standalone `/size-guide/` page for SEO and the footer.

**6b — Likes (save + popularity) and share.**

- Heart on the product card and product page, with the live count.
- POST toggle, CSRF-protected, via `fetch` with optimistic UI and rollback on failure. **Works without
  JavaScript** — a plain form POST that redirects back.
- `likes_count` updated with `F('likes_count') ± 1` inside a transaction.
- Anonymous visitors see the count and get a login prompt on click.
- Rate limited via `core/ratelimit.py` (60 toggles / 5 min / user).
- New sorts: **Ommabop** (`?sort=popular`) and **Reyting** (`?sort=rating`).
- **Share button** — `navigator.share` on mobile; on desktop a menu with copy-link, Telegram and
  Instagram. Telegram first: it is where Uzbek sharing actually happens.

**6c — Global search.** Header search field on every page, posting to `/qidiruv/`. Matches product
name (all languages), description and tag names. Debounced suggestions are a nice-to-have, not a
requirement; the results page is.

**6d — Map, pickup points and location.** *(Highest complexity in this phase.)*

- All map code behind the `GX.map` wrapper (§8). No page calls a Yandex global directly.
- Yandex Maps JS API under the commercial licence, loaded **only** where a map is shown, `async`,
  after the form is interactive — never blocking first paint.
- **Pickup-point picker — list-first, map-second.** Region select → district select → a scrollable
  list of branches, each showing name, address and working hours. Selecting a list item highlights its
  pin; clicking a pin selects the list item. A "nearest to me" button sorts by distance behind an
  explicit geolocation permission prompt.

  *Why list-first: on a 390 px screen a pure-map picker with thirty overlapping pins is genuinely
  hard to use, and it fails completely when the map does. The list is the control; the map is
  confirmation. This is the pattern every large CIS marketplace settled on.*
- **Door delivery:** draggable pin defaulting to Tashkent centre, "use my location" button, and
  reverse-geocoding into the address textarea in the active language. The customer can freely edit
  the result.
- **The map is assistive, never required.** The address textarea stays required and authoritative for
  door delivery; the pickup list works as a plain `<select>` with no map at all. A customer who denies
  location permission, blocks the script, or has JavaScript off can still complete checkout. **Hard
  requirement, not a nicety.**
- Store `latitude`/`longitude` (door) or `pickup_point` + `pickup_snapshot` (office) on the order.
- The admin order view and the Telegram notification both show a maps deep link for the courier.
- Graceful failure: if the script fails to load, the map area hides itself and everything still works.
  Never a broken grey box.

**6e — Delivery tiers and cash on delivery.**

- `DeliveryOption` selector at checkout: **15 000 so'm to an Uzpost branch** or **30 000 so'm to the
  door**. Choosing the branch option reveals the pickup-point picker; choosing door reveals the map
  and address.
- Both tiers ship via Uzpost, Tashkent and regions alike — stated at checkout, on the confirmation, on
  `/yetkazib-berish/` and in the terms. The customer should never be surprised about who delivers.
- `delivery_price` snapshotted onto the order; the total computed inside the existing locked
  transaction via `create_order_from_cart`'s `delivery` argument. **Do not restructure the
  locked-total computation.**
- Enable the "Naqd pul" (cash on delivery) option that is currently rendered but disabled. A cash
  order skips Click and goes straight to `processing`.

**6f — Telegram notifications.**

A new `core/telegram.py`, structured exactly like `core/sms.py`: module logger, catches everything,
logs failures, returns a boolean, **never raises**. Credentials `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID` in `.env` (§19 Q2) — the code must degrade silently and log a warning when they
are unset, so local development is unaffected.

Fired via `transaction.on_commit()` so a notification is never sent for a rolled-back transaction and
a Telegram outage can never fail a checkout.

| Event | Message contents |
|---|---|
| **New order** | Order number · item count and each line (name / size × qty) · total · delivery tier and price · **pickup branch or map link** · payment method · customer name and phone (tap-to-call) · short address · link to the order in the admin panel |
| **Payment confirmed** | Order number · amount · "To'landi ✅" |
| **New contact message** | Sender name and username · phone (tap-to-call) · topic · message body · admin link |
| **New review awaiting moderation** | Product · rating · excerpt · whether photos were attached · admin link |

Telegram HTML parse mode; all user-supplied text HTML-escaped.

**6g — Anonymous cart.**

- Guests get a session-keyed cart (§7). `cart_add` no longer redirects to login.
- On login **and** on signup, merge the guest cart into the user's open cart inside a transaction with
  both carts locked: sum quantities, cap at `min(99, stock)`, delete the guest cart. If the user has no
  open cart, claim the guest cart by setting `user`.
- Checkout still requires login; the prompt says plainly that the cart is preserved.
- A management command prunes anonymous carts older than 30 days.
- **Critical regression guard:** `_cancel_and_delete` in `user/views.py` deletes unverified users.
  It must never delete a user who has an order or a claimed cart. Add the guard and a test — this is
  a real data-loss path once carts and accounts start meeting each other.

**Definition of Done:** the size guide shows the chart image (and table where rows exist) on every
product · liking persists, counts correctly, and both new sorts work · share works on mobile and
desktop · global search returns sensible results in all three languages · a checkout completes with a
pickup branch selected, with a door pin, **and with JavaScript disabled** · delivery price and pickup
snapshot are frozen on the order · a cash order reaches `processing` without touching Click · a Click
order still completes end to end · a Telegram message arrives within seconds of an order, a message
and a review · unsetting the Telegram credentials breaks nothing · a guest cart survives login and
merges correctly · an unverified user with an order is never deleted.

---

### Phase 7 — Admin panel

*Goal: a focused staff panel at `/boshqaruv/` that runs the daily job from a phone. Django admin stays
for everything else.* Guarded by `staff_member_required`, built on the same design system, mobile-first.

**The owner adds every product himself, with photos, from this panel.** Product creation is therefore
the panel's most important screen, not an afterthought — it gets the same design care as the
storefront's product page.

1. **Dashboard** — today and this week: orders, revenue, awaiting payment, to pack, low stock, unread
   messages, **reviews awaiting moderation**.
2. **Orders** — filter by status, date, payment method, delivery tier; search by `order_no`, phone or
   customer; inline status change; detail view with items, customer, tap-to-call phone, address or
   pickup branch, map link, and notes. Status changes logged with who and when.
3. **Products** — the core screen:
   - List with thumbnail, price, total stock, availability; toggle availability and edit stock and
     price inline without a page reload.
   - **Create / edit**: name and description per language, category, **tags**, **spec fields (GSM,
     material, print method, fit)**, size chart, multi-image upload with drag-to-reorder and instant
     preview, and a **size × stock grid** (colour hidden — the default colour is applied silently).
   - Client-side image validation before upload (type, dimensions, file size) with a clear error — the
     owner should never wait 30 s for an upload that will be rejected.
4. **Reviews** — moderation queue: approve or reject, with the photos shown at a reviewable size.
   Approving recomputes the product's `rating_avg` and `review_count`.
5. **Pickup points** — search, edit, activate/deactivate, and correct coordinates on a map.
6. **Size charts** — upload chart images, attach to categories or products, optional measurement rows.
7. **Delivery options** — edit prices, notes and the (currently unused) free threshold without code.
8. **Tags** — create and rename, in all three languages.
9. **Messages** — contact-form inbox, read/unread, tap-to-call.
10. **Style guide** — `/boshqaruv/style/` from Phase 2.

**Definition of Done:** a complete product with four images, tags, specs and a full size/stock grid can
be created from a phone at 390 px in one sitting · every daily task doable from a phone · non-staff get
403 · inline edits save without a full reload · status changes audit-logged · review approval updates
the product rating · the panel shares the site's design tokens exactly.

---

### Phase 8 — Legal documents and content

*Goal: real, complete, trilingual legal pages, and site copy that reads like a brand.* Written
in-project, to a real standard, against Uzbek law — not filled from a generic template.

1. **Privacy policy** (`/privacy/`) — the data controller and how to contact them; what is collected
   (name, username, phone, delivery address, map coordinates, chosen pickup branch, order history,
   reviews and review photos, contact messages, IP for rate limiting, session and cart data); why and
   on what legal basis; who it is shared with (**Eskiz** for SMS, **Click** for payment, **Yandex**
   for maps and geocoding, **Uzpost** for delivery, **Telegram** for internal order notifications);
   retention; the customer's rights and how to exercise them; cookies and browser storage, including
   the anonymous cart and the `sessionStorage` signup draft; children's data; how changes are
   announced. Written against the Uzbek personal-data law
   (*"Shaxsga doir ma'lumotlar to'g'risida"gi qonun*).
2. **Terms of use** (`/terms/`) — parties and definitions; registration and phone verification;
   ordering and when a contract forms; prices, currency and VAT; payment via Click and cash on
   delivery; **delivery terms — 15 000 so'm to an Uzpost branch, 30 000 so'm to the door, all via
   Uzpost nationwide, expected timeframes, uncollected-parcel policy**; returns, exchanges and
   cancellation, including the sizing disclaimer (measurements approximate, ±1 cm); **review rules and
   the moderation policy**; intellectual property in the printed designs; acceptable use; limitation of
   liability; governing law and disputes; amendment procedure.
3. **Delivery & returns page** (`/yetkazib-berish/`) — the plain-language version customers actually
   read before buying, including how pickup collection works.
4. All three documents in all three languages, with a "last updated" date and version history.
5. Linked from the footer and from the signup consent checkbox — which currently links only to terms
   and must link to both.
6. Rewrite About and Contact in the new brand voice, all three languages.
7. Product copy guidelines: a template for a product description (what it is, the print, fabric and
   weight, fit, care) so the catalogue stays consistent as it grows.

> These documents create real legal obligations under Uzbek law. They will be written carefully and
> completely, but an independent legal review before launch is still worth the cost — recommended,
> not a launch blocker.

**Definition of Done:** three documents complete in three languages · linked from footer and signup
consent · dated and versioned · delivery and review terms match the implemented behaviour exactly.

---

### Phase 9 — Performance, SEO and accessibility

**Performance**

1. **Image pipeline** — on upload, generate 400 / 800 / 1600 px WebP derivatives with Pillow; serve via
   `srcset` + `sizes`; keep the original as archival. Applies to product images **and review photos**.
   *The current 3.8 MB PNG in `media/products/` is roughly 15× the entire budget for one image.* Since
   the owner and customers both upload straight from phones, this pipeline is what stands between the
   catalogue and a four-second load.
2. Backfill derivatives for existing images with a management command.
3. `loading="lazy"` below the fold; `fetchpriority="high"` on the LCP image.
4. Explicit `width`/`height` on every image.
5. nginx: gzip and brotli, long `Cache-Control` on hashed static assets, HTTP/2.
6. `ManifestStaticFilesStorage` for cache-busted filenames.
7. Audit every list view for N+1 queries (the current shop and item views already do this well).
8. Indexes on everything filtered or ordered: `slug`, `likes_count`, `rating_avg`, `created_at`,
   `order_no`, `Variant(product, available)`, `PickupPoint(region, district)`.

**SEO**

9. Unique `<title>` and meta description per page, per language.
10. Open Graph and Twitter cards everywhere, product-specific on product pages. *In Uzbekistan most
    sharing happens on Telegram — the OG image and title are frequently the first thing a potential
    customer ever sees of the brand.*
11. JSON-LD: `Product` (with `offers` and **`aggregateRating` once reviews exist**), `Review`,
    `BreadcrumbList`, `Organization`.
12. Sitemap across all three languages with `hreflang`; canonicals; updated `robots.txt`.
13. Verify every 301 from the old domain and the old `/item/<pk>/` URLs.

**Accessibility**

14. Full keyboard pass over every page and flow.
15. Screen-reader pass on the critical path: shop → product → cart → checkout.
16. Contrast audit against the final palette.
17. Focus trapping in modals, the drawer and the pickup picker; focus restored on close.
18. `aria-live` for the cart count, toasts and like-count updates.
19. Verify with reduced motion enabled and at 200 % browser zoom.

**Definition of Done:** Lighthouse mobile ≥ 90 on home, shop, product, cart and checkout · all §5
budgets met · zero axe-core violations · valid structured data on every product page (Rich Results
Test) · the whole checkout flow completable with the keyboard alone.

---

### Phase 10 — Testing and hardening

**Test suite** (Django's built-in runner — no new dependency):

| Area | Tests |
|---|---|
| `user` | Phone normalisation across formats · signup creates an unverified user and sends an OTP · correct OTP verifies · wrong OTP counts an attempt · 7 wrong attempts delete the account · expiry deletes the account · `expire_verification` refuses a premature POST · resend respects the cooldown · full password-reset happy path · reset cannot skip the OTP step · **a user with an order is never deleted by `_cancel_and_delete`** |
| `cart` | Add creates a line with a snapshotted price · adding again bumps quantity, caps at 99 · price change does not alter an existing line · quantity 0 removes the line · another user's cart item is inaccessible · stock cap respected · **anonymous cart is created and persists** · **guest cart merges on login, quantities summed and capped** · **guest cart is claimed when the user has no open cart** |
| `payment` | Checkout creates an order and closes the cart · concurrent checkout does not duplicate · empty cart rejected · **office tier charges 15 000 and requires a pickup point** · **door tier charges 30 000 and rejects a pickup point** · **delivery price is snapshotted and unaffected by a later price change** · **pickup snapshot survives the branch being deactivated** · webhook marks paid · webhook idempotent · cancellation restores stock · cash order skips Click |
| `product` | Shop filters by category, size and tag · sorts by price, popularity and rating · search matches name, description and tags in all languages · only available variants listed · slug resolves · old PK URL 301s · size-chart resolution falls back product → category → none |
| `reviews` | Only a delivered purchaser can review · one review per user per product · a new review is `pending` and invisible · approval publishes it and updates `rating_avg` and `review_count` · rejection does not · photo upload validates type and size |
| `core` | Rate limiter allows up to the limit and blocks past it · fails open on cache error · contact requires login to POST · **Telegram send failure does not break the request** · **missing Telegram credentials handled cleanly** · **`seed_pickup_points` is idempotent and deactivates rather than deletes** |
| `i18n` | All three languages resolve · the webhook path is unprefixed · `tfield` falls back to Uzbek |
| Smoke | Every URL in §6 returns 200 (or the right redirect) for anonymous, logged-in and staff users |

**Security hardening**

1. `manage.py check --deploy` clean.
2. Verify HSTS, secure cookies, `SECURE_PROXY_SSL_HEADER`, CSP headers.
3. Rate limiter correct with Redis across multiple gunicorn workers.
4. All new endpoints (like, review, panel, pickup lookup) enforce authentication, ownership and CSRF.
5. No view leaks another user's order, cart or liked items.
6. Click webhook validates signatures; a replayed callback is a no-op.
7. **Review photo upload rejects non-images and oversized files server-side**, not only in the browser,
   and strips EXIF (phone photos carry GPS coordinates).
8. Admin panel image upload validated server-side too.
9. Review `DEBUG=False` error pages for information leakage.

**Operations**

10. Verify the nightly `pg_dump` cron **and a restore**, again.
11. Copy backups off-server.
12. **Back up `media/` too** — product photography and review photos are irreplaceable and are not in
    the database dump.
13. Confirm log rotation is working and disk usage bounded.
14. Uptime monitoring on `/` and on the webhook endpoint.

**Definition of Done:** full suite passes · `check --deploy` clean · an off-server backup of both the
database and `media/` restored successfully · uptime monitoring live and alerting.

---

### Phase 11 — Launch and after

1. Full catalogue loaded: real products, photography to the §8 standard, complete descriptions in three
   languages, correct stock, tags, specs and size charts.
2. **Verify the "100+ designs" claim is true**, or adjust the tagline.
3. Full manual pass on real devices — a mid-range Android and an iPhone, on mobile data, not wifi.
4. Final end-to-end live tests: a Click payment with a real card, a cash-on-delivery order, an office
   pickup order and a door order.
5. Verify Telegram notifications with the production bot token and chat ID.
6. Announce: Telegram channel, Instagram, Search Console.
7. Watch closely for 72 hours: server logs, failed payments, 404s in Search Console, Lighthouse field
   data, Telegram delivery.

**Optional, only if everything above is stable:** independent legal review of the Phase 8 documents ·
rename the internal package `vm` → `graphix` (touches settings module, wsgi, systemd, nginx, venv —
rehearse on a staging copy first).

---

### Phase 12 — Reviews and ratings

*Goal: verified, moderated customer reviews with photos.* **Runs between Phase 6 and Phase 7**, so the
moderation UI lands with the rest of the admin panel and the product page is built only once.

1. **Submission flow** — `/order/<id>/sharh/`, reachable from a delivered order in the account area and
   from a link in the order-complete SMS. Rating 1–5, optional text, up to 4 photos.
2. **Eligibility, enforced server-side:** the user must own an order with status `done` containing that
   product; one review per user per product; `Review.order` records which order granted the right.
3. **Moderation** — every review is `pending` on creation and invisible until a staff member approves
   it. Approval recomputes `rating_avg` and `review_count` from approved reviews only.
   *Photos are user-uploaded content on a public page; a moderation queue is not optional.*
4. **Display** — reviews section on the product page: average rating, distribution bars, individual
   cards with a "verified purchase" badge, photos in a lightbox, newest first with pagination.
5. **Photo handling** — same image pipeline as products, plus EXIF stripping (phone photos carry GPS).
6. **Telegram** notification when a review needs moderation (§6f).
7. **SEO** — `aggregateRating` and `Review` JSON-LD, which is what produces star ratings in Google
   results. A real, measurable acquisition win.
8. **Sort by rating** enabled on the shop page.

**Definition of Done:** only a delivered purchaser can review · a review is invisible until approved ·
approval updates the product rating correctly · photos are validated, resized and EXIF-stripped ·
rich-result validation passes on a product with reviews · the rating block is hidden entirely on
products with no approved reviews.

---

### Phase 13 — Recommendations

*Goal: "products you might like", driven by what the customer has liked.* **Runs after launch**, once
there is real like data — a recommender built before that has nothing to recommend from.

**This is deliberately not machine learning.** With 200–300 designs and a young user base, a
collaborative-filtering model would be over-engineering with a cold-start problem. A tag-overlap
recommender is a single SQL query, needs no new dependency, and is genuinely useful.

1. **Algorithm** — score every active product by the number of tags it shares with products the user
   has liked; exclude what they already liked or bought; tie-break by `likes_count`, then
   `rating_avg`, then recency. Cache per user for an hour.
2. **Fallbacks, and they matter more than the algorithm** — an anonymous visitor, or a user with no
   likes yet, gets most-liked-this-month. The "Siz uchun" row on the home page (built in Phase 5)
   simply changes what fills it; no template changes.
3. **Also on the product page** — "similar designs" by tag overlap with the product being viewed, which
   needs no user history at all and works from day one.
4. **Measure it** — log impressions and clicks on the row. If it does not outperform "most liked", the
   honest answer is to keep the simpler thing.

**Prerequisite:** the `Tag` taxonomy from Phase 4 must actually be applied to products. *A recommender
on `Category` alone is worthless when every product is a t-shirt* — tags are what carry the signal, and
they must be filled in as products are added, not retrofitted later.

**Definition of Done:** a user with likes gets recommendations that visibly reflect them · a user with
none gets a sensible fallback · the row never renders empty · the query is a single cached statement ·
click-through is measured against the most-liked baseline.

---

## 10. Adding new work during the project

The plan is expected to grow. This is the procedure, so growth doesn't turn into drift.

| Situation | Where it goes |
|---|---|
| Its phase hasn't started | Added directly into that phase's task list, and to its Definition of Done if substantial |
| Its phase is in progress | Added **only if it doesn't push the phase past its Definition of Done**; otherwise a new phase |
| Its phase is finished | A new phase at the end — never reopen a closed phase |
| A bug in shipped work | Fixed immediately in a `fix/` branch, outside the phase sequence, noted in §16 |

**Every addition gets:** a one-line description, a phase, an acceptance criterion, and a §17
decision-log row if it changes an approach rather than just adding work.

**A chat that hits a new idea mid-phase writes it into §18 (Backlog) and keeps going** — it does not
silently expand its own scope. Placing it into a phase is a decision made with Kamronbek.

New phases are appended as Phase 14, 15, … and **never renumbered**. Execution order lives in §13.

---

## 11. Explicitly out of scope

- Discount codes and promotions
- Multi-vendor / marketplace features
- A native mobile app or PWA offline mode
- Email (the site is deliberately phone-only)
- Live Uzpost tracking-number integration *(a strong candidate for a later phase once volume justifies
  the integration work)*
- Wishlist sharing between users
- Loyalty points
- Machine-learning recommendations (Phase 13 is deliberately not this)
- Custom-design ordering as a self-service flow — handled through the contact form, which is the right
  level of complexity for now

---

## 12. Risk register

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | Click webhook URL wrong on the new domain | **Critical** — silent payment failures | Register in Phase 1b, verify with a real 1 000 so'm payment, uptime monitoring on the endpoint. *(The old-domain 301 mitigation is gone — valleymade.uz is abandoned, §17 #35.)* |
| 2 | `i18n_patterns` prefixes the webhook path | **Critical** — every Click callback 404s | Explicitly excluded in §6; a dedicated test asserts the unprefixed path resolves |
| 3 | A migration corrupts production data | **Critical** | Verified backup before every deploy; migrations rehearsed on a restored copy |
| 4 | `_cancel_and_delete` deletes a user who now has an order or claimed cart | **Critical** — data loss | Guard plus a dedicated test in Phase 6g; called out in the Phase 6 Definition of Done |
| 5 | Yandex commercial licence costs more than the business can carry | High — a locked decision becomes unaffordable | All map code behind the `GX.map` wrapper, so switching provider is a one-file change; get pricing before Phase 6 (§19 Q1) |
| 6 | 30 000 so'm door delivery is below actual cost in far regions | High — every distant order loses money | Verify against Uzpost's published courier tariffs before launch (§19 Q5) |
| 7 | Machine-translated Russian/English makes the site read as cheap | High — undermines the whole rebuild | Human-quality copy per Phase 3; never bulk-translate `.po` files |
| 8 | Product photography inconsistent | High — no CSS can rescue it | Photography standard in §8; a Phase 11 blocker |
| 9 | Owner- and customer-uploaded phone photos are enormous | High — a 3.8 MB image already exists | Image pipeline in Phase 9 plus client-side validation at both upload points |
| 10 | Pickup-point data is incomplete, stale or wrong | High — parcels sent to a branch that has moved | We own the table; `pickup_snapshot` freezes what the customer chose; deactivate rather than delete; periodic re-verification |
| 11 | Review photos are abused (offensive or irrelevant content on a public page) | High — brand damage | Moderation queue; nothing is public until approved; Telegram alert on every pending review |
| 12 | Selling designs that reproduce other brands' trademarks | High — legal exposure and payment-processor risk | If the mockup artwork was placeholder, no issue. If any are intended products, they should be reviewed before listing (§19 Q8) |
| 13 | Scope creep across a long project | High — nothing ships | §10 procedure; one phase at a time; §11 out-of-scope list |
| 14 | "100+ designs" is untrue at launch | Medium — a false claim in the first line a visitor reads | **Live and unmitigated.** Kamronbek chose to hardcode the claim (§17 #39), so the only remaining guard is **Phase 11 item 2, now a hard launch gate**: either the catalogue has 100+ designs or the line changes before launch |
| 15 | Rate limiting wrong across gunicorn workers without Redis | Medium — brute-force window | Redis in Phase 1b, on the new VPS (§17 #31). `settings.py` already reads `REDIS_URL` and falls back to LocMemCache, so only the server side is outstanding |
| 16 | Stock decrement races on a popular drop | Medium — oversell | Decrement inside the existing payment transaction; `select_for_update` on the variant row |
| 17 | Telegram outage or bad token breaks checkout | Medium | `on_commit` + catch-everything, mirroring `core/sms.py`; a test asserts failure doesn't break the request |
| 18 | Guest cart merge loses items or duplicates them | Medium — direct revenue loss | Merge inside a transaction with both carts locked; three dedicated tests |
| 19 | `media/` not in the database backup | Medium — irreplaceable photography lost | Explicit `media/` backup in Phase 10 |
| 20 | Legal documents wrong under Uzbek law | Medium — regulatory exposure | Written carefully in Phase 8; independent review recommended in Phase 11 |
| 21 | Task chats drift from the plan or each other | Medium — inconsistent codebase | §0 cross-chat protocol; every task chat reads the plan and updates §15–§17 |
| 22 | Tags never get filled in, so Phase 13 has no signal | Medium — the recommender is worthless | Tags are a required field in the Phase 7 product form, not optional |
| 23 | The chosen typeface lacks U+02BB, so Uzbek renders as tofu | Medium — `Oʻzbekiston` breaks in the brand's own language | Check the cmap of every candidate face in Phase 2 before shortlisting. Poppins already failed this test |

---

## 13. Execution order and sequencing rationale

**Execution order:**

```
0 → 1a → 2 → 3 → 4 → 5 → 6 → 12 → 7 → 8 → 9 → 10 → 1b → 11 → 13
```

**Phase 1b (deployment) moved to just before launch (§17 #36).** It was originally early because a
domain move has external lead times — but there is no domain move any more: valleymade.uz is
abandoned and graphix.uz is a fresh deployment onto a VPS that hasn't been bought (§17 #35). Standing
up a server months before there is anything worth serving buys nothing and costs rent. It still runs
*before* Phase 11, because Phase 11's live payment tests and 72-hour watch need a live site.

Phase 12 (reviews) runs before Phase 7 so review moderation ships with the rest of the admin panel.
Phase 13 (recommendations) runs after launch, once there is like data worth reading.

**Why this order:**

- **Stabilise before building.** A broken `settings.py` and a dirty git tree make every later step
  harder to reason about.
- **Rebrand early, deploy late.** The brand work (1a) is early because every template written after
  it would otherwise be written twice. The server work (1b) is late because nothing else depends on
  it and an idle VPS is pure cost.
- **Design system before pages.** Building pages first and extracting a system afterwards produces a
  system that fits the first three pages and fights the next ten.
- **i18n before the page rebuild.** Otherwise every template gets written twice.
- **Data model before UI.** Templates get built once, against the final schema — which is why the
  review, tag, spec and pickup models all land in Phase 4 even though their features come later.
- **Features after the page rebuild.** Size guide, likes, search, map and delivery all attach to pages
  that must exist in final form first.
- **Reviews before the admin panel**, so moderation is built with the panel rather than bolted on.
- **Performance and accessibility as a dedicated phase** — but after the pages exist, because you
  cannot optimise what isn't built.
- **Recommendations last.** They need like data, and like data needs a live site.
- **Smoke tests from day one, the full suite before launch.** The four Phase 0 tests catch
  catastrophic breakage during the twelve phases in between.

---

## 14. Rough effort shape

| Phase | Weight | Notes |
|---|---|---|
| 0 Stabilise | ▏ Small | Mostly mechanical |
| 1 Rebrand | ▎ Small–Medium | External lead times |
| 2 Design system | ▊ **Large** | Three directions + full component library |
| 3 i18n foundation | ▌ Medium–Large | Infrastructure is quick; three languages of real copy is not |
| 4 Data model | ▋ Medium–Large | Grew substantially: tags, reviews, pickup points, cart changes |
| 5 Frontend rebuild | █ **Largest** | Eleven page groups × six breakpoints × three languages |
| 6 Features | █ **Largest** | Size guide, likes, share, search, map + pickup picker, delivery, Telegram, anonymous cart |
| 12 Reviews | ▌ Medium | Submission, moderation, display, photo handling, SEO |
| 7 Admin panel | ▊ Large | A second interface; product creation and moderation are both substantial |
| 8 Legal & content | ▌ Medium | Three documents × three languages |
| 9 Perf / SEO / a11y | ▌ Medium | Image pipeline is the bulk |
| 10 Testing | ▋ Medium–Large | ~90 tests now |
| 11 Launch | ▎ Small–Medium | Gated by photography and catalogue entry |
| 13 Recommendations | ▎ Small | One cached query — the thinking is done in this plan |

**Phases 2, 5 and 6 decide whether this project succeeds.** Everything else is supporting work.
Phase 6 has grown enough that splitting it is worth considering once it starts.

---

## 15. Progress tracker

| Phase | Status | Branch | Started | Finished | Notes |
|---|---|---|---|---|---|
| 0 Stabilise | ✅ Done | `phase-0-stabilise` | 2026-09-08 | 2026-09-08 | Items 7 and 9 moved to Phase 1b (new VPS) |
| 1a Rebrand | ✅ Done | `phase-1-rebrand` | 2026-09-09 | 2026-09-09 | Mark, icons, OG, all copy, canonical contacts |
| 1b Deployment | ⛔ Blocked | `phase-1b-deploy` | — | — | **Waiting on the VPS purchase.** Runs after Phase 10, before launch (§13) |
| 2 Design system | 🟨 In progress | `phase-2-design` | 2026-09-09 | — | **Three directions built + typeface screened. Waiting on Kamronbek to pick a direction (§19 Q18)** — items 2, 4–9 are blocked on it |
| 3 i18n foundation | ⬜ Not started | `phase-3-i18n` | — | — | |
| 4 Data model | ⬜ Not started | `phase-4-models` | — | — | Needs the pickup-point CSV |
| 5 Frontend rebuild | ⬜ Not started | `phase-5-frontend` | — | — | |
| 6 Features | ⬜ Not started | `phase-6-features` | — | — | Needs Yandex licence + Telegram token |
| 12 Reviews | ⬜ Not started | `phase-12-reviews` | — | — | Runs before Phase 7 |
| 7 Admin panel | ⬜ Not started | `phase-7-panel` | — | — | |
| 8 Legal & content | ⬜ Not started | `phase-8-content` | — | — | |
| 9 Perf / SEO / a11y | ⬜ Not started | `phase-9-quality` | — | — | |
| 10 Testing | ⬜ Not started | `phase-10-tests` | — | — | |
| 11 Launch | ⬜ Not started | `phase-11-launch` | — | — | |
| 13 Recommendations | ⬜ Not started | `phase-13-recommend` | — | — | After launch |

Legend: ⬜ Not started · 🟨 In progress · ✅ Done · ⛔ Blocked

---

## 16. Session log

| Date | Chat | Phase | Done | Next |
|---|---|---|---|---|
| 2026-09-08 | Planning | — | Full codebase audit; plan v1.0 | Answer open questions |
| 2026-09-08 | Planning | — | v1.1: delivery, Telegram, image-first size guide, logo, cross-chat protocol | Customer requirements |
| 2026-09-08 | Planning | — | v1.2: customer requests reviewed and folded in; Uzpost research; Phases 12–13 added | Project instructions, then Phase 0 |
| 2026-09-08 | Planning | — | v1.3: cross-chat rule corrected (a chat may span several phases); project instructions written to `docs/PROJECT_INSTRUCTIONS.md` | Phase 0 |
| 2026-09-08 | Task | 0 | v1.4: **Phase 0 complete.** `Kamron's` merged into `main`; `phase-0-stabilise` cut from `main`. Settings restored + `CSRF_TRUSTED_ORIGINS` added; 48 `.pyc` files and `.idea/` untracked and `.gitignore` rewritten; simplejwt, cors-headers and PyJWT removed and `requirements.txt` re-encoded UTF-8; footer categories rendered from a context processor; stale Click TODO deleted; four smoke tests added and passing. Redis and backup-restore moved to Phase 1 with the new VPS | Phase 1 — rebrand + new VPS |
| 2026-09-09 | Task | 1a | v1.5: **Phase 1a complete.** Mark redrawn geometrically (1.9 KB traced path → 225 B, true 60°, IoU 0.943 against the original); full icon set, manifest and OG card; every ValleyMade string replaced; canonical contacts fixed; hero de-"Arzon"-ed; sitewide OG/Twitter meta. Phase 1 split into 1a/1b, 1b moved to just before launch, and the valleymade.uz 301 requirement deleted. Found: Poppins lacks U+02BB — a Phase 2 elimination criterion (risk #23) | Phase 2 — design system |
| 2026-09-09 | Task | 2 | **Phase 2 started.** Typeface screening run against 31 families by reading cmaps — 22 fail on U+02BB; shortlist and evidence in `docs/design/typeface-screening.md`. No product photography exists, so a garment-mockup generator was built (`docs/design/mockup/`) and eight products composed. Three directions delivered as one self-contained file, `docs/design/directions.html` | **Kamronbek picks a direction**, then tokens, base.css, components.css, style guide |

---

## 17. Decision log

| # | Date | Decision | Reasoning |
|---|---|---|---|
| 1 | 2026-09-08 | Django templates + hand-written CSS/JS, no build step | Deploys unchanged; nothing new on the VPS |
| 2 | 2026-09-08 | ~~Yandex free tier~~ → **paid Yandex commercial licence** | Free tier is not licensed for commercial sites. Yandex kept for its Uzbek data quality; cost accepted |
| 3 | 2026-09-08 | ~~Separate like and favourite~~ → **one merged "like"** | Two similar hearts confuse shoppers; one action matches how the customer and every fashion store think about it |
| 4 | 2026-09-08 | Evolve in place, one branch per phase | Site stays live; no big-bang cutover |
| 5 | 2026-09-08 | Zero new Python dependencies | Everything needed is installed or standard library |
| 6 | 2026-09-08 | Uzbek unprefixed, `/ru/` and `/en/` prefixed | Best SEO for the primary audience |
| 7 | 2026-09-08 | Internal package `vm` keeps its name until Phase 11 | Renaming touches wsgi, systemd, nginx, venv |
| 8 | 2026-09-08 | Translation via explicit `_ru` / `_en` fields | No new dependency; existing rows keep working |
| 9 | 2026-09-08 | Base font size 14 px → 16 px | The biggest reason the current site reads as cramped |
| 10 | 2026-09-08 | Map is assistive; the address stays required and authoritative | Checkout must work with no JS, no permission, no map |
| 11 | 2026-09-08 | Keep the six-point asterisk; redraw it geometrically | Already distinctive and vector; the traced path is the only problem |
| 12 | 2026-09-08 | ~~15k flat, free at 2 items~~ → **15k to an Uzpost branch, 30k to the door, no free threshold** | Each tier reflects real cost; simplest possible rule to explain |
| 13 | 2026-09-08 | Delivery configured as `DeliveryOption` rows, not hardcoded | Prices will change; that must not require a deploy |
| 14 | 2026-09-08 | `delivery_price` and `pickup_snapshot` frozen on the order | Same principle as `CartItem.price_stat` — a later change must not rewrite history |
| 15 | 2026-09-08 | Size guide image-first, with optional structured rows | The owner supplies charts as photos; rows are a bonus for a11y and SEO |
| 16 | 2026-09-08 | Telegram notifications committed, not optional | Highest operational value per line of code in the project |
| 17 | 2026-09-08 | Telegram sends fire on `transaction.on_commit`, never raise | A notification must never fail a checkout or fire for a rolled-back order |
| 18 | 2026-09-08 | Legal documents written in-project; review recommended, not blocking | Owner's call; still written to a real standard |
| 19 | 2026-09-08 | Product creation with photo upload is a first-class admin screen | The owner enters the whole catalogue himself |
| 20 | 2026-09-08 | Planning chat and task chats separated; the plan is shared memory | Keeps many chats consistent over a long project |
| 21 | 2026-09-08 | **We own the pickup-point dataset** rather than querying a third party live | No public Uzpost API exists; a live lookup would add a checkout failure mode for no benefit |
| 22 | 2026-09-08 | **Pickup picker is list-first, map-second** | A pure-map picker with thirty overlapping pins is unusable at 390 px and fails when the map does |
| 23 | 2026-09-08 | **Colour removed from the storefront UI, kept in the data model** | Every design is one colourway, so the picker is noise — but deleting the model is a destructive migration for no gain |
| 24 | 2026-09-08 | **Anonymous cart; login still required at checkout** | Captures most of the conversion benefit without reworking the most sensitive code in the project |
| 25 | 2026-09-08 | **Reviews are verified-purchase only and moderated before publication** | It is what makes reviews trustworthy, and user-uploaded photos on a public page need a gate |
| 26 | 2026-09-08 | **Recommendations are tag-overlap, built after launch; tags collected from day one** | A recommender needs data; tags are the signal, and `Category` alone is worthless when everything is a t-shirt |
| 27 | 2026-09-08 | **All map code behind a `GX.map` wrapper** | The Yandex licence cost is unknown; switching provider must be a one-file change |
| 28 | 2026-09-08 | Phase numbers are stable identifiers; execution order is separate (§13) | The plan will keep growing; renumbering would break every earlier reference |
| 29 | 2026-09-08 | Home page must show a product row above the fold at 390 × 844 | A full-viewport hero on a shop is a known conversion killer; the customer's instinct is right |
| 30 | 2026-09-08 | A chat may span several phases; consistency between chats is the actual requirement | Chats open and close for practical reasons. What must hold is that the output reads as one person's work — enforced by the plan, not by chat boundaries |
| 31 | 2026-09-08 | **Redis and the verified backup restore move from Phase 0 to Phase 1**, with the new VPS | Kamronbek is replacing the VPS, and the old database holds nothing worth migrating. Setting up Redis and a restore drill on a server about to be discarded is wasted work — but both are still hard requirements before the new server takes a real order, so they became Phase 1 Definition-of-Done criteria rather than being dropped |
| 32 | 2026-09-08 | **`main` is the integration branch.** `Kamron's` was merged into `main` before Phase 0; every phase branch is cut from `main` and merges back into it | `Kamron's` and `origin/main` had diverged (8 commits vs 4 PR merges). One integration branch removes the ambiguity about which branch production follows, and keeps the one-branch-per-phase convention meaningful |
| 33 | 2026-09-08 | **Footer categories render from a `product.context_processors.nav_categories` context processor**, not hardcoded values | `Category` has no slug until Phase 4 and `shop()` filters on `category_id`, so any hardcoded link is either wrong or a guess at primary keys. Reading the real rows is correct today and stays correct as categories change. Costs one query per page; the footer is rebuilt in Phase 5 anyway |
| 34 | 2026-09-08 | **The previous production database is treated as empty** | Kamronbek confirmed it holds no items. Phase 4's slug and `order_no` backfill migrations must still be written and correct, but there is no legacy data to rescue, and no catalogue to migrate |
| 35 | 2026-09-09 | **valleymade.uz is abandoned outright. No 301s, no old server, no Change of Address.** GRAPHIX launches as a brand-new site on graphix.uz | Kamronbek: *"we won't use previous domain never."* The old site has no catalogue, no orders and no meaningful search presence, so there is no link equity to preserve — the redirect infrastructure would have been cost and complexity protecting nothing. Phase 1 item 7 is deleted and risk #1 loses its 301 mitigation |
| 36 | 2026-09-09 | **Phase 1 splits into 1a (brand and code) and 1b (deployment), and 1b moves to just before Phase 11** | Kamronbek's push-back was correct: the VPS isn't bought, the work is local, and nothing between here and Phase 10 needs a server. The original "rebrand early" rationale was about external lead times for a *domain move* — and there is no domain move any more (#35). An idle VPS is rent paid for nothing. 1b still runs before Phase 11, whose live payment tests need a live site |
| 37 | 2026-09-09 | **The mark is redrawn at a true 60° hexagonal asterisk, symmetrising the original** | Measuring the source PNG showed the two diagonals at different slopes — 0.594 and 0.543 dx/dy — which is hand-trace error, not intent; their mean is within 1.5 % of 60°. The redraw uses exact 60°, equal bar weights and a common centre. IoU against the original is 0.943, and the whole residual is a hair-thin sliver along the diagonal edges. 1.9 KB and hundreds of nodes → **225 bytes and three straight-edged subpaths** |
| 38 | 2026-09-09 | **The wordmark lockups move from Phase 1 to Phase 2** | `logo-full.svg` and `logo-stacked.svg` are the mark *set with the wordmark*, and Phase 2 chooses the display typeface. Drawing them in Phase 1 means drawing them in a face we are about to replace, then drawing them again. Nothing in Phase 1 needs them — every icon and the favicon use the mark alone |
| 39 | 2026-09-09 | **"100+ dizayn" is hardcoded in the tagline, not rendered from the live product count** | Kamronbek's call, made with the trade-off stated: the catalogue is currently empty, so the claim is untrue today. Recorded because it is the first sentence a visitor reads. Risk #14 stays open and **Phase 11 item 2 becomes a hard launch gate** — 100+ real designs, or the line changes before launch |
| 40 | 2026-09-09 | **Every raster icon is one identity: a white mark on a solid black tile** | Favicon, apple-touch, both PWA icons and the OG card all read as the same object at every size, and white-on-black is legible on light and dark browser chrome alike. It also matches the existing `theme-color: #000000`. Phase 2 may re-skin them once the palette is chosen; black and white is the lowest-regret choice to ship before that decision exists |
| 41 | 2026-09-09 | **`site.webmanifest` is a rendered template, not a static file** | It has to name the icon files, and Phase 9 introduces `ManifestStaticFilesStorage`, which hashes their filenames. Serving it through `TemplateView` + `{% static %}` — the same pattern `robots.txt` already uses — means the paths keep resolving instead of silently 404ing after that change |
| 42 | 2026-09-09 | **Phase 2 proceeds on drawn garment mockups instead of waiting for photography** | Kamronbek's call, with the trade-off stated. `media/products/` contains no photograph of a t-shirt, and the alternative was parking Phase 2 for an unknown time. A generator (`docs/design/mockup/`) draws a garment with real oversize-tee proportions, fabric shading and a consistent 4:5 crop on one backdrop. **What this buys and what it does not:** layout, crop, hierarchy and typography are judgeable; *"does this shop look professional"* is not, because that question is answered by the photography. §8's warning stands and Phase 11 stays gated on real shots |
| 43 | 2026-09-09 | **The typeface shortlist is fixed to the nine families that contain U+02BB and Cyrillic; `--f-mono` is settled as IBM Plex Mono** | Measured, not assumed: 31 families were downloaded and their cmaps read. 22 fail, including Manrope, Figtree, Outfit, Plus Jakarta Sans, Sora, Space Grotesk, Bricolage, Archivo and Rubik — and Golos Text, which is a Cyrillic-first family built for Russian. IBM Plex Mono is the **only** monospace that passes, so there is no choice to make there. IBM Plex Sans and Mulish pass on coverage but set `O ʻzbekiston` with a visible gap, so they are out on spacing |

---

## 18. Backlog

Ideas raised but not yet placed in a phase. Reviewed in the planning chat, then scheduled or moved to
§11. A task chat that hits a new idea adds it here and keeps going.

| # | Idea | Raised | Notes |
|---|---|---|---|
| 1 | Uzpost tracking-number integration — attach a tracking number to an order and show it to the customer | 2026-09-08 | Currently §11 out of scope; revisit once order volume justifies the integration work |
| 2 | Branded `info@graphix.uz` email forwarding to the Gmail address | 2026-09-08 | Free with the domain; reads considerably more credible on a contact page. Phase 1 if wanted |
| 3 | Debounced search suggestions in the header field | 2026-09-08 | Phase 6c ships the results page; suggestions are a later nicety |
| 4 | Drop `django-environ` from `requirements.txt` | 2026-09-08 | Pinned but never imported — the project reads `.env` through `python-dotenv`. Left in during Phase 0 because it was outside the two packages the plan named. One-line removal whenever Kamronbek confirms |
| 5 | Rename the git branch `Kamron's` | 2026-09-08 | The apostrophe needs quoting in every shell command and breaks some tooling. `main` is now the integration branch (§17 #32), so the branch can simply be deleted once nothing depends on it |
| 6 | Give the commit history real messages going forward | 2026-09-08 | Most existing commits are literally `.`. The `<phase>: <imperative summary>` convention (§4) starts with Phase 0; history before that stays as-is |
| 7 | **Instagram and TikTok links — need the real handles** | 2026-09-09 | Both were `href="#"` in the footer and were removed in Phase 1a rather than shipped dead. Instagram matters: §9 Phase 9 calls it out as a primary sharing surface alongside Telegram. Give me the handles and they go back in — Phase 5 at the latest, when the footer is rebuilt |
| 8 | Redraw the OG card once the display typeface exists | 2026-09-09 | The Phase 1a card is set in Poppins Bold, which is a placeholder — and which lacks U+02BB, so the tagline had to be set in a second face. Phase 2 picks the real face; regenerate the card then |
| 9 | Rename the GitHub repository `ValleyMade` → `graphix` | 2026-09-09 | Cosmetic, and it changes the clone URL and every local remote. Pair it with the `vm/` → `graphix` package rename already parked in Phase 11 |

---

## 19. Open questions

| # | Question | Needed by | Status |
|---|---|---|---|
| 1 | **Yandex Maps commercial pricing for Uzbekistan** — needs a sales conversation. What is the monthly cost at our volume, and is it acceptable? | Phase 6d | ⏳ Open — blocks a locked decision |
| 2 | Telegram bot token and chat ID | Phase 6f | ⏳ Owner will supply |
| 3 | Can Uzpost supply an official branch list (index codes, addresses, coordinates, hours)? A business partner asking is a normal request and would beat any scraped source. | Phase 4 | ⏳ Open |
| 4 | Pickup-point launch scope — Tashkent only, Tashkent + regional capitals, or nationwide? | Phase 4 | ⏳ Open |
| 5 | **Is 30 000 so'm door delivery actually above cost in far regions?** Check Uzpost's published courier tariffs. | Phase 6e | ⏳ Open |
| 6 | Tag taxonomy — who defines the style/theme tags, and what is the starting list? | Phase 4 | ⏳ Open |
| 7 | Fit range — regular and oversize only, or more? Drives the size charts and the `fit` choices. | Phase 4 | ⏳ Open |
| 8 | **Were the designs in the customer's mockup placeholders?** If any reproduce other brands' marks and are intended for sale, that is worth reviewing before listing. | Phase 11 | ⏳ Open |
| 9 | Size-chart images — do they exist, or do they need producing? | Phase 4 | ⏳ Open |
| 10 | Expected delivery timeframes to quote — branch pickup vs door, Tashkent vs regions | Phase 8 | ⏳ Open |
| 11 | Returns window and conditions; uncollected-parcel policy | Phase 8 | ⏳ Open |
| 12 | Legal entity name and details for the terms and privacy policy | Phase 8 | ⏳ Open |
| 13 | Cash-on-delivery limits — any order-value cap, or regions excluded? | Phase 6e | ⏳ Open |
| 14 | Earlier notes said "BTS pochta"; the current answer says Uzpost for everything. One carrier or two? | Phase 8 | ⏳ Open |
| 15 | **When is the VPS bought?** Specs are settled (Ubuntu 24.04, 2 vCPU / 4 GB / 40 GB SSD, upgradeable to 26.04), and Phase 1b is the only thing waiting on it. Ask again when Phase 10 finishes. | Phase 1b | ⏳ Open — not urgent |
| 16 | Instagram and TikTok handles for the footer (§18 #7) | Phase 5 | ⏳ Open |
| 17 | Confirm the Eskiz sender name is approved as exactly `GRAPHIX`, and that the two SMS templates were re-moderated after the rebrand — Eskiz moderates message *text*, and both bodies changed in Phase 1a | Phase 1b | ⏳ Open — worth checking before it blocks a live signup |
| 18 | **Which direction — A · Galereya, B · Bosma, or C · Tungi?** Open `docs/design/directions.html`, ideally on a phone. Everything else in Phase 2 depends on this: tokens, `base.css`, `components.css`, the style guide, the wordmark lockups, and the palette the icons may be re-skinned to. A mix is allowed — say which parts of which. | Phase 2 | ⏳ **Open — blocking Phase 2 items 2 and 4–9** |
| 19 | Product photography — when can real shots exist? Not blocking now (§17 #42), but it gates Phase 11 and it is what decides whether the chosen direction actually looks professional. | Phase 11 | ⏳ Open |

**Resolved:**

| Question | Answer |
|---|---|
| Is `graphix.uz` available? | ✅ Registered |
| Is there a logo? | ✅ The six-point asterisk, already vector in `favicon.svg` |
| Eskiz sender under the GRAPHIX name? | ✅ Approved |
| Canonical contact details? | ✅ abdurahmonboboyev.magic@gmail.com · +998 50 788 84 36 · [@greatestamal](https://t.me/greatestamal) |
| Who writes the Russian and English copy? | ✅ Written in-project |
| Who writes the legal documents? | ✅ Written in-project |
| Who enters products? | ✅ The owner, via the custom admin panel |
| Delivery carrier and pricing? | ✅ Uzpost nationwide · 15 000 to a branch · 30 000 to the door · no free threshold |
| Telegram bot? | ✅ Yes — order, payment, message and review notifications |
| Size guide format? | ✅ Image-first, optional measurement rows |
| Map provider? | ✅ Yandex, paid commercial licence, behind a swappable wrapper |
| Like vs favourite? | ✅ Merged into one heart |
| Guest checkout? | ✅ Anonymous cart; login required at checkout |
| Is there data in the current production database to preserve? | ✅ No — it holds no items. A new VPS is being provisioned; nothing needs migrating (§17 #34) |
| Which branch is the integration branch? | ✅ `main`. `Kamron's` merged into it before Phase 0; phase branches cut from `main` (§17 #32) |
| What happens to valleymade.uz? | ✅ Abandoned outright — no 301s, no old server, no Change of Address (§17 #35) |
| New VPS specs? | ✅ Ubuntu 24.04 (upgradeable to 26.04), 2 vCPU, 4 GB RAM, 40 GB SSD — anything can be installed on it |
| Who runs the server commands? | ✅ Kamronbek has shell access and I can drive it from his machine when the time comes |
| Wordmark lockups in Phase 1? | ✅ No — moved to Phase 2, after the display typeface is chosen (§17 #38) |
| "100+ designs" before the catalogue exists? | ✅ Hardcoded now; Phase 11 item 2 is the launch gate (§17 #39) |

---

*End of plan. Amend it rather than working around it.*
