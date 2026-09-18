# GRAPHIX — Rebuild Plan

**Project:** ValleyMade → **GRAPHIX** — online graphic t-shirt store for Uzbekistan
**Repo:** `D:\phyton\ValleyMade\` — GitHub `A-Kamronbek/Graphix`. **Flattened 2026-09-18 (§17 #242):** the apps, `manage.py`, `templates/`, `static/` and `locale/` sit at the repository root; the settings package is `config/`. There is no `vm/` any more — paths in entries written before that date name it, and are left as they were written
**Production:** **graphix.uz** (domain secured, not yet deployed). valleymade.uz is abandoned — see §17 #35.
**Owner / developer:** Kamronbek
**Plan version:** 2.22 · created 2026-09-08 · last amended 2026-09-18
**Status:** Phases 0, 1a, 2, 3, 4, 5, 6, 7, 8, **9** and 12 complete · **Phase 1b (deployment) moved ahead of Phase 10 on 2026-09-18 (§17 #238)** and is in progress, so Phase 10's operations items and its hardening are checked against the real server rather than deferred past it · Phase 10 follows, on `phase-10-tests`
**This is the merged plan (§17 #89).** Two versions of this file existed on 2026-09-12: a planning line at v1.5 and an implementation line at v1.19. v2.0 is one document again, and the delivery redesign and Google Maps from the planning line are carried into it.

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

### The plan forked once. Here is how not to do it again

On 2026-09-12 two chats amended this file from different starting points: a planning chat took v1.3
and produced its own v1.4 and v1.5, while the task chats had already carried the same file to v1.18.
Both were legitimate work and both wrote `docs/PLAN.md`, so whichever saved last erased the other —
and because both numbered their new decisions from #23, the same number meant two different things.

**The rules that prevent it:**

1. **Read the file immediately before amending it, and bump the version you actually read.** A chat
   that has been open for hours is holding a stale copy.
2. **A version number is never reused.** If the file says 1.18, the next amendment is 1.19 — not 1.4,
   whatever the chat last saw.
3. **Decision numbers are append-only across the whole project**, like phase numbers (§0 below). Never
   restart them, and never renumber an existing one.
4. **Check the version string before and after writing** (§17 #82). A write that did not land, or that
   landed on the wrong base, is silent otherwise.

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

An honest baseline, taken on 2026-09-08 before the rebuild began, from a full read of every Python
file, template, `main.css` and `main.js`, plus an inspection of the live site. What has changed since
is in §15 and §17.

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
8. ✅ **`django-environ` was pinned but never imported** — the project reads its `.env` through
   `python-dotenv`. → *Removed 2026-09-13 (§18 #4).*

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
| Map provider | **Google Maps Platform** | Owner's decision, 2026-09-12 (§17 #83). It replaces the paid Yandex licence: Google bills per use with a monthly free allowance rather than requiring a commercial-site contract, and the map is now needed on one form only, so the volume is small. Yandex's edge on Uzbek street naming is real but does not pay for a licence negotiation (§19 Q1). |
| Map abstraction | **All map code sits behind one thin internal wrapper** | Written before the provider was settled, and it is exactly why changing it cost nothing: the provider moved from Yandex to Google with no code to rewrite, because none had been written outside the plan. Keep the wrapper — 2GIS and Leaflet stay one file away. |
| Saved items | **One "like" — public count and private saved list in a single action** | One heart, one model. Matches how every fashion store and social app works, and how the customer describes it. Feeds the popularity sort and the recommender. |
| Guest browsing | **Anonymous cart; login required at checkout** | Guests browse and fill a cart freely; the login wall moves from "add to cart" to "checkout". Captures most of the conversion benefit without reworking the most sensitive code in the project. |
| Rebuild strategy | **Evolve in place, one branch per phase** | Same repo, one branch per phase. *The old database held nothing and valleymade.uz is abandoned, so graphix.uz starts from a fresh database on the new VPS and nothing is deployed before Phase 1b (§17 #34–#36).* |
| New Python dependencies | **None.** | Everything needed is already installed or is in the standard library. |
| Language strategy | **Uzbek default; every language prefixed — `/uz/`, `/ru/`, `/en/`** *(amended 2026-09-14, §17 #121 — Uzbek was unprefixed until then)* | One URL shape for all three. An unprefixed default is a special case Django keeps working around — it is what left the language switcher one-way (§17 #115). Old unprefixed URLs redirect into the prefixed tree. |
| Internal package name | **`vm/` stays** for now | Renaming touches wsgi, systemd, nginx and the venv. Deferred to after launch, paired with the repository rename (Phase 11, §18 #9). |
| Brand mark | **The existing six-point asterisk carries over** | Already vector, already distinctive. It needs a clean geometric redraw, not a redesign. |
| Delivery | **Two methods, no free threshold: 15 000 UZS to an Uzpost branch · 40 000 UZS to the home. All shipping via Uzpost, Tashkent and regions alike.** | Simple, predictable, and each tier reflects real cost. The home tier rose from 30 000 on the owner's pricing call (§17 #85); the rows and the copy have said 40 000 since Phase 6e (§18 #18). |
| Branch delivery | **No branch table. The customer picks a region and a district, then types the 6-digit postal index of their branch.** | Owner's decision, 2026-09-12 (§17 #84), and it removes the hardest dependency in the project: there is no public Uzpost branch list, so a `PickupPoint` table meant owning and verifying a dataset we could not obtain. Every Uzbek knows their own postal index; two small reference tables (14 regions, ~210 districts and cities) are verifiable by hand in an afternoon. **Phase 4 shipped the `PickupPoint` table before this decision existed; Phase 6d retired it.** |
| Colour | **Removed from the product-page UI; kept in the data model** | Every design ships in one colourway, so the picker is noise. Deleting the model would be a destructive migration with no benefit. |
| Reviews | **Verified purchase only, with moderation** | Only a customer with a delivered order containing that product can review it. Photos are queued for approval before they appear publicly. |
| Recommendations | **Tag-overlap, not machine learning. Data collected from day one, algorithm built after launch.** | A recommender needs like data and product tags to be worth anything. Tags land in Phase 4; the algorithm is Phase 13. |
| Telegram notifications | **Committed deliverable, not optional** | A push to the owner's phone within seconds of an order is worth more than any dashboard. *Built in 6f; switched on from `.env`, straight to Telegram or through the shop's bot service (§17 #93, #206).* |
| Legal documents | **Written in-project** | Drafted to a real standard against Uzbek law. Independent review recommended, not blocking. |

### Research finding: Uzpost branch data — *why the branch table was dropped*

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

**Original conclusion (2026-09-08):** seed a `PickupPoint` table once from OSM plus an official
list requested from Uzpost, verify by hand, maintain it in the admin panel.

**Revised conclusion (2026-09-12, §17 #84):** drop the table. The research above is what forced the
change rather than contradicting it — *there is no list to seed from*. Phase 4 built the loader, its
validation and its tests, and shipped `data/pickup_points.csv` with a header and no rows, because
inventing branches would misroute real parcels (§17 #58). That file would have stayed empty
indefinitely, and it was the blocker on the whole of Phase 6.

The postal index removes the dependency: the customer supplies the one piece of data we cannot obtain,
and they already know it. What we own instead is a two-level reference table — 14 regions and ~210
districts and cities — built from the official **SOATO / MHOBT** classifier, which *is* published.
The index's first two digits encode the region, so a typo that would send a parcel to another province
is caught at checkout against a prefix we know (§17 #86).

---

## 4. Constraints and conventions

### Dependencies

The rebuild adds **zero** new Python packages. Verified: Redis caching is built into Django 6;
Pillow handles thumbnails; `django.utils.text.slugify` handles slugs; Django's own `gettext` handles
i18n; `requests` (already installed) handles Telegram; the region tables are built from the SOATO
classifier with the standard library (§17 #98); Django's built-in runner handles tests; Google Maps is
browser-side JavaScript.

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
- **External calls never break a request.** Every outbound integration (Eskiz, Telegram, Google,
  Click) follows the pattern in `core/sms.py`: module logger, catch everything, log, return falsy.
  An outage degrades the feature — it never 500s the page.
- **Commits**: `<phase>: <imperative summary>` — e.g. `P5: rebuild item page on the new design system`.

### Branches

`main` is the integration branch (§17 #32). One branch per phase, cut from `main`:
`phase-0-stabilise`, `phase-1-rebrand`, … Merged back into `main` when the phase's Definition of
Done passes. Once the site is live, a merge into `main` is what gets deployed; nothing is deployed
before Phase 1b (§17 #36).

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

Every path in the tree sits under a language prefix — `/uz/`, `/ru/` or `/en/` (§17 #121).

```
/                          Home
/shop/                     Catalogue — search, filter, sort
/mahsulot/<slug>/          Product detail  (301 from /item/<pk>/)
/qidiruv/                  Global search results          ← new
/saqlanganlar/             Liked / saved items            ← new
/cart/                     Cart  (anonymous allowed)
/checkout/                 Checkout — login required; region and district, then a branch index or a street
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
/olcham-jadvali/           General sizing guide           ← new
/boshqaruv/                Custom admin panel             ← new (staff only)
```

**Must stay outside `i18n_patterns()`** — called by machines, and a language prefix would break them:

- `/payment/click/update/` — the Click webhook. **Breaking this breaks payments.**
- `/admin/` (the Django admin, kept as the fallback), `/sitemap.xml`, `/robots.txt`,
  `/site.webmanifest`, `/favicon.ico`, `/i18n/` (the language switch), `/media/`, `/static/`

---

## 7. Target data model

All changes are additive except where noted. No existing column is dropped or renamed.

### `product`

```python
class TagKind(Model):                   # a table since #164, not choices
    slug          SlugField(30, unique)
    name_uz/ru/en CharField(60)
    Meta: ordering = ['id']             # oldest first; the sort column went in #171

class PrintMethod(Model):               # a table since #164, same shape, same reason
    slug          SlugField(30, unique)
    name_uz/ru/en CharField(60)
    Meta: ordering = ['id']

class Tag(Model):                       # NEW — powers filtering and recommendations
    slug          SlugField(60, unique)
    name_uz/ru/en CharField(60)
    kind          FK(TagKind, PROTECT, null, blank, related_name='tags')
    Meta: ordering = ['kind', 'slug']
    # e.g. style: oversize, boxy · theme: anime, streetwear, music, sport, minimal, vintage

class SizeChart(Model):                 # NEW — a name and a picture, and that is all (#172)
    name          CharField(120)
    image         ImageField('size-charts/', null, blank)   # PRIMARY: a photo/graphic chart
    note_uz/ru/en TextField(blank)
    # There was a `fit` here and it is gone with the cut it keyed on (#172).
    # A chart reaches a product because somebody attached it, or because it is
    # the category's, and no other way.

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
             + print_method    FK(PrintMethod, PROTECT, null, blank)   # a table since #164
             # `fit` was here — two cuts as choices — and is gone (#172). A cut is
             # something the owner says with a tag, at any value he likes.

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
    requires_branch  BooleanField(False)          # region + district + index, not an address
                                                  # shipped as `requires_pickup_point`; renamed
                                                  # in Phase 6d (migration 0014)
    is_active        BooleanField(True)
    sort_order       PositiveSmallIntegerField(0)

# Two small reference tables, from the official SOATO / MHOBT classifier.
# They replace PickupPoint (§17 #84). Shipped in Phase 6d, not Phase 4.
class Region(Model):                    # NEW — 12 viloyat + Qoraqalpogʻiston + Toshkent shahri
    code             CharField(4, unique)         # SOATO code
    name_uz/ru/en    CharField(80)
    postal_prefix    CharField(3, db_index)       # '100' Toshkent shahri, '14' Samarqand,
                                                  # '15' Fargʻona … 2 or 3 digits, so the check
                                                  # is startswith(), never a fixed slice
    is_active        BooleanField(True, db_index)
    sort_order       PositiveSmallIntegerField(0)
    Meta: ordering = ['sort_order', 'name_uz']

class District(Model):                  # NEW — tumanlar AND regionally-subordinate shaharlar
    region           FK(Region, PROTECT, related_name='districts')
    code             CharField(8, unique)         # SOATO code
    name_uz/ru/en    CharField(80)
    kind             CharField(10, choices=['district', 'city', 'other'])   # tuman | shahar | Boshqa (§17 #97)
    is_active        BooleanField(True, db_index)
    Meta: ordering = ['region', 'name_uz'], unique_together = ('region', 'name_uz')

Order        + order_no        CharField(20, unique, db_index)   # "GX-260908-0042"
             + latitude, longitude   DecimalField(9,6, null, blank)   # home delivery, map only
             + address_source  CharField(10, blank, choices=['map','manual'])  # home delivery
             + delivery_option FK(DeliveryOption, null, blank, PROTECT)
             + delivery_price  DecimalField(15,0, default=0)     # SNAPSHOT at checkout
             + region          FK(Region, null, blank, PROTECT)      # both methods (§17 #106)
             + district        FK(District, null, blank, PROTECT)    # both methods (§17 #106)
             + postal_index    CharField(6, blank, db_index)         # branch method only
             + location_note   CharField(160, blank)   # the Boshqa escape's own words (§17 #97)
             + location_snapshot TextField(blank)   # frozen text of where the parcel was sent
             + recipient_name  CharField(120, blank)   # who collects it (§17 #190)
             ~ user            FK(User, PROTECT)   # was CASCADE: an order outlives its account (§17 #219)

class PaymentOption(Model):             # NEW in Phase 6 (§17 #99) — Click on, cash off
    code             CharField(20, unique)        # matches Order.payment_method
    name_uz/ru/en, note_uz/ru/en
    is_active        BooleanField(False, db_index)
    sort_order       PositiveSmallIntegerField(0)
```

**Seeded delivery options:**

| code | Uzbek name | Price | What the customer gives | Note shown |
|---|---|---|---|---|
| `uzpost_office` | Pochta boʻlimiga | 15 000 | region · district · 6-digit index | Collect from your Uzpost branch |
| `uzpost_door` | Eshikkacha yetkazib berish | **40 000** | address — dropped pin or typed | Uzpost courier to your address |

The code is `uzpost_door`, not `uzpost_home`: that is what Phase 4 seeded and what any existing order's
`PROTECT` foreign key points at. Renaming it would buy nothing. Phase 6e raised the seeded price
from 30 000 to 40 000, and the copy on the product and delivery pages with it (§18 #18).

Both tiers ship via Uzpost, in Tashkent and every region alike. There is currently **no free-delivery
threshold** — `free_from_items` stays 0. The field exists so a promotion can be switched on later
without a deploy.

**Two snapshots, for the same reason `CartItem.price_stat` exists:** `delivery_price` freezes the fee
at checkout, and `location_snapshot` freezes as text whatever the customer chose — region, district and
index, or the address. A district renamed or deactivated a year later cannot rewrite where a parcel
was sent.

**Validation, and it is the point of this design** (§17 #86). Both methods **must** carry a region and a
district (§17 #106); a branch order adds the index, and a home order a street address and no index. The
index must be exactly six digits, and
its **first two digits must match the chosen region's `postal_prefix`** — the one check that catches the
typo that would otherwise send a parcel to another province. **Both drawers carry a `Boshqa` (Other) escape with a free-text field**, for an address the
classifier does not cover — a new district, a spelling the customer knows and we do not. When the
region is `Boshqa` the prefix check is skipped; **the six-digit format check still applies**, because
a four-digit index is wrong no matter where it is. Enforced in the checkout view **and** in
`Order.clean()`, so neither path can be skipped.

Uzbek indexes encode the province in their leading digits — `100` Toshkent shahri, `14` Samarqand,
`15` Fargʻona (UPU standard, cross-checked against published directories). A customer who picks
Toshkent shahri and types `140216` is told at the form, not three weeks later when the parcel comes
back. That is what turns typed input from sloppy into safe, and it costs nothing.

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
static/js/    main.js · gallery.js · variant.js · viewer.js · auth.js · checkout.js · map.js
              admin_map.js · forms.js · panel.js
```

`map.js` talks only to a thin internal wrapper (`GX.map`) exposing `init`, `show` (the admin's
read-only map, §17 #108), `setPin`, `getPin` and `reverseGeocode` — the marker calls went with the
branch table (§17 #84). No page ever calls a Google global directly — that is what makes a provider
swap a one-file change.

### Token set (values decided in Phase 2, shape decided now)

*The shape as planned. Where the values differ, `tokens.css` is the authority: radius is 3 · 6 · 14,
`--container-wide` was deleted (§17 #81), there is a `--z-sticky` layer, and breakpoints are set per
component — 640 · 720 · 860 · 1024 in use.*

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

Before Phase 1a, `static/img/favicon.svg` was a **traced** path with a 3125 pt viewBox and hundreds of
nodes (1.9 KB). Phase 1a **redrew it geometrically** — three rotated bars on a `0 0 24 24` viewBox,
225 bytes, exact at every size, recolourable via `currentColor`. Same mark, correctly built.

Deliverables: `logo-mark.svg`, `logo-full.svg` (mark + GRAPHIX wordmark), `logo-stacked.svg`, each one
`currentColor` file that serves light and dark grounds alike. Source PNG archived at
`docs/brand/logo-mark-source.png`; the share card's source is `docs/brand/og-card.html` (§17 #223).

### Component inventory

Buttons (primary / secondary / ghost / danger; three sizes; loading and disabled) · Text input,
textarea, select, checkbox, radio, quantity stepper, OTP cells · **Search field (header)** · Product
card (image, name, price, heart with count) · Product gallery with thumbnails, swipe and zoom · Size
selector with out-of-stock state · **Spec strip** (GSM / material · print method) · **Star
rating** (display + input) · **Review card** (rating, text, photos, verified badge) · Heart button
with count · **Share button** · Badge / pill (order status, "Yangi", "Ommabop", "Tugadi") · Modal /
sheet (mobile sheet, desktop dialog) · Toast · Breadcrumb · Pagination · Empty state · Skeleton
loader · Responsive table (stacks on mobile) · Filter panel (sidebar desktop, bottom sheet mobile) ·
**Region and district drawers** (scoped list, search appearing only where the list is long) + postal-index field · Tabs · Accordion ·
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
a running server is **1b**. Kamronbek has bought the new VPS (OVHcloud, Warsaw — Ubuntu 24.04,
2 vCore / 4 GB / 40 GB SSD) and will not deploy until the site is worth deploying, so 1b is deliberately
parked. The rest of the
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

#### Phase 1b — deployment *(unblocked 2026-09-12: the server is bought)*

Ubuntu 24.04, 2 vCore, 4 GB RAM, 40 GB SSD — the specs §19 Q15 asked for. **It runs before Phase
10 as of 2026-09-18 (§17 #238):** Phase 10's operations items and a good part of its hardening are
server work, so testing first and deploying afterwards left half of Phase 10's Definition of Done
unreachable. Phase 11 still follows both.

**The box already serves something.** GRAPHIX is installed *beside* whatever is running, never over
it (§17 #241), and a `pg_dump` of what is there is taken before PostgreSQL is touched at all.
**§19 Q36 gates every step below**: whether the target machine is the VPS bought on 2026-09-12 or an
older one.

8. **Provision the VPS** (OVHcloud, Warsaw — Ubuntu 24.04, 2 vCore / 4 GB / 40 GB SSD — bought) and
   deploy to it as a fresh install — there is nothing to migrate (§17 #34): nginx `server_name`,
   certbot for graphix.uz + www, gunicorn + systemd, PostgreSQL, `ALLOWED_HOSTS`,
   `CSRF_TRUSTED_ORIGINS`, the `.env`; then `migrate`, `seed_regions` (no migration loads the regions),
   `compilemessages` and `collectstatic`. The owner's staff account needs a verified phone before the
   panel will open for it (§19 Q34).
   Two items moved here from Phase 0 (§17 #31):
   - **Redis** — install it, set `REDIS_URL`, and confirm the rate limiter counts correctly across
     more than one gunicorn worker. Without it, risk #15 is live from the first day of traffic.
   - **Backups** — nightly `pg_dump` plus a `media/` copy, both off-server, and a **verified
     restore** into a scratch database with row counts checked, before the site takes a real order.
     An untested backup is not a backup.
9. **Register the Click webhook** at `https://graphix.uz/payment/click/update/`; verify with a real
   1 000 so'm payment end to end. *The single highest-risk step in the project — a wrong webhook URL
   means silent payment failures.*
10. Confirm an OTP SMS arrives with the GRAPHIX sender name — **the sender is approved** (§19 Q17).
    Check with Eskiz that the **two message bodies** are moderated too: both changed in Phase 1a,
    and Eskiz moderates the text, not just the sender. A rejected body fails silently at signup.
11. **Fill the real credentials into the server `.env`** — `GOOGLE_MAPS_API_KEY`,
    `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, Click, Eskiz. Every one of them ships blank and the
    code runs without it (§17 #93), so this step turns features on rather than fixing breakage.
    **If the shop's bot service relays the notifications** (§17 #206), it is
    `TELEGRAM_BOT_WEBHOOK_URL` and `WEBSITE_WEBHOOK_SECRET` instead — the secret is the value the bot
    holds, and the URL must be HTTPS unless the bot runs on this same server (§19 Q33).
12. Google Search Console: add graphix.uz, verify, submit the sitemap. *No Change of Address — there
    is no old property to move from (§17 #35).*
13. **Do what the privacy policy says the server does** (§17 #183, #196). Run
    `manage.py prune_guest_carts` daily from cron or a systemd timer — the policy says a guest cart is
    deleted after thirty days, and nothing but that command deletes one. Give nginx's access log the
    same thirty-day rotation the Django log already has (`LOG_RETENTION_DAYS`). The VPS is in Warsaw,
    and the policy's cross-border section says so (§17 #211); Poland is on the Cabinet of Ministers'
    list of countries that protect personal data equally (§17 #215).

**Phase 1b Definition of Done:** graphix.uz serves over HTTPS · a real Click payment completes and
the order flips to `paid` · an OTP SMS arrives branded GRAPHIX · the OG image renders correctly when
pasted into Telegram · **Redis is live and the rate limiter counts correctly across multiple gunicorn
workers** · **a `pg_dump` + `media/` backup has been restored off-server with row counts checked.**

---

### Phase 2 — Design system and visual direction

*Goal: one agreed visual language, expressed as tokens and components, before any page is rebuilt.*

1. **Round one — three directions, all rejected.** A · Galereya (light gallery), B · Bosma (print
   spec sheet), C · Tungi (near-black). Kamronbek's verdict, in his words: the type was *"thin and
   sharp, looks like hand made cheap design"*, the desktop layout was *"nothing"* with *"metrics
   wrong"* — one image filling the page and three or four scrolls to reach the bottom of it — and
   the customer wants **dark, but not pure black**. Archived in git history; superseded.

   **What was actually wrong, so it doesn't repeat (§17 #44):**
   - *The desktop layout was broken, not merely plain.* The product image had no height cap and the
     two-column breakpoint sat at 900 px, so at any narrower frame the page collapsed to one column
     and the image ran to its natural height. That is a bug that got shipped as a design.
   - *The typography was thin because the shortlist was biased.* Every candidate came from one
     register — modern grotesques — so all three directions inherited the same tech-sans voice.
     Screening never covered editorial or fashion faces at all.
   - *Light text on a dark ground reads thinner than it measures.* 400-weight and pure white on
     near-black is exactly the combination that looks brittle.

2. ✅ **Round two — one direction, built properly.** `docs/design/directions.html`, still one
   self-contained file, now showing **two pages** (product and shop) at 390 px and desktop.
   - **Ground:** warm charcoal, not black — `#100E0C` with `#17140F` and `#211C15` layered above,
     so panels separate by material rather than by outline.
   - **Accent:** brass `#C6A44E`, carrying the price, the chosen size and the buy button. Nothing else.
   - **Ink:** warm off-white `#EFE9DE`, never pure white — it stops the halation that thins white
     text on dark.
   - **Type:** Playfair Display 600–700 for display, Onest 500–600 for UI. **Body weight is 500 and
     never 400.**
   - **Desktop product page:** two columns from 860 px — gallery left with a vertical thumbnail
     rail, buy panel right at 430–470 px, sticky gallery. **The main image is capped at
     `min(76vh, 760px)`**, so one photograph never exceeds one screen (§17 #47).
   - **Shop:** 2 columns at 390 px, 3 from 720 px, 4 from 860 px; filter chips and a sort control.

   **Signed off 2026-09-09** — turned into tokens and components below.
3. ✅ Fill in every token value in `tokens.css` — colour, space, type, radius, shadow, motion,
   layout, z-index. No `TODO` remains. **Every foreground token was contrast-checked against all
   four grounds: the lowest ratio in the whole system is 3.34:1 on `--c-fg-subtle` (decorative,
   needs 3.0), and every text token clears 4.5:1 with room to spare.**
   Two layout constants live here as tokens rather than in a component, because they are contracts:
   `--ar-product: 4/5` (one ratio for the whole catalogue) and `--pdp-image-max: min(76vh, 760px)`
   (§17 #47).
4. Self-host the typefaces. Subset to Latin + Latin Extended (Uzbek needs `oʻ` and `gʻ`) + Cyrillic.

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

   ✅ **A second batch was screened after round one was rejected as "thin and sharp"** — 35 more
   families, this time editorial, serif and fashion faces, because the first shortlist had been
   drawn entirely from modern grotesques and that bias *was* the problem (§17 #44). 18 more pass.
   The one that matters: **Playfair Display** — a high-contrast fashion serif that contains U+02BB
   and Cyrillic, at 294 KB variable. Also passing: Cormorant, EB Garamond, Spectral, Literata,
   Lora, Source Serif 4, Alegreya, Bona Nova, Merriweather, Noto Serif, Montserrat, Raleway,
   Nunito, Fira Sans, Exo 2, Comfortaa.

   **Failing, and worth knowing** — every conventional Cyrillic fashion display face:
   **Prata, Forum, Tenor Sans, Bodoni Moda, Marcellus**, plus PT Serif, PT Sans, Philosopher,
   Oranienbaum, Arsenal, Cuprum and Fraunces. There is very little premium display type that can
   set Uzbek, which is exactly why this has to be checked before a face is proposed.

   **Chosen (round two): Playfair Display display + Onest UI + IBM Plex Mono where data needs it.**

   ✅ **Self-hosted and subset.** `pyftsubset` to Latin + Latin Ext-A/B + U+02BB/02BC + Cyrillic +
   the punctuation and symbols the storefront actually prints, then WOFF2. The variable axes
   survive, so one file covers every weight: **Playfair 293 KB → 56 KB, Onest 188 KB → 54 KB,
   IBM Plex Mono 132 KB → 21 KB.** `font-display: swap`; the two storefront faces are preloaded.
   Mono is declared but **not** preloaded — no storefront page sets it, so the browser never fetches
   it until the admin panel does in Phase 7. The third-party `rsms.me` request is gone.

   ✅ **Wordmark lockups delivered** (§17 #38): `logo-full.svg` and `logo-stacked.svg`, outlined from
   Playfair Display 700 at 0.055 em tracking and cap-height-aligned to the mark, `currentColor` so
   one file serves both light and dark.
5. ✅ Build `base.css` — `@font-face`, reset, typography scale, layout primitives, utilities,
   focus ring, the global reduced-motion guard.
6. ✅ Build `components.css` — the full §8 inventory in 22 numbered blocks: buttons (4 variants ×
   3 sizes × disabled/loading), inputs, textarea, select, checkbox, radio, quantity stepper, OTP
   cells, search field, product card, gallery, size selector, spec strip, star rating (display and
   input), review card, heart with count, share, badges, modal/mobile sheet, toast, breadcrumb,
   pagination, empty state, skeleton, the table that stacks into cards, filter chips, the
   list-first pickup picker, tabs, accordion, nav + drawer, footer, language switcher, messages,
   product grid, mobile buy-bar and the height-capped hero.
7. ✅ **Living style guide at `/boshqaruv/style/`**, `staff_member_required` and `noindex`.
   Verified: anonymous → 302, non-staff → 302, staff → 200.
   It is deliberately **standalone rather than extending `base.html`** — the storefront still runs
   on the old `main.css` until Phase 5, and loading both stylesheets together would let their class
   names collide (§17 #48). This is the only page loading the new system until then.
8. ✅ Motion tokens plus one global `prefers-reduced-motion` guard in `base.css`.
9. ✅ Icons: 28 symbols in one inline SVG sprite, `templates/partials/_icons.svg.html`, inheriting
   `currentColor`. No icon fonts.
10. **Verify the above-the-fold rule** — on a 390 × 844 viewport the home hero must leave at least
   one partially visible row of product cards. The `.hero` component enforces it with
   `max-height: 58vh` on mobile, so the rule is structural rather than a judgement call. **The
   measurement itself moves to Phase 5**, where the home page is actually built; there is no home
   hero to measure yet.

> **Photography note.** The directions are built on **drawn garment mockups**, not photographs —
> there is no product photography yet, and Kamronbek chose to proceed rather than wait (§17 #42).
> Layout, crop, hierarchy and type are judgeable from them. *Whether the shop looks professional*
> is not — that question belongs to the photography, and §8 is explicit that no CSS rescues bad
> photos. The generator lives in `docs/design/mockup/`; real shots drop straight in.

**Definition of Done:** a direction is chosen and recorded in §17 · `tokens.css` has no `TODO` ·
every component exists in the style guide with all states · contrast passes on every token pairing ·
fonts self-hosted and preloaded · CSS under budget · the style guide renders at all six breakpoints.

**Verified 2026-09-09:** direction recorded (§17 #44–47) · no `TODO` in `tokens.css` · every
component renders at `/boshqaruv/style/`, which returns 302 for anonymous, 302 for non-staff and 200
for staff · **lowest contrast anywhere in the system is 3.34:1 on a decorative token; every text
token clears 4.5:1** · fonts self-hosted, subset and preloaded · **CSS 8.5 KB gzipped against a
60 KB budget** · `manage.py check` clean · `makemigrations --check` clean · 4 smoke tests pass.

**Still open:** item 10's measurement, which needs the Phase 5 home page.

---

### Phase 3 — Internationalisation foundation

*Goal: uz / ru / en infrastructure in place, so every template built afterwards is translatable from
the first line.* **Deliberately before the page rebuild** — adding i18n afterwards means editing
every template twice.

1. ✅ Settings: `LANGUAGES = [('uz', "Oʻzbekcha"), ('ru', 'Русский'), ('en', 'English')]`,
   `LANGUAGE_CODE = 'uz'`, `LOCALE_PATHS`. `LocaleMiddleware` **after** `SessionMiddleware`, **before**
   `CommonMiddleware`. A one-year `graphix_lang` cookie is the fallback; the URL prefix decides.
2. ✅ Public URL tree wrapped in `i18n_patterns(...)` — with `prefix_default_language=False` as built, and **`=True` since 2026-09-14** (§17 #121), so Uzbek is at `/uz/` too. Admin, sitemap,
   robots, manifest, `set_language`, media and static stay **outside** it (§6) — **and so does the
   Click webhook**, which now lives in its own `webhook_urlpatterns` list in `payment/urls.py` that
   `vm/urls.py` includes before the prefixed block (§17 #52).
   **Five tests guard it**: `reverse('click_webhook')` is `/payment/click/update/` under uz, ru *and*
   en; the path resolves to the webhook view; and `/ru/…` and `/en/…` variants both 404.
3. ✅ `set_language` wired at `/i18n/setlang/` plus a POST language switcher in the footer. Verified:
   posting `language=ru, next=/shop/` redirects to `/ru/shop/` — the visitor stays on the page they
   were reading.
4. ✅ `<html lang="{{ LANGUAGE_CODE }}">` and `hreflang` alternates for all three languages plus
   `x-default`, both fed by the same context processor as the switcher so they cannot disagree.
   Sitemaps set `i18n`/`alternates`/`x_default`: **21 `<url>` entries, 84 `xhtml:link` alternates.**
5. ✅ Translation fields (`name_ru/_en`, `description_ru/_en`, `colour_ru/_en`) with migration
   `product.0009_i18n_fields`, plus `core/i18n.py::tfield` and the `{{ obj|t:"name" }}` filter.
   **Uzbek stays in the base field**, so every existing row keeps working with no backfill (§17 #8),
   and a *blank* translation falls back rather than rendering an empty product name.
6. ✅ Django admin groups the fields into one fieldset per language, Uzbek first, each non-Uzbek
   fieldset labelled "blank falls back to Uzbek".
7. ✅ `locale/{uz,ru,en}/LC_MESSAGES/`, `makemessages`, `compilemessages`. **25 strings, all three
   catalogues compiled.** gettext is already installed on the development machine.

**Translation quality standard** — this decides whether the site reads professional or machine-made:

- **Uzbek** is the source of truth. Latin script. Correct `oʻ` / `gʻ` (U+02BB) — never a plain ASCII
  apostrophe in body copy. Every string Phase 3 touched was corrected on the way through; the
  remaining ASCII apostrophes are all in templates that Phase 5 replaces, and are corrected there as
  each page is rebuilt (§17 #50).
- **Russian** written in natural commercial register, *not* word-for-word from the Uzbek. The two
  languages differ enough structurally that literal translation reads as broken.
- **English** written for a fluent reader, not translated.
- **Never** bulk-machine-translate into `.po` files. Every string reviewed before `compilemessages`.
- Translator comments on any string ambiguous out of context.

> **Scope call — template copy moves to Phase 5 (§17 #50).** Phase 3 delivers the machinery and
> every **Python-side** string: form labels and errors, validator messages, rate-limit and checkout
> messages — 25 strings, written in three languages, compiled and tested. It does **not** wrap the
> current templates, because Phase 5 rebuilds all 25 of them from scratch; wrapping them now means
> translating copy that Phase 5 deletes, which is the exact "written twice" waste this phase exists
> to prevent. Phase 5's per-page checklist already requires all three languages, so each page is
> written once, in three languages, against the finished design.

**Definition of Done:** all three languages resolve and render · switching preserves the current page
· the Click webhook resolves unprefixed under every language · sitemap emits three URLs per page with
correct `hreflang` · translation fields editable in the admin · every Python-side string translated
to native quality.

**Verified 2026-09-09:** `/`, `/ru/`, `/en/` and `/shop/`, `/ru/shop/`, `/en/shop/` all return 200 ·
`set_language` moves `/shop/` → `/ru/shop/` · **`/payment/click/update/` resolves unprefixed (405 to
a GET, i.e. the view is there) while `/ru/payment/click/update/` 404s** · sitemap emits 21 `<url>`
entries with 84 alternates and 21 `x-default` · 4 `hreflang` tags on every page · translation
fieldsets render in the admin · `check` and `check --deploy` clean · **23 tests pass** (4 smoke + 19
new).

*The remaining DoD clause — a **completed** test payment — needs a live Click endpoint and is
carried to Phase 1b, where the webhook is registered against the real domain.*

---

### Phase 4 — Data model expansion

*Goal: every schema change landed and migrated, so the UI phases build against a final model.*

1. Write all migrations from §7 — product (slug, ~~translations~~ *(landed in Phase 3 as
   `product.0009_i18n_fields`)*, tags, `likes_count`, rating denorm,
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
11. ~~Seed the size charts, using the owner's uploaded chart images.~~ **Carried to Phase 6** — the
    models are built and registered in the admin, but no chart images exist to seed (§19 Q9). Nothing
    in the DoD depends on it.
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

> **Superseded on 2026-09-12 (§17 #84).** Everything below shipped and works, and none of it is
> used any more: there is no branch table in the target model. Phase 6d replaced it with `Region`,
> `District` and a typed postal index, and retired `PickupPoint`, `seed_pickup_points` and
> `data/pickup_points.csv`. Kept here unedited because Phase 4 is closed and its record should say
> what it actually did — and because the reasoning below is *why* the redesign happened.

**Built in Phase 4, and the file is empty on purpose.** The command validates the whole file before
writing anything, checks every coordinate against Uzbekistan's bounding box (which catches swapped
lat/lng — the one typo that yields a perfect-looking row pointing at another country), and ships with
`data/README.md` documenting every column. `data/pickup_points.csv` has a header and no rows:
inventing branches to make the phase look finished would misroute real parcels (§17 #58). Q3 is now
the blocker, not the loader.

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
   - Gallery with thumbnails, swipe, and arrow-key navigation. **Zoom moves to Phase 6a**,
     where it shares one full-screen viewer with the size chart (§17 #79)
   - Title, price, **star rating + review count** (hidden entirely until the first approved review —
     an empty rating looks worse than no rating)
   - Size selection with clear out-of-stock states; **no colour picker**
   - **Size-guide link** beside the sizes
   - **Spec strip** — GSM / material · print method
   - **Heart** (saves + counts) and **share** buttons
   - Description, **reviews section**, related products
   - Delivery line: "15 000 so'm pochta boʻlimiga · 30 000 so'm eshikkacha" — **what shipped.**
     Phase 6e changed the second figure to 40 000 (§17 #85)
   - Sticky add-to-cart bar on mobile
3. **Shop (`/shop/`)** — responsive grid; filters as a sticky sidebar on desktop and a sheet that
   comes down from the top on mobile (§17 #76, #77); **tag filters**; pagination; a real empty state.
   **"Ommabop"** and **"Reyting bo'yicha"** sort with the data that makes them meaningful, in Phase 6b,
   and **skeleton loading** arrives with the first asynchronous fetch there too — the grid is rendered
   by the server today, so there is no moment for a skeleton to fill (§17 #79).
4. **Home (`/`)** — hero that shows actual product and **obeys the above-the-fold rule**; tagline;
   a **"Siz uchun" (For you) row** — filled with most-liked initially, swapped for the real
   recommender in Phase 13; new arrivals; category entry points; brand statement.
5. **Search results (`/qidiruv/`)** — global search across name, description and tags.
6. **Cart** — line items with thumbnails, quantity steppers, totals; the checkout button prompts
   login for guests, stating plainly that the cart is kept. **The anonymous cart itself is Phase 6g.**
   Phase 4 built the model for it — nullable `user`, `session_key`, two partial unique constraints —
   but the views never followed: `cart`, `cart_update` and `cart_remove` were still `@login_required`
   and `cart_add` sent an anonymous visitor to login. Found by this phase's gate review (§17 #79);
   built in 6g.
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
- [ ] Images have `alt`, and a frame that holds the catalogue’s 4:5 ratio before the file
      arrives, so nothing shifts. `width`/`height` and `srcset` need the image pipeline and
      belong to Phase 9 (§18 #14)
- [ ] No hardcoded colour, spacing or font-size value, and no `style` attribute
- [ ] Every user-facing string it can produce goes through `{% trans %}` **or `gettext`** — the
      Python that flashes a message at the page is copy too (§17 #80)

**Definition of Done:** every page passes its full checklist · the old `main.css` is deleted · CSS
and JS under the §5 budget, **measured gzipped, which is how they are served** · no class defined in
CSS that no markup uses, and no class used in markup that no rule styles · every user-facing string
through gettext · `.git/audit.py`, `.git/interact.py` and `.git/fold.py` all clean · the full test
suite green.

**Lighthouse is Phase 9's gate, not this one.** The mobile score is dominated by the image pipeline,
which does not exist yet: measuring it here would either fail for a reason this phase cannot fix, or
pass against a catalogue of eight photographs and mean nothing. §5's targets stand; Phase 9 owns
proving them (§17 #79).

---

### Phase 6 — Product and checkout features

*Goal: the features that make the shop genuinely better to use.*

**6a — Size guide and the zoomable viewer.** The standalone `/size-guide/` page (now
`/olcham-jadvali/`) already shipped in
Phase 5, and it shows the chart only when `static/img/size_guide.png` is actually there — Kamronbek's
call, and the right one: if there is no chart, nobody should learn that there was supposed to be one
(§17 #69). The link beside the size selector goes to that page.

What is left here is the **viewer**: a tap on the size chart — or on a product photograph — opens it
full-screen with native pinch-zoom and a focus trap. One viewer serves both, which is why the gallery's
zoom was moved here rather than built twice (§17 #79). The `.overlay` / `.modal` CSS is already in the
design system waiting for it.

Then the **`SizeChartRow` table** below the image, with the selected size highlighted and the chart
note in the active language.

**We produce the chart ourselves** (§19 Q9 answered, §17 #95). Two charts, a regular cut and an
oversize one — drawn to the design system rather than photographed:
a garment diagram with the four measured lines (chest, length, shoulder, sleeve) and a table of
`SizeChartRow` values for S/M/L/XL, in all three languages. It ships as `static/img/size_guide.png`
plus seeded `SizeChart` rows, which also closes Phase 4's carried item 11. **The measurements must
come from the real garments before launch** — a chart that does not match what arrives in the parcel
is worse than no chart, so Phase 11 verifies them against stock. Kamronbek replaces the image
whenever he wants; the page picks it up with no deploy (#69).

**6b — Likes (save + popularity) and share.**

- Heart on the product card and product page, with the live count.
- POST toggle, CSRF-protected, via `fetch` with optimistic UI and rollback on failure. **Works without
  JavaScript** — a plain form POST that redirects back.
- `likes_count` updated with `F('likes_count') ± 1` inside a transaction.
- Anonymous visitors see the count and get a login prompt on click.
- Rate limited via `core/ratelimit.py` (60 toggles / 5 min / user).
- New sorts: **Ommabop** (`?sort=popular`) and **Reyting** (`?sort=rating`).
- **Share button** — `navigator.share` on mobile; on desktop a menu with Telegram and copy-link.
  Telegram first: it is where Uzbek sharing actually happens. *Instagram was dropped as built: it has
  no URL that shares a link, so copy-link is the Instagram path (`main.js`).*

**6c — Global search.** Header search field on every page, posting to `/qidiruv/`. Matches product
name (all languages), description and tag names. Debounced suggestions are a nice-to-have, not a
requirement; the results page is.

**6d — Delivery method selection, the map, and retiring the branch table.**
*(Highest complexity in this phase.)*

The checkout's delivery step is **one choice that reveals one of two different forms**. Nothing from
the branch the customer did not pick is submitted, validated or stored.

```
                        DELIVERY
                            │
              ┌─────────────┴─────────────┐
              │                           │
            HOME                        UZPOST
              │                           │
      ┌───────┴───────┐                   │
      │               │                   │
    MAP           MANUAL           POSTAL INDEX
   lat/lng        address              index
      │               │                   │
      └───────┬───────┘                   │
              │                           │
              └─────────────┬─────────────┘
                            │
                          ORDER
```

*Kamronbek's diagram, kept verbatim: it is the clearest statement of the design in the whole plan.
Two branches, nothing shared but the order they both produce.*

**Uzpost branch — 15 000 so'm. No map on our side at all.** Three fields:

- **Region** — a drawer, 14 entries.
- **Tuman / shahar** — a drawer scoped to the chosen region, so it lists 10–30 entries rather than
  210, grouped under *Tumanlar* and *Shaharlar* headings: someone in Angren is looking for a city, not
  scanning an alphabetical mix. **Changing the region clears this field** — a stale district from the
  previous region would submit silently, and a wrong address that looks completely plausible is the
  worst kind (§17 #87).
- **Postal index** — six digits, typed. Validated as §7 describes.

Each drawer shows a search field **only above about fifteen entries**, which in practice means the
largest regions only; a search box over twelve items is clutter. Both fall back to plain `<select>`s
with JavaScript off.

**A customer who does not know their index gets a link to Uzpost's own branch map**
(`uz.post/uz/map`) — a clustered national map that searches by address *and* by index and filters by
branch type. It **opens in a new tab**, and the checkout form state is written to `sessionStorage`
first, so nothing is lost if they come back through history instead: the same pattern the signup form
already uses for its terms link. Sending someone off-site mid-checkout is a real drop-off risk, and
these two mitigations are what make it acceptable (§17 #92).

**Home delivery — 40 000 so'm.** Two ways to give an address, presented as a toggle, and
`address_source` records which was used:

- **Map** — a draggable pin defaulting to Tashkent centre, plus a "use my location" button behind an
  explicit permission prompt. Dropping the pin stores `latitude`/`longitude` and reverse-geocodes into
  the address field, which the customer can then edit freely.
- **Manual** — the customer types the address. No coordinates stored.

**The address field stays required either way, pin or no pin** (§17 #91). A courier delivers to an
address, not to a coordinate; the pin adds precision on top of one. That also means a failed geocode
or a denied permission costs the customer nothing.

**The map is needed on this one form only**, which is what made Google affordable (§17 #83): all map
code behind the `GX.map` wrapper (§8), Google Maps JS never blocking first paint. *As built it is
`defer`, not `async` (§17 #119), and it loads with the checkout page whenever a key is set; loading it
only when the map is about to be used is §18 #34.*

**The key is `GOOGLE_MAPS_API_KEY` in `.env`, and it ships blank** (§17 #93). Everything is written as
though it were set — loader, wrapper, pin, reverse-geocoding, the referrer restriction documented in
`.env.example`. With the variable empty the map block simply does not render and the address field
carries the form on its own, which is the behaviour §3 already requires when the script is blocked.
That means the map can be turned on later by pasting a key into the server `.env`, with no deploy and
nothing to rewrite.

**Retiring the branch table** — part of this sub-phase, in one migration: add `Region` and `District`,
add `Order.region` / `district` / `postal_index` / `address_source`, rename `pickup_snapshot` to
`location_snapshot` and `DeliveryOption.requires_pickup_point` to `requires_branch`, then drop
`Order.pickup_point` and `PickupPoint`. Also delete `seed_pickup_points`, `data/pickup_points.csv` and
their tests, and replace them with `seed_regions` + `data/regions.csv`; update `create_order_from_cart`'s
keyword arguments, `payment/admin.py`, `order_detail.html` and the style guide's picker demo. **No
order in the database points at a `PickupPoint`** (checkout has never set one), so the drop is safe —
verify that before running it, not after.
- **The map is assistive, never required.** The address field stays required and authoritative for home
  delivery; the branch method has no map to fail. A customer who denies location permission, blocks the
  script, or has JavaScript off can still complete checkout. **Hard requirement, not a nicety** — and
  cheaper to honour now that only one of the two methods involves a map at all.
- Store `latitude`/`longitude` + `address_source` (home) or `region` + `district` + `postal_index`
  (branch) on the order, and `location_snapshot` either way.
- **`seed_regions`** mirrors `seed_pickup_points`' discipline: validate the whole CSV before writing
  anything, upsert on SOATO code, deactivate rather than delete so an order's `PROTECT` key survives,
  idempotent across runs. `data/regions.csv` is committed — 14 regions and ~210 districts and cities.
  **Two levels only, no mahallas.** Small enough to verify by hand in an afternoon, and worth it,
  because a wrong district name at checkout is a wrong parcel (§19 Q23).
- **We build and verify `data/regions.csv` in-project** (§19 Q23 answered): assembled from the
  classifier, cross-checked against published directories and the public compilations, every postal
  prefix confirmed, and the sources and method written into `data/README.md` so the next person can
  re-check rather than re-trust. A wrong prefix rejects valid indexes at checkout, which is a silent
  lost sale, so this is verification work rather than a copy-paste.
- **The CSV is built from the official SOATO / MHOBT classifier, not copied from a public repo**
  (§17 #90). Three compilations exist on GitHub; the most complete one is GPL-3.0 and the other two
  carry **no licence at all**, which is legally worse — no licence means all rights reserved. An
  administrative division is a government-published fact and nobody owns it; a particular compilation
  of one may be owned. They are a cross-check, not a source.
- The admin order view and the Telegram notification both show a maps deep link for the courier.
- Graceful failure: if the script fails to load, the map area hides itself and everything still works.
  Never a broken grey box.

**6e — Delivery tiers.**

- `DeliveryOption` selector at checkout: **15 000 so'm to an Uzpost branch** or **40 000 so'm to the
  home**. Choosing the branch option reveals the region and district drawers and the index field;
  choosing home reveals the address toggle and the map.
- **Change the seeded home price from 30 000 to 40 000** (§17 #85) — the migration row, the product
  page's delivery line, `delivery.html`, the style guide and the three `.po` entries that carry the
  delivery paragraph, plus the assertion in `core/test_phase4.py`. *Done — §18 #18.*
- Both tiers ship via Uzpost, Tashkent and regions alike — stated at checkout, on the confirmation, on
  `/yetkazib-berish/` and in the terms. The customer should never be surprised about who delivers.
- `delivery_price` snapshotted onto the order; the total computed inside the existing locked
  transaction via `create_order_from_cart`'s `delivery` argument. **Do not restructure the
  locked-total computation.**
- **Remove the disabled "Naqd pul" control from checkout.** Cash is out of scope, for delivery and
  for payment alike (§17 #94, §19 Q13): the shop takes Click and nothing else. The `payment_method`
  field and its `CASH` choice stay in the model — dropping them would be a destructive migration for
  no gain, and the admin may yet need to record an exception — but the storefront offers one method,
  and the checkout view **rejects any other value rather than defaulting past it**. A disabled control
  that has sat there since before the rebuild reads as "coming soon" to a customer; deleting it is
  the honest version. *Amended during the build: cash is kept and switched off, as a `PaymentOption`
  row the owner can turn on — an inactive method is absent from checkout, not greyed out (§17 #99).*
- **Delivery timeframes are quoted, not guessed.** Look them up on uz.post for both tiers, Tashkent
  and regions (§19 Q10), and state them at checkout, on the confirmation and on `/yetkazib-berish/`.
  A customer deciding between 15 000 and 40 000 is really deciding between two waits.

**6f — Telegram notifications.**

A new `core/telegram.py`, structured exactly like `core/sms.py`: module logger, catches everything,
logs failures, returns a boolean, **never raises**. Credentials `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID` in `.env` (§19 Q2) — the code must degrade silently and log a warning when they
are unset, so local development is unaffected.

*Since 2026-09-16 there is a second route:* with `TELEGRAM_BOT_WEBHOOK_URL` set, the same three events
go to the shop's own bot service as signed JSON, and the bot talks to Telegram (§17 #206). The
contract for the bot is `docs/integrations/telegram-bot.md`.

Fired via `transaction.on_commit()` so a notification is never sent for a rolled-back transaction and
a Telegram outage can never fail a checkout.

| Event | Message contents |
|---|---|
| **Order paid** | Order number · item count and each line (name / size × qty) · total · delivery tier and price · **region · district · index, or the address and a map link** · payment method · recipient name and phone (tap-to-call) · link to the order in the staff panel. **Sent when the payment lands, not when the order is written (§17 #237)** — an unpaid or cancelled order notifies nobody |
| ~~**Payment confirmed**~~ | Merged into the order event on 2026-09-18 (§17 #237): one message per order, carrying everything, when the money has arrived |
| **New contact message** | Sender name and username · phone (tap-to-call) · topic · message body · link to the message in the staff panel |
| **New review awaiting moderation** | Product · rating · excerpt · whether photos were attached · link to the review in the staff panel |

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
branch selected by region, district and index, with a home-delivery pin, **and with JavaScript
disabled** · an index that contradicts its region is rejected · delivery price and location snapshot
are frozen on the order · **the storefront offers Click and nothing else, and a POSTed `cash`
method is rejected** · a Click order still completes end to end · a Telegram message arrives within seconds of an order, a message
and a review · unsetting the Telegram credentials breaks nothing · a guest cart survives login and
merges correctly · an unverified user with an order is never deleted.

---

### Phase 7 — Admin panel

*Goal: a focused staff panel at `/boshqaruv/` that runs the daily job from a phone. Django admin stays
for everything else.* Guarded by `staff_member_required`, built on the same design system, mobile-first.

**The owner adds every product himself, with photos, from this panel.** Product creation is therefore
the panel's most important screen, not an afterthought — it gets the same design care as the
storefront's product page.

1. **Dashboard** ("Hisobot") — today and this week: orders, revenue, awaiting payment, in progress,
   out for delivery, low stock, unread messages, **new reviews**. "Running low" means *on sale and
   down to five or fewer*, defined once on `Variant` and shared by the tile, the list under it and
   the list it links to (§17 #179).
2. **Orders** — filter by status, date, payment method, delivery tier; search by `order_no`, phone or
   customer; inline status change; detail view with items, customer, tap-to-call phone, address or
   pickup branch, map link, and notes. Status changes logged with who and when.
3. **Products** — the core screen:
   - List with thumbnail, price, total stock, availability; toggle availability and edit stock and
     price inline without a page reload.
   - **Create / edit**: name and description per language, category, **tags**, **spec fields (GSM,
     material, print method)**, size chart, multi-image upload with drag-to-reorder and instant
     preview, and a **size × stock grid** (colour hidden — the default colour is applied silently).
   - Client-side image validation before upload (type, dimensions, file size) with a clear error — the
     owner should never wait 30 s for an upload that will be rejected.
4. **Reviews** — moderation queue: approve or reject, with the photos shown at a reviewable size.
   Approving recomputes the product's `rating_avg` and `review_count`.
5. **Regions and districts** — search, edit, activate/deactivate, correct a postal prefix. Small reference data, edited rarely; the screen exists so a district rename never needs a deploy.
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

### Phase 8 — Legal documents and content *(complete, 2026-09-16)*

*Goal: real, complete, trilingual legal pages, and site copy that reads like a brand.* Written
in-project, to a real standard, against Uzbek law — not filled from a generic template.

**How it was built.** Each document is written whole, once per language, in
`templates/legal/<doc>.<lang>.html` — nine files — and rendered inside one shared page that carries the
version, a contents list read out of the text itself, and the version history (§17 #182, #192). Every
figure a document states is read from the code that enforces it, through `core/legal.py` (§17 #183),
and the seller's details are written there once and printed by the footer and the contact page too
(§17 #184, #193). The Uzbek text is authoritative and the Russian and English say so at the top.

1. ✅ **Privacy policy** (`/privacy/`) — the data controller and how to contact them; what is collected
   (name, username, phone, delivery address, map coordinates, chosen pickup branch, order history,
   reviews and review photos, contact messages, IP for rate limiting, session and cart data); why and
   on what legal basis; who it is shared with (**Eskiz** for SMS, **Click** for payment, **Google**
   for maps and geocoding, **Uzpost** for delivery, **Telegram** for internal order notifications);
   retention; the customer's rights and how to exercise them; cookies and browser storage, including
   the anonymous cart and the `sessionStorage` signup draft; children's data; how changes are
   announced. Written against the Uzbek personal-data law
   (*"Shaxsga doir ma'lumotlar to'g'risida"gi qonun*).
   *Built:* eleven sections. Written against the law as amended on 26.03.2026 (ZRU-1125), which
   narrowed data localisation to biometric, genetic and telecom data, so an ordinary shop database may
   sit on a server abroad provided the policy says so — the server is in Warsaw, and it does (§17 #211);
   the host meets the first of the amendment's conditions — Poland is on the Cabinet of Ministers' list
   (§17 #215, §19 Q32). Registering with the state register of
   personal-data operators is the owner's to do (§19 Q30). Every retention period it states is a value
   the code enforces, the log's thirty days included (§17 #196).
2. ✅ **Terms of use** (`/terms/`) — parties and definitions; registration and phone verification;
   ordering and when a contract forms; prices, currency and VAT; **payment via Click only — the shop
   takes no cash, for the goods or the delivery** (§17 #94); **delivery terms — 15 000 so'm to an Uzpost branch, 40 000 so'm to the home, all via
   Uzpost nationwide, expected timeframes, and the uncollected-parcel policy — **the Postal Service Rules
   (Ministry of Justice registration No. 2219, 18.04.2011 — earlier versions of this plan called them a
   Cabinet of Ministers resolution, §17 #186): held at the destination branch — a month for an ordinary
   parcel, 14 days on Bir Qadam (¶190) — a second notice if it is still uncollected (¶127), then return
   to the sender at the sender's expense (¶188). The sender is GRAPHIX**, so an uncollected parcel costs us both legs and a month of tied-up stock, and the terms
   must say what the customer gets back (§19 Q11)**; returns, exchanges and
   cancellation, including the sizing disclaimer (measurements approximate, ±1 cm); **review rules and
   the moderation policy**; intellectual property in the printed designs; acceptable use; limitation of
   liability; governing law and disputes; amendment procedure.
   *Built:* seventeen sections, the public offer and the seller's details among them. The payment
   methods and delivery prices it lists are the active rows (§17 #111). An uncollected or refused
   parcel: 15 000 so'm kept, the rest refunded by the admin within ten days (§17 #187). A wrong size is
   exchanged at the customer's cost both ways, a defect at ours (§17 #185). The seller is named as a
   sole proprietor at Qoʻqon's index (§17 #208, #209), and a branch holds a parcel one month (§17 #210).
3. ✅ **Delivery & returns page** (`/yetkazib-berish/`) — the plain-language version customers actually
   read before buying: both tiers, **the timeframes quoted from uz.post** for Tashkent and the regions
   (§19 Q10), how collection at a branch works, and what happens if nobody collects it.
   *Built:* seven sections, dated and versioned like the other two. The order page of every branch
   order states the same rule in two sentences and links here (§17 #191).
4. ✅ All three documents in all three languages, each with a version number, the day it took effect
   and its history (`VERSIONS` in `core/legal.py`). **Amending a document means adding a row there in
   the same commit**, never editing an old one — except once, before launch (Phase 11 item 8).
5. ✅ Linked from the footer, from the signup consent checkbox — which now names both documents and
   asks for consent to processing — and from a line beside the checkout button (§17 #195).
6. ✅ About and Contact rewritten in all three languages. The About page's same-day Tashkent promise is
   gone (§17 #194); the contact page names the seller and refuses a subject longer than its column.
7. ✅ Product copy guidelines — `docs/content/product-copy.md` — and a *Namunani qoʻyish* button beside
   each description box that inserts the template in that box's own language (§17 #197).

> These documents create real legal obligations under Uzbek law. They will be written carefully and
> completely, but an independent legal review before launch is still worth the cost — recommended,
> not a launch blocker.

**Definition of Done:** three documents complete in three languages · linked from footer and signup
consent · dated and versioned · delivery and review terms match the implemented behaviour exactly.

**Verified 2026-09-16:** 486 tests, among them 51 for this phase that hold each document's three
languages to the same sections, every stated figure to the code or row it comes from, the seller block
to Kamronbek's choice, and the links to both documents from all three places · `check` clean ·
`makemigrations --check` clean · no catalogue entry empty or fuzzy in any language, read by a parser
that can see a wrapped msgid (§17 #198) · `audit_live` 0 findings and 0 console errors across 24 pages × 5 widths × 3 languages · `drive_legal` 61 checks — every link in the signup consent, beside the checkout button, in a document's contents at 390 and 1440, on the order page and on the contact page opens what it says and lands below the sticky header · every changed page photographed at 390 and 1440 and looked at

**Rechecked 2026-09-16** (`phase-8-recheck`), every file read again and the pages driven in
Kamronbek's Brave as well as in Edge. Q27, Q28, Q29 and Q31 answered and built (§17 #208–#211); the
Telegram bot relay added (§17 #206, #207); and six things fixed that the first pass missed — the grey
site (§17 #205), "back" leading to the same document in another language (§17 #212), the log's two
404s (§17 #213), an email address broken inside "com" (§17 #214), the prune command's help describing a
filter it does not use, and the Russian delivery page sending readers to Uzpost's Uzbek map.
**525 tests** · `check` and `makemigrations --check` clean · no catalogue entry empty or fuzzy ·
`audit_live` 0 findings and 0 console errors across 24 pages × 5 widths × 3 languages ·
`drive_legal` 65 checks, a language switch on a document among them · the changed pages
photographed and looked at

---

### Phase 9 — Performance, SEO and accessibility *(complete, 2026-09-17)*

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
   `order_no`, `Variant(product, available)`, `District(region)`, `Order(postal_index)`.

**SEO**

9. Unique `<title>` and meta description per page, per language.
10. Open Graph and Twitter cards everywhere, product-specific on product pages. *In Uzbekistan most
    sharing happens on Telegram — the OG image and title are frequently the first thing a potential
    customer ever sees of the brand.*
11. JSON-LD: `Product` (with `offers` and **`aggregateRating` once reviews exist**), `Review`,
    `BreadcrumbList`, `Organization`.
12. Sitemap across all three languages with `hreflang`; canonicals; updated `robots.txt`.
13. Verify the old `/item/<pk>/` URLs still 301 to their product. There is no old domain to
    redirect (§17 #35).

**Accessibility**

14. Full keyboard pass over every page and flow.
15. Screen-reader pass on the critical path: shop → product → cart → checkout.
16. Contrast audit against the final palette — starting with form-control borders, which get a token
    of their own, `--c-line-control: #756853` (§17 #188, §19 Q22).
17. Focus trapping in modals, the navigation drawer and the region and district drawers; focus
    restored on close.
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
| `payment` | Checkout creates an order and closes the cart · concurrent checkout does not duplicate · empty cart rejected · **branch method charges 15 000 and requires region, district and index** · **home method charges 40 000 and rejects an index** · **a 5-digit or non-numeric index is rejected** · **an index whose prefix contradicts the chosen region is rejected** · **the prefix check is skipped for the `Boshqa` region but the format check still applies** · **delivery price is snapshotted and unaffected by a later price change** · **location snapshot survives the district being deactivated** · **a map order stores coordinates, a manual order does not, and `address_source` records which** · webhook marks paid · webhook idempotent · cancellation restores stock · **the checkout offers no cash method and rejects a POSTed one** |
| `product` | Shop filters by category, size and tag · sorts by price, popularity and rating · search matches name, description and tags in all languages · only available variants listed · slug resolves · old PK URL 301s · size-chart resolution falls back product → category → none |
| `reviews` | Only a delivered purchaser can review · one review per user per product · a new review is `pending` and invisible · approval publishes it and updates `rating_avg` and `review_count` · rejection does not · photo upload validates type and size |
| `core` | Rate limiter allows up to the limit and blocks past it · fails open on cache error · contact requires login to POST · **Telegram send failure does not break the request** · **missing Telegram credentials handled cleanly** · **`seed_regions` is idempotent and deactivates rather than deletes** |
| `i18n` | All three languages resolve · the webhook path is unprefixed · `tfield` falls back to Uzbek |
| Smoke | Every URL in §6 returns 200 (or the right redirect) for anonymous, logged-in and staff users |

**Security hardening**

1. `manage.py check --deploy` clean.
2. Verify HSTS, secure cookies, `SECURE_PROXY_SSL_HEADER`, CSP headers.
3. Rate limiter correct with Redis across multiple gunicorn workers.
4. All new endpoints (like, review, panel) enforce authentication, ownership and CSRF.
5. No view leaks another user's order, cart or liked items.
6. Click webhook validates signatures; a replayed callback is a no-op.
7. **Review photo upload rejects non-images and oversized files server-side**, not only in the browser,
   and strips EXIF (phone photos carry GPS coordinates).
8. Admin image upload validated server-side too — the panel since Phase 7, the Django admin since
   §17 #221. Verify both.
9. Review `DEBUG=False` error pages for information leakage.

**Repository hygiene** — small, long-standing items, done here because Phase 10 is the last phase
that touches the repo before it is deployed and they each affect what gets installed or cloned:

- ~~**Drop `django-environ` from `requirements.txt`**~~ ✅ *Done 2026-09-13, brought forward (§18 #4).*
- ~~**Delete the `Kamron's` branch**~~ ✅ *Done 2026-09-13, brought forward (§18 #5).*
- **Tests write into `vm/media/`** (§18 #42) — give every test that saves a file a throwaway
  `MEDIA_ROOT`, as the newer ones do, and clear what earlier runs left.

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
4. Final end-to-end live tests with a real card: **one order on each delivery tier** — a branch
   order by region, district and index, and a home order with a dropped pin — plus one home order
   with the address typed rather than pinned. No cash test while cash is off (§17 #99); if the owner
   switches it on before launch, add one.
5. Verify Telegram notifications end to end — through the bot service if it relays them (§17 #206),
   otherwise with the production bot token and chat ID.
6. Announce: Telegram channel, Instagram, Search Console.
7. Watch closely for 72 hours: server logs, failed payments, 404s in Search Console, Lighthouse field
   data, Telegram delivery.
8. **Legal pages.** Q27, Q28, Q29 and Q31 are answered and in the text (§17 #208–#211), edited into
   1.0 in place. Before launch: Q30 — registering as a personal-data operator — is the owner's; Q33
   asks where the bot service runs. Q32 is answered — Poland is on the Cabinet of Ministers' list —
   and the texts stay as they are (§17 #215).
   Then, if the texts are otherwise unchanged, set the three `VERSIONS` dates in `core/legal.py` to
   the launch day: nobody has been shown the 2026-09-15 wording, so this is the one time an existing
   row may be edited.

**After launch, once everything above is stable:** independent legal review of the Phase 8 documents ·
**rename the GitHub repository `ValleyMade` → `graphix` and the internal package `vm` → `graphix`**
(the repository: §18 #9, confirmed; the package: §3). Do the two together: the package rename touches the settings module,
wsgi, systemd, nginx and the venv, and the repository rename changes the clone URL and every local
remote — one rehearsal on a staging copy covers both, and doing them apart means two disruptions
instead of one. GitHub redirects the old repository URL, so nothing breaks the moment it happens; the
package rename is the half that can.

---

### Phase 12 — Reviews and ratings

*Goal: verified, moderated customer reviews with photos.* **Runs between Phase 6 and Phase 7**, so the
moderation UI lands with the rest of the admin panel and the product page is built only once.

1. **Submission flow** — `/order/<id>/sharh/`, reachable from a delivered order in the account area and
   from a link in the order-complete SMS. Rating 1–5, optional text, up to 4 photos. *The SMS link
   waits on Eskiz moderating the message bodies (§17 #104); the account area carries the entry points.*
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
- Cash as a default — cash on delivery and cash payment are a `PaymentOption` row that ships off;
  the owner can switch it on without a deploy (§17 #99, amending #94)
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
| 5 | Google Maps billing grows with traffic, or the free allowance changes again | Medium — a cost that scales with success | Google replaced the flat $200 monthly credit on **1 March 2025** with per-SKU thresholds — 10 000 free Essentials events a month. The map now loads on **one form for one delivery method**, so the volume is nowhere near it. A billing card is still required to issue a key at all, so: HTTP-referrer restriction and a budget alert on day one (§19 Q1). All map code stays behind `GX.map`, so 2GIS, Leaflet or Yandex remain a one-file swap |
| 6 | Delivery is priced below what Uzpost charges us | High — and now measured, not suspected | **The 15 000 branch tier is the one to worry about first.** Uzpost's own Bir Qadam tariff is **15 000 so'm for the first kilogram**, +3 000 per further kilogram, +7 000 to Nukus, Termiz and Urganch (§17 #103) — so that tier breaks even at one kilogram and loses money above it, and a two-tee order is over a kilogram once it is boxed. The 40 000 home tier is the owner's confirmed decision (§19 Q5) and its courier tariff is still unchecked. **Before launch: price a real two-tee parcel to a real far region on both tiers**, and treat Q24's partner programme as the lever if the margin is thin |
| 7 | Machine-translated Russian/English makes the site read as cheap | High — undermines the whole rebuild | Human-quality copy per Phase 3; never bulk-translate `.po` files |
| 8 | Product photography inconsistent | High — no CSS can rescue it | Photography standard in §8; a Phase 11 blocker |
| 9 | Owner- and customer-uploaded phone photos are enormous | High — a 3.8 MB image already exists | ✅ **Built in Phase 9 (§17 #230).** Every photograph is stored once and delivered as WebP at 400 / 800 / 1600 px, encoded down until it fits §5's 250 KB; the largest file any page fetched in the measured run was 41 KB. Both upload paths still check size and pixel count before decoding |
| 10 | A customer mistypes their postal index, or picks the wrong district | High — parcel sent to the wrong place | The index prefix is checked against the chosen region (§17 #86), which catches the province-level error; `location_snapshot` freezes what they chose, so the order record never drifts. A within-province typo is not detectable and is why the index is shown back on the confirmation page for the customer to check |
| 11 | Review photos are abused (offensive or irrelevant content on a public page) | High — brand damage | Moderation queue; nothing is public until approved; Telegram alert on every pending review |
| 12 | Selling designs that reproduce other brands' trademarks | High — legal exposure and payment-processor risk | If the mockup artwork was placeholder, no issue. If any are intended products, they should be reviewed before listing (§19 Q8) |
| 13 | Scope creep across a long project | High — nothing ships | §10 procedure; one phase at a time; §11 out-of-scope list |
| 14 | "100+ designs" is untrue at launch | Medium — a false claim in the first line a visitor reads | **Live and unmitigated.** Kamronbek chose to hardcode the claim (§17 #39), so the only remaining guard is **Phase 11 item 2, now a hard launch gate**: either the catalogue has 100+ designs or the line changes before launch |
| 15 | Rate limiting wrong across gunicorn workers without Redis | Medium — brute-force window | Redis on the VPS in Phase 1b (§17 #31), **and the server now exists** (§19 Q15). `settings.py` reads `REDIS_URL` and falls back to LocMemCache. ⚠️ **Amended 2026-09-18:** the server side was *not* the only thing outstanding — the `redis` package the backend needs was neither installed nor in `requirements.txt`, so setting `REDIS_URL` would have raised on the first cache read. Nothing caught it because local dev never sets `REDIS_URL`. Fixed by §17 #240 |
| 16 | Stock decrement races on a popular drop | Medium — oversell | Decrement inside the existing payment transaction; `select_for_update` on the variant row |
| 17 | Telegram outage or bad token breaks checkout | Medium | `on_commit` + catch-everything, mirroring `core/sms.py`; a test asserts failure doesn't break the request |
| 18 | Guest cart merge loses items or duplicates them | Medium — direct revenue loss | Merge inside a transaction with both carts locked; three dedicated tests |
| 19 | `media/` not in the database backup | Medium — irreplaceable photography lost | Explicit `media/` backup in Phase 10 |
| 20 | Legal documents wrong under Uzbek law | Medium — regulatory exposure | Written carefully in Phase 8; independent review recommended in Phase 11 |
| 21 | Task chats drift from the plan or each other | Medium — inconsistent codebase | §0 cross-chat protocol; every task chat reads the plan and updates §15–§17 |
| 22 | Tags never get filled in, so Phase 13 has no signal | Medium — the recommender is worthless | ✅ **Closed in Phase 9 (§19 Q35, §17 #228):** the product form refuses to save a product with no tag, in the panel and in the Django admin alike |
| 23 | The chosen typeface lacks U+02BB, so Uzbek renders as tofu | Medium — `Oʻzbekiston` breaks in the brand's own language | Check the cmap of every candidate face in Phase 2 before shortlisting. Poppins already failed this test; so did Prata, Forum, Tenor Sans and Bodoni Moda, i.e. every conventional Cyrillic fashion display face |
| 24 | A layout bug ships as a design decision | Medium — wasted review rounds and lost trust | Round one's desktop page was rejected as a design when the real fault was an uncapped image height and a 900 px breakpoint. Screenshot every page at 390 px **and** at desktop width before showing it, and hold it against §17 #47 |
| 25 | An uncollected branch parcel returns at our expense | Medium, and it recurs | The Postal Service Rules hold an ordinary parcel — the service we use — at the branch for a month, then send it back and **we** pay both legs (§17 #186, #210). **The refund rule is decided** — 15 000 so'm kept, the rest refunded within ten days (§17 #187) — and stated in the terms, on the delivery page and on the order page of every branch order, where the customer checks their index. The three-week reminder this row once promised is **not built**: it needs to know when the parcel reached the branch (§18 #35) |
| 26 | The region/district dataset is copied from a licensed compilation | Low likelihood, high consequence | `data/regions.csv` is built from the official SOATO / MHOBT classifier; the GitHub compilations (one GPL-3.0, two unlicensed) are used only to cross-check (§17 #90) |

---

## 13. Execution order and sequencing rationale

**Execution order:**

```
0 → 1a → 2 → 3 → 4 → 5 → 6 → 12 → 7 → 8 → 9 → 1b → 10 → 11 → 13
```

**Phase 1b (deployment) runs after Phase 9 and before Phase 10 (§17 #238, amending #36).** #36 had
moved it to just before launch, on the argument that a domain move has external lead times, that
there is no domain move any more (§17 #35), and that an idle VPS is rent paid for nothing. Two of
those still hold; the third has expired — the server was bought on 2026-09-12 (§19 Q15, Q31) and is
being paid for whether or not anything is on it. What tipped it is that **Phase 10 cannot finish
without a server**: its nightly `pg_dump` and verified restore, its off-server and `media/` backups,
its log rotation, its uptime monitoring and its "rate limiter correct across gunicorn workers" are
all server work, so half of Phase 10's Definition of Done was unreachable in its own slot. Deploying
first also puts Phase 10's hardening against the thing that will actually serve the site, which is
the argument §17 #236 already made for measuring Phase 9 that way. 1b still runs before Phase 11,
whose live payment tests and 72-hour watch need a live site.

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
| 4 Data model | ▌ Medium | Tags, reviews, cart changes. Shipped a `PickupPoint` table that §17 #84 then retired — the replacement reference tables land in Phase 6d |
| 5 Frontend rebuild | █ **Largest** | Eleven page groups × six breakpoints × three languages |
| 6 Features | ▊ Large | Size guide, likes, share, search, the delivery redesign, the Google map, Telegram, anonymous cart. **Lighter than it was**: the branch picker, the thousands of rows behind it and its two open questions are gone (§17 #84) — but it now also carries the migration that retires what Phase 4 built. Delivered as sub-phases 6a–6h |
| 12 Reviews | ▌ Medium | Submission, moderation, display, photo handling, SEO |
| 7 Admin panel | ▊ Large | A second interface; product creation and moderation are both substantial |
| 8 Legal & content | ▌ Medium | Three documents × three languages |
| 9 Perf / SEO / a11y | ✅ Done | Image pipeline was the bulk, as expected |
| 10 Testing | ▋ Medium–Large | **685 tests before it starts (2026-09-18).** Runs after Phase 1b as of §17 #238, so its ops items have a server |
| 11 Launch | ▎ Small–Medium | Gated by photography and catalogue entry |
| 13 Recommendations | ▎ Small | One cached query — the thinking is done in this plan |

**Phases 2, 5 and 6 decide whether this project succeeds.** Everything else is supporting work.
Phase 6 grew enough that it was delivered as sub-phases, 6a to 6h.

---

## 15. Progress tracker

| Phase | Status | Branch | Started | Finished | Notes |
|---|---|---|---|---|---|
| 0 Stabilise | ✅ Done | `phase-0-stabilise` | 2026-09-08 | 2026-09-08 | Items 7 and 9 moved to Phase 1b (new VPS) |
| 1a Rebrand | ✅ Done | `phase-1-rebrand` | 2026-09-09 | 2026-09-09 | Mark, icons, OG, all copy, canonical contacts |
| 1b Deployment | 🟨 In progress | `phase-1b-deploy` | 2026-09-18 | — | **Moved ahead of Phase 10 (§17 #238).** Target box **57.128.240.51** (OVHcloud, Ubuntu 24.04.4, 4 GB, 38 GB free, passwordless sudo) — reachable by key since Kamronbek authorised it. It serves valleymade.uz today, so GRAPHIX goes up beside it (§17 #241). Redis is **not** installed there yet; PostgreSQL is 16, Python 3.12.3. **Done so far:** every deploy artefact written and the backup pair proved against a real database; the repository flattened (§17 #242), documented and put under CI (§17 #244). **Waiting on Kamronbek:** the A record for graphix.uz at Eskiz (it still points at 45.138.159.4), and the credentials |
| 2 Design system | ✅ Done | `phase-2-design` | 2026-09-09 | 2026-09-09 | Round one rejected, round two signed off. Tokens, fonts, base, components, style guide, icons, lockups all shipped. Item 10's measurement carried to Phase 5 |
| 3 i18n foundation | ✅ Done | `phase-3-i18n` | 2026-09-09 | 2026-09-09 | Machinery + 25 Python strings in 3 languages. Template copy moves to Phase 5, per page (§17 #50) |
| 4 Data model | ✅ Done | `phase-4-models`, `phase-4-verify` | 2026-09-10 | 2026-09-10 | DoD met, 68 tests. Verification pass fixed two silent defects (§17 #59, #60). Item 11 (size charts) carried to Phase 6 — blocked on §19 Q9. `data/pickup_points.csv` shipped header-only, and §17 #84 then retired the whole branch table — Phase 6d replaces it with `Region`/`District` |
| 5 Frontend rebuild | ✅ Done | `phase-5-frontend`, `phase-5-polish` | 2026-09-10 | 2026-09-12 | All 11 items. `main.css` and the legacy shim deleted. 25 templates on the design system, 221 strings in 3 languages. Defects found by verification rather than review at every step: four in the first pass (§17 #63, #64), seventeen in the browser re-check (§17 #67–#73), five when Kamronbek ran it himself — including two page layouts flattened to one column (§17 #74–#77). **Gate review 2026-09-12 (§17 #79–#82):** DoD met after fixing twenty user-facing Python strings that bypassed gettext, deleting two superseded CSS sections, and restoring this file from a stale write that had silently reverted it to v1.5. Four checklist items moved to the phase that can honestly meet them. 70 tests |
| 6 Features | ✅ Done | `phase-6-features` | 2026-09-13 | 2026-09-13 | All seven sub-phases. `data/regions.csv` built from the official SOATO classifier and checked mechanically; `PickupPoint` retired in one migration with a guard. Cash is kept and switched off rather than deleted (§17 #99, amending #94). Three defects found by driving the pages rather than reading them (§17 #101, #102, #105). **6h (2026-09-13) added region and district to home delivery, wired the Maps key, and re-verified the whole site in a real browser** — eight more defects (§17 #107–#114), 147 tests. **6i (2026-09-14) made the dropped pin fill the region, district and street, and fixed a language switcher that had been one-way since Phase 3** (§17 #115–#120), 157 tests |
| 12 Reviews | ✅ Done | `phase-12-reviews`, `phase-12-recheck` | 2026-09-14 | 2026-09-14 | All eight items but the SMS link, which is blocked on Eskiz body moderation (§17 #104) — the account area carries the entry points instead. Eligibility, moderation, EXIF-stripped photos, the distribution, the lightbox and the JSON-LD. Six defects in the build pass (§17 #122–#128), **twelve more in the recheck that followed** — a plural that read wrong in two languages, a wrong Uzbek letter inherited from three earlier phases, a text limit that lived only in HTML, a decompression bomb the size check could not see, a form that threw away what the customer typed, the only unrated write endpoint on the site, a notification that could not see its own photographs, an unconstrained rating column, the plan file destroyed a second time, a Russian date in the wrong case, a browser-default box around the rating, and an anchor that hid its own heading under the header (§17 #129–#140). The last three were found by photographing the pages and looking at them, not by any assertion. **226 tests** |
| 7 Admin panel | ✅ Done | `phase-7-panel` | 2026-09-14 | 2026-09-14 | **7a done:** a `panel` app at `/boshqaruv/`, its own guard (a signed-in customer gets 403, not a second login form), a mobile-first shell on the site's own tokens, the dashboard, and the orders list and detail with filters, search, an inline status change and the audit trail. **The panel may assume JavaScript** — Kamronbek's decision, §17 #141, and the one place on the project where that is true. New: `panel.OrderStatusChange` (§17 #142) and `core.Msg.is_read`. **7b done:** the catalogue list with availability, price and per-size stock editable in place, and the create/edit screen — three languages, specs, tags, the size × stock grid, and a gallery that uploads through the same pipeline as a customer's review photo, checks the file before sending it, and reorders by drag. The DoD's "a complete product in one sitting" is a test. **7c–7e done:** the moderation queue (photographs shown at a size somebody can judge, approval through the service that moves the rating), the contact inbox with read/unread and a tap-to-call number, and the reference screens — delivery tiers, tags and size charts on one page, regions and their two hundred districts on another with a search. Five models edit through **one endpoint behind an allowlist** (§17 #149). **All ten items; 317 tests.** Rechecked and corrected four times since, at Kamronbek's request: fourteen defects the phase's own tests could not see (v2.12), ten corrections he found by using the panel (v2.13), four from the settings screen (v2.14), and five more from the dashboard and the account screens — the wording, the low-stock rule and the size pills (v2.15). **424 tests** |
| 8 Legal & content | ✅ Done | `phase-8-content` | 2026-09-15 | 2026-09-16 | All seven items. Three documents × three languages as nine whole-text templates in one shared page (§17 #182), every figure read from the code that enforces it (§17 #183), the seller named without tax or bank details (§17 #184). Q11, Q12, Q22 and Q26 answered and built or scheduled (§17 #185–#189). **Found on the way:** the checkout threw away the name it asked for — fixed first, on its own branch (§17 #190); every home order called its address a post office (§17 #191); the fuzzy-entry test could not see a wrapped msgid (§17 #198); the suite's language leak surfaced in a Phase 7 test while a single failure under `--parallel` took the whole run down (§17 #199); and driving the pages found a Russian title wider than a phone (§17 #202) and a consent link whose tap opened the other document (§17 #203), and a range the dash split across two lines (§17 #204). **486 tests**. **Rechecked 2026-09-16** on `phase-8-recheck`: Q27–Q29 and Q31 answered and built, the Telegram bot relay, and six fixes the first pass missed (§17 #205–#214). **525 tests** |
| 9 Perf / SEO / a11y | ✅ Done | `phase-9-quality` | 2026-09-17 | 2026-09-17 | All nineteen items, **measured rather than asserted**: Lighthouse mobile **98–99** on home, shop, product, cart and checkout, accessibility **100**, LCP ≤ 2.3 s, CLS 0, and **zero axe-core violations** over ten pages at two widths — all against a production-shaped server (hashed static files, DEBUG off, compression and cache headers), because measuring `runserver` measures something the visitor never gets (§17 #236). WebP renditions at 400/800/1600 built on commit and backfilled by a command (§17 #230); hashed static filenames (§17 #231); canonicals, path-only alternates and `noindex` on every private page (§17 #232); one `@graph` per page, with the `offers` Search Console was going to warn about (§17 #233). Kamronbek's three answers built: the address is in the offer and nowhere else (§17 #226), a product needs a tag (§17 #228), and Q34 is a deploy step rather than a code change (§17 #227). Eight backlog items closed — §18 #14, #22, #24, #27, #31, #34, #36, #37 — and the measured run found two defects no test and no sweep had: a closed drawer still in the tab order, and a heart whose name left out the number printed inside it |
| 10 Testing | 🟨 Opened | `phase-10-tests` | 2026-09-18 | — | Branch cut and audited 2026-09-18; the work follows Phase 1b (§17 #238). **Audit:** `check --deploy` is already clean with `DEBUG=False` but nothing asserts it · **no §6 smoke matrix exists** — `SmokeTests` is still Phase 0's four · **no CSP at all**, to be built as a nonce middleware (§17 #239) · 703 files left in `vm/media/` by the suite, up from 575 the day §18 #42 was written · backlog #32, #41 and #42 still open here |
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
| 2026-09-09 | Task | 2 | v1.7: **round one rejected, round two built.** Kamronbek: type "thin and sharp, looks like hand made cheap", desktop "nothing" with wrong metrics, wants dark-but-not-black. Root causes found and recorded (§17 #44): the shortlist came from one type register, and the desktop page had an uncapped image height plus a 900 px breakpoint — a bug shipped as a design. Screened 35 editorial/fashion faces; **Playfair Display** is the only premium display serif that contains U+02BB. Rebuilt as one dark direction — warm charcoal layers, brass accent, Playfair + Onest 500 min — covering product page **and** shop, verified by screenshot at 390 px and 1280 px before publishing | Sign-off on the design, then tokens and components |
| 2026-09-09 | Task | 2 | v1.8: **Phase 2 complete.** Design signed off, then built into the real system: `tokens.css` (every foreground token contrast-checked against all four grounds — lowest 3.34:1 on a decorative token), `base.css`, `components.css` (22 blocks, the full §8 inventory), 28-symbol inline icon sprite, and the living style guide at `/boshqaruv/style/` (staff-only, verified 302/302/200). Fonts subset and self-hosted as variable WOFF2 — Playfair 293→56 KB, Onest 188→54 KB — killing the third-party `rsms.me` request. Wordmark lockups outlined from Playfair. **CSS 8.5 KB gzipped against a 60 KB budget.** New system deliberately loads only on the style guide until Phase 5, so it cannot collide with `main.css` (§17 #48) | Phase 3 — i18n foundation |
| 2026-09-09 | Task | 3 | v1.9: **Phase 3 complete.** uz unprefixed, `/ru/` and `/en/` prefixed; `LocaleMiddleware`, `set_language` + footer switcher, `hreflang` + `x-default`, trilingual sitemap (21 urls, 84 alternates). **The Click webhook moved into its own `webhook_urlpatterns` list outside `i18n_patterns`, with five tests asserting it never moves** — risk #2 is where the failure is silent. `tfield` + `\|t` filter with blank-translation fallback, `product.0009_i18n_fields`, admin grouped one fieldset per language. 25 Python-side strings written in ru and en and compiled. Template copy moved to Phase 5 per page (§17 #50). 23 tests pass | Phase 4 — data model |
| 2026-09-10 | Task | 4 | v1.11: **Phase 4 complete.** Every §7 schema change landed across three apps in eight migrations, with the three-step pattern — add nullable, backfill, tighten — so no migration ever invents a value. New: `Tag`, `SizeChart` + `SizeChartRow`, `ProductLike`, `Review` + `ReviewImage`, `DeliveryOption`, `PickupPoint`. `Product` gained slug, tags, `is_active`, the denorm counters and the spec strip; `Variant` gained `stock` + `is_purchasable`; `Cart` went nullable-user with `session_key` and two partial unique constraints. Product detail moved to `/mahsulot/<slug>/` with a 301 at `/item/<pk>/` and every call site — sitemap, shop grid, related strip, cart and order-detail links, both `cart_add` redirects — moved with it. Stock wired end to end: `add_variant` caps at `min(99, stock)` on the existing `Least`/`F` expression, payment decrements inside the existing transaction, `cancel_paid_order` restores. `seed_pickup_points` validates the whole CSV before writing and refuses coordinates outside Uzbekistan; **the shipped CSV is header-only — the real dataset is Q3/Q4 and inventing branches would misroute real parcels.** Admin registers the new models with slug prepopulation and review moderation, and assigns the default colour itself so the owner never meets a picker the storefront doesn't render; the full admin pass stays Phase 7. `core/test_phase4.py` holds the DoD as assertions — **60 tests pass, `makemigrations --check` clean.** Item 11 (size charts) carried to Phase 6, blocked on Q9 | Phase 5 — frontend rebuild |
| 2026-09-10 | Task | 4 | v1.12: **verification pass after a dropped connection — and it found two real defects, neither of them from the disconnection.** (1) **Every page on the site was rendering a developer comment as text.** Django's `{# #}` is single-line; a comment spanning lines falls through the lexer as literal output. `base.html` and `_footer.html` each had one, the footer's inside `<body>` as visible text; `style.html` and `_icons.svg.html` too. Proved by rendering — the home page lost 408 bytes once fixed (§17 #59). (2) **Thirteen Phase 4 labels were marked for translation and never extracted**, so `Product.Fit`, `Tag.Kind`, `Review.Status`, `PrintMethod` and the two `Order.clean()` messages rendered Uzbek under `/ru/` and `/en/`. Written by hand in all three languages (§17 #60). Both are the silent kind: a wrong page, not an exception. Each now has a test that fails on the class of mistake, not just the instance — `core/test_templates.py` walks every template, and `CatalogueCompletenessTests` fails on any untranslated or drifted catalogue entry. **Also replayed the Phase 4 migrations in an isolated scratch database seeded with legacy-looking rows** — duplicate names, an unsluggable name, orders across two days — because the dev database has no orders and `payment.0011` had therefore never run against a non-empty table; slugs, the `-2` suffix, the `mahsulot-<pk>` fallback, the stock backfill and the per-day numbering all came out right, and the stack reversed and re-applied with no duplicate seed rows. Git, file integrity (110 Python files, 49 text files), every URL in three languages, the 301, all twenty admin screens and the webhook's unprefixed path all verified clean. **68 tests pass** | Phase 5 — frontend rebuild |
| 2026-09-10 | Task | 5 | v1.13: **Phase 5 items 1–3 built** — the shell, the product page and the shop, the first pages on the design system. Scope and two boundaries agreed with Kamronbek first: a legacy base keeps un-rebuilt pages styled (§17 #61), and Phase 5 renders markup while Phase 6 wires behaviour (§17 #62). Shell: sticky header with brand mark, global search, heart and cart badges, focus-managing drawer, skip link, and the icon sprite finally included. Product page: two columns from 860 px, sticky gallery, vertical rail from 1024 px, image capped at `min(76vh, 760px)` per #47, real out-of-stock size states, spec strip, delivery lines, related strip, mobile buy bar, rating hidden until the first approved review. Shop: one filter markup that is a sidebar on desktop and a bottom sheet on mobile, tag filters wired through the view, sort, pagination, real empty state, shared card partial. All progressive enhancement — drawer, search, quantity and filters work with JS off. **63 strings written by hand in three languages.** Verified by screenshot at 360/390/768/1024/1440/1920 in uz, ru and en: no horizontal scroll, no failed image, no `style` attribute in any new template. **Three defects found by that verification, not by review:** the PDP scrolled sideways at 390 (the quantity stack stretched and pushed the actions 43 px off-screen); the quantity input rendered as a white bar (`.stepper__val` was written for a `<span>` in the Phase 2 style guide); and **four strings shipped as fuzzy catalogue entries, rendering Uzbek under `/ru/` and `/en/` — including the add-to-cart button** (§17 #63). 69 tests pass | **Kamronbek reviews items 1–3**, then items 4–11 |
| 2026-09-10 | Task | 5 | v1.14: **Phase 5 complete.** Items 4–11 rebuilt — home, search at `/qidiruv/`, saved designs at `/saqlanganlar/`, cart, the six auth pages, three account pages, checkout, payment, order detail and status, about, contact, delivery, a standalone size guide, terms, and 404/403/500. **`main.css`, `legacy.js`, `base_legacy.html` and both legacy partials deleted** with `git rm` — that deletion is the DoD (§17 #61). All 25 templates now extend one `base.html` and the design system is the only stylesheet on the site. Search reuses the shop's query and template rather than reimplementing either. The OTP cell field and signup draft were *ported* to `auth.js` unchanged — the OTP flow is on the never-break list, so a move, not a rewrite. **201 strings now written by hand in three languages.** Verified: **306 breakpoint checks** (51 pages × 6 widths) with no horizontal scroll, no failed image and no unfocusable control. **Four more defects found by verification, not review:** `terms.html` used single quotes in its `extends` so the repoint script missed it and it had been sitting unstyled on the new shell; its section 3 still described Yandex, BTS and a free-delivery threshold, all superseded by locked decision #12; the OTP resend label was a hardcoded Uzbek string in JavaScript that reverted to Uzbek under `/ru/` and `/en/`; and **the home hero pushed the first product card 108 px below the fold at 390 × 844, breaking locked decision #29** (§17 #64). 69 tests pass | Phase 6 — features |
| 2026-09-10 | Task | 5 | v1.15: **Phase 5 closed out.** The contact page's 21 px horizontal scroll at 360 px took two attempts, and the first one is the lesson: `overflow-wrap: break-word` stops the visual overflow but does **not** reduce an element's min-content width, and min-content is exactly what a grid column sizes to — so the page still scrolled. `anywhere` plus an explicit `minmax(0, 1fr)` on the six single-column mobile grids fixed it (§17 #65). **306 breakpoint checks now clean, and the fold check passes in all three languages.** Also cleared the last two Phase 5 debts: the four `CartError` messages in `cart/services.py` are wrapped in `gettext` with their Uzbek spelling corrected to U+02BB, written in Russian and English by hand (§18 #11 done) — and `makemessages` guessed one of them fuzzy from `Nimadir notoʻgʻri ketdi`, so the #63 defect tried to recur within a day of the test being written; the test caught it. `vm/core/forms.py` deleted, since Phase 5 built the contact form as markup against the existing view and nothing ever imported the file (§18 #13 closed). §19 Q6, Q7 and Q16 were all marked “needed by Phase 5” and are still unanswered; retargeted to the phase that actually next needs them — **Kamronbek to confirm those three retargets.** Finally, the review pass caught that **the three error templates had never been rendered** — the sweep had been checking Django’s debug 404 — and rendering them properly exposed a defect in the footer on a real 500 (§17 #66). **342 breakpoint checks clean across 57 pages.** 69 tests pass | Phase 6 — features |
| 2026-09-11 | Task | 5 | v1.16: **polish pass on branch `phase-5-polish`, driven by rendering rather than by reading.** Kamronbek answered the four open questions (fit range, tag taxonomy, social handles, size guide) and asked for every page to be re-checked in a real browser. Two harnesses now do that: `.git/audit.py` asks fourteen questions of every page at every breakpoint in all three languages — clipped text, escaped elements, unlabelled controls, heading order, duplicate ids, contrast, and **tap targets measured by hit-testing rather than by the element’s own box** — and `.git/interact.py` *operates* the drawer, search, filter sheet, stepper, gallery and size picker with real clicks and Tab presses, then asserts on what the page became. Both serve the pages over HTTP, because on `file://` the woff2 faces are blocked by CORS and every screenshot was being judged in fallback fonts. **They found twenty-four defects, almost none of which reading the source would have shown**, among them: an open drawer let Tab walk out onto links behind it; the filter sheet never took focus and never gave it back; every text field on the site lost its focus ring to an `outline: none`; the stepper’s minus at quantity 1 looked live and did nothing; `.nav__actions button` out-specified three `display: none` rules, so the burger and a redundant search icon sat on desktop and a fifth icon sat on mobile — which is also what pushed the header onto two rows and dropped the first product card below the fold once the icons grew to 44 px; the footer was indented past every other block because it set `--pad-x` on top of the `.wrap` that already had it; the header sat 80 px left of the page’s own left edge at 1440; and the delivery rows put their icon on a line of its own because the reset makes every `svg` a block. **342 breakpoint checks and every interaction check now pass**, the fold check passes in all three languages, and 69 tests pass. Decisions §17 #67–#73 | Kamronbek reviews, then Phase 6 |
| 2026-09-12 | Task | 5 | v1.17: **Kamronbek ran the site himself and found what no harness had been asked to check: whether a page has the layout it is supposed to have.** One rule caused most of it — a shared `grid-template-columns: minmax(0, 1fr)` written *after* the breakpoints that set the real columns. A media query adds no specificity, so it won everywhere, and **the product page and the shop had a single column on every screen since the 360 px overflow fix** (§17 #74). On the product page that put the buy column under a gallery whose image was sticky, so the photograph slid down over the title as he scrolled; on the shop it stacked the filters above the grid. Fixed, and now measured: `interact.py` asserts the column counts, that the buy column sits *beside* the gallery, and that the gallery never overlaps it at any scroll position. Also from his list: **the image frame no longer takes any size from the photograph inside it** (§17 #75) — proved by swapping in 3000×500, 500×3000 and 900×900 sources and measuring the box; **the shop is a sticky sidebar plus an independently scrolling results column** (§17 #76), which needed a wrapper, because a stretched grid item fills its own grid area and a sticky box with no room in its containing block cannot move at all — and the sidebar’s `top` had never applied anyway, reset by an `inset: auto` written after it; **the mobile hero is type and two buttons**, no photograph, with the supporting line under them (§17 #77) — the first product card is now 283 px above the fold instead of 36; **the mobile filter sheet comes down from the top** with a backdrop that dims the page and dismisses on tap; and the account logout is a bordered button rather than a ghost that read as one more link. 342 breakpoint checks, every interaction check and 69 tests pass | Kamronbek reviews |
| 2026-09-12 | Task | 5 | v1.18: **the eight review designs are now the local database, seeded by `manage.py seed_demo_catalogue`.** They had only ever existed inside a throwaway test database that `.git/render_all.py` built and destroyed, so every screenshot and every breakpoint sweep was measured against a catalogue no developer ever actually saw — which is exactly how a single-column product page survived for days: nobody had a page in front of them with four photographs and four sizes on it. The command is destructive by design and says so before it acts: it replaces products, images, variants, categories and sizes, and the carts and orders that hang off them, while keeping user accounts, delivery options, pickup points and contact messages. It refuses any `DB_HOST` that is not local. The photographs live in `docs/design/demo-catalogue/` because `vm/media/` is gitignored, and are copied into place when missing, so a fresh clone needs nothing but the command — verified by deleting them and running it again. Kamronbek’s three scratch products, two categories and one test order are gone at his request; a `pg_dump` of the old database is in `.git/dbbackup/` anyway. 69 tests pass | Phase 6 |
| 2026-09-12 | Task | 5 | v1.19: **gate review before Phase 6 — "is everything actually ready?" answered by measuring rather than by reading the tracker.** Three findings mattered. (1) **This file had been silently reverted to v1.5.** The working copy was 1 697 lines of plan at v1.18 in git and 1 572 lines at v1.5 on disk — every decision from #23 on, every session row past Phase 1, the whole Phase 2–5 record, gone from the file the next chat would read, with `git status` showing one unremarkable modified file. §18 #17 again, on the one file the project cannot afford to lose; restored from `HEAD` and now version-asserted by any script that writes it (§17 #82). (2) **Twenty user-facing Python strings had never been marked for translation** — the add-to-cart and remove confirmations, every OTP and password-reset message, signup and login, order cancellation, the "number already registered" error. A Russian visitor got Uzbek at each of those moments. Wrapped, written by hand in Russian and English, and **`makemessages` guessed thirteen of them fuzzy**, so §17 #63 tried to recur one more time — and the test written to catch that class of defect did not, because it matched a bare `#, fuzzy` and gettext writes `#, fuzzy, python-format` when the string has a placeholder. Both the test and `.git/po_tool.py` now read the flag line properly, and a new `ast`-based test fails on any `messages.*` or `add_error` literal that bypasses gettext (§17 #80). (3) **Four checklist items could not honestly be ticked and were moved, not ticked**: gallery pinch-zoom and skeleton loading to Phase 6, `srcset` to Phase 9, Lighthouse to Phase 9 — and Phase 5 item 6 claimed an anonymous cart that Phase 6g actually owns (§17 #79). Also: two whole CSS sections deleted that nothing had used since Phase 2 (`.gallery__*`, `.hero__*` — superseded by `.pdp__*` and `.home__hero*`), three hand-written page scrims collapsed into one `--c-scrim` token, and the last class used in markup with no rule behind it removed. **Measured, not assumed: CSS 17.8 KB and JS 7.5 KB gzipped against 60 and 30; `audit.py` 0 findings across 57 pages × 6 widths × 3 languages; every `interact.py` check; the fold check in all three languages; `makemigrations --check` clean; 70 tests.** | Phase 6 — start with 6b, 6c, 6g and 6a's viewer |
| 2026-09-12 | Task | 5 | v2.0: **the plan had forked, and this is the merge.** Kamronbek asked where the delivery redesign and the Google Maps decision had gone. They were in a *second* version of this file: a planning chat had taken v1.3 and amended it into its own v1.4 and v1.5 — **map provider Google, `PickupPoint` dropped for region + district + a typed postal index, home delivery 40 000, postal-index prefix validation** — while the task chats carried the same file from v1.6 to v1.19. Both wrote `docs/PLAN.md`, so the last writer won; and because both numbered new decisions from #23, **the same number meant two different things** in the two copies. During the v1.19 gate review I read the planning file's lower version number as a stale revert and ran `git checkout` over it. That was my error and the file is not recoverable: PyCharm's local history holds the path but not the content, and no copy survived on disk or in the project. **Its decisions were rebuilt from this session's own transcript**, which had captured the parts of it I read — §3, §7's delivery table, Phase 5, Phase 6a/6d, Phase 10's payment tests, §12 risk #6, §14, §15, §16, §17 #1–#22 and #37, §19 Q5 — and folded in here as **#83–#88**, renumbered into this line's sequence because a cross-reference has to resolve to one thing forever (#89). The reconstruction is faithful on the decisions and their reasoning; **the `Region`/`District` field list in §7 is mine and should be checked against the planning chat before 6d builds it.** The redesign is also the best news in the plan: it **closes Q3 and Q4**, which were the hardest blockers in the project — there is no Uzpost branch dataset to obtain any more, because the customer types the one field we could never get. Code debt recorded rather than done: the seeded home price is still 30 000 in six places (§18 #18), and `PickupPoint` and its loader are retired by 6d's migration. §0 now carries the four rules that stop this happening twice | Phase 6 — 6b, 6c, 6g, 6a's viewer; 6d once there is a Maps key and a verified `regions.csv` |
| 2026-09-12 | Task | 5 | v2.1: **Kamronbek supplied the planning chat's own messages, and they correct the v2.0 reconstruction in eight places.** The diagram is his, restored verbatim. `District.kind` is `district` | `city`, not `tuman` | `shahar`, and the drawer groups them under *Tumanlar* / *Shaharlar* because someone in Angren is looking for a city. `postal_prefix` is **2 or 3 digits** — Toshkent shahri is `100` — so the check is `startswith()`, not a fixed slice; v2.0 had it as a 2-char field, which would have rejected every valid Tashkent index. The `Boshqa` escape is on **both** drawers with free text, not one region row. The drawer's search appears only above ~15 entries. **Changing the region clears the district** — v2.0 missed it, and without it a stale district submits silently as a plausible wrong address. Added from his research: the index-to-region prefix table and its sources; the link out to `uz.post/uz/map` for a customer who does not know their index, in a new tab with the form saved to `sessionStorage` (#92); the address field staying required even with a pin (#91); the licence caution on the three public SOATO compilations — one GPL-3.0, two unlicensed — so `data/regions.csv` is built from the classifier itself (#90); Google's 1 March 2025 switch from the $200 credit to 10 000 free Essentials events a month, with a card still required for a key; and the legal answer on uncollected parcels — **Resolution 2219 §5: one month, a second notice, then return at the sender's expense, and the sender is us** — which turns Q11 into a refund decision that has to be made before the first case, plus two cheap mitigations and risk #25. Uzpost's partner programme is now Q24 with its phone number | Phase 6 |
| 2026-09-12 | Task | 5 | v2.2: **ten open questions and four backlog items answered — plan only, nothing built, and nothing scheduled inside a closed phase.** The two that change scope: **there is no cash, anywhere** — online payment only for the goods and the delivery, so 6e deletes the disabled "Naqd pul" control, the checkout rejects any non-Click method, and cash joins §11 (§17 #94); and **we draw the size charts ourselves** rather than waiting for the owner's, which unblocks Q9 and Phase 4's carried item 11 (§17 #95). The pattern behind two more: **every external credential ships as a blank `.env` variable with the feature fully built around it** (§17 #93) — the Google Maps key and the Telegram token are written as though set, and an empty value takes the degraded path the plan already required, so turning them on later is a paste into the server `.env` rather than a deploy. Confirmed: **40 000 nationwide** (Q5 closed; the cost question stays as risk #6), **Uzpost only, no BTS** (Q14), **the Eskiz GRAPHIX sender is approved** (Q17 — the residual body-moderation check moves into Phase 1b item 10), and **the VPS is bought** (Q15), which takes Phase 1b from ⛔ to ⬜ while leaving it in its §13 slot after Phase 10. Assigned to us rather than to Kamronbek: **verifying `data/regions.csv`** (Q23) and **looking up Uzpost's delivery timeframes** (Q10). Backlog #4, #5 and #9 are scheduled — `django-environ` and the `Kamron's` branch into Phase 10's new repository-hygiene block, the repository rename into Phase 11 beside the package rename — and #6 is closed as already the practice. **Six open questions left: Q8, Q11, Q12, Q19, Q22, Q24**, none of which block Phase 6 | Phase 6 |
| 2026-09-13 | Task | 6 | v2.3: **Phase 6 built, all seven sub-phases.** **6b** one heart that saves and counts together, in a transaction with an `F()` expression, guarded against going below zero, rate limited, `next` checked so it is not an open redirect — a real form first and a fetch second, so it works with JavaScript off. Ommabop and Reyting sorts, and share via `navigator.share` with a copy-link/Telegram menu where that does not exist. **6c** search now matches every language of every searchable field; it had been matching the Uzbek columns only, which made the other two decorative. **6g** guests get a session-keyed cart, merged on login *and* signup by reading the session key **before** Django cycles it, both carts locked, quantities summed and capped at stock, and a new line keeps the price the guest was shown. The deletion guard now lives in one place and both callers use it — the middleware had its own unguarded copy, which is the second half of risk #4 nobody had noticed. **6a** the charts are drawn rather than waited for: authored as HTML against the real tokens and the real self-hosted faces and rendered by a headless browser, because the brand faces ship as subsetted WOFF2 and Pillow cannot read one. `SizeChart.fit` makes them resolve without the owner linking anything (#96). **6d/6e** the branch table is gone; `data/regions.csv` is built from **stat.uz's own SOATO classifier** by a script and verified mechanically — counts against the classifier's totals, unique codes, no ASCII apostrophes, no mixed scripts, every prefix 2–3 digits and unique, and no prefix that is a prefix of another. `Order.clean` is the one validator and the view asks it. Home delivery is 40 000 and the product and delivery pages now render the figures from the rows (§18 #18 closed). **6f** `core/telegram.py` in `core/sms.py`'s shape, every send on `transaction.on_commit`, four events, credentials blank. 55 strings written by hand in three languages; gettext guessed 17 and marked them fuzzy, which the §17 #63 test caught. **Three defects only rendering found** (§17 #101, #102, #105 — the last one is §17 #72's pattern for the third time), and **an Eskiz rejection that matters more than any of them** (§17 #104). **141 tests, `check` clean, `makemigrations --check` clean**, and a real branch order placed through the form end to end | Phase 12 — reviews |
| 2026-09-13 | Task | 6 | v2.4: **Phase 6h — home delivery gets the same two drawers, the Maps key goes in, and the whole site is driven in a real browser rather than looked at.** Kamronbek supplied a Google Maps key and three instructions. **Region and district now belong to both methods** (§17 #106): one shared block of drawers, then either a six-digit index or a street and a house — so the courier half stops asking a customer to type a province into a free-text box, and `location_snapshot` reads the same shape either way. **The key is in `vm/.env`** and the map renders; the admin's order page now draws the dropped pin as a picture rather than printing two decimals at the owner (§17 #108). **The single-image product page was the headline bug and it was Kamronbek who spotted it**: a gallery grid that assumed a thumbnail rail the template omits, so seven of the eight products rendered their photograph 64 px wide (§17 #109). Then the verification pass, and it is the reason this row is long: **two of the tools were lying.** Django 6 caches templates even under `DEBUG=True`, and with `--noreload` the browser was being shown pages that had already been fixed; and four stray `runserver` processes were alive, the oldest holding the port, so a context processor that worked in the shell rendered nothing in the page. `.git/serve.py` now starts and stops the server for every sweep (§17 #112). What the honest sweep then found: **the footer quoted the old 30 000 delivery price on every page of the site**, and the terms page did too *and* promised cash on delivery, which has been off since #99 — both now read from the rows (§17 #111); **both halves of the delivery form were `hidden` in the markup**, so with JavaScript blocked the checkout had no fields at all (§17 #107); a tap target derived from text size (§17 #110); an admin script running before its own element existed (§17 #113); and an admin map that passed every assertion while being **zero pixels wide**, caught only by looking at the picture (§17 #114). New harnesses, in their own venv outside the repo because requirements.txt is locked: `audit_live.py` (20 pages × 5 widths × 3 languages, **0 findings, 0 console errors**) and `interact_live.py` (**31 checks, 0 failed** — drawers, search, the index's inline check, the map, a real order placed with a pin, the admin map). **147 tests, `check` clean, `makemigrations --check` clean.** Outstanding and only Kamronbek can do it: **billing on the Google project** — the map works but Geocoding answers `REQUEST_DENIED`, so a pin cannot fill the address field — and an HTTP-referrer restriction on the key (§19 Q1) | Phase 12 — reviews |
| 2026-09-14 | Task | 6 | v2.5: **Phase 6i — three things Kamronbek found by using the site.** **(1) The language switcher had been one-way since it was built.** From any Russian or English page every button reloaded the same page in the same language, and nothing in four phases of tests had noticed, because the control had only ever been rendered and never operated. The cause is a Django 5.1 change meeting `prefix_default_language=False`: `LocaleMiddleware` forces the default language on any unprefixed path, `/i18n/setlang/` is unprefixed, so `set_language` always runs in Uzbek and `translate_url` cannot resolve a `/ru/` path to translate it. Each button now posts its own already-translated URL, which the context processor computes correctly because it runs where the active language matches the path (§17 #115). The mobile drawer had its own copy of the control and its own copy of the bug. Kamronbek also asked whether Uzbek should take a `/uz/` prefix; it would fix this a second way, and it is a §3 locked decision, so it is **§19 Q25 for him to decide** rather than something to change quietly. **(2) A dropped pin now fills the region, the district and the street**, each still editable — amending #91, which was written when the address was one free-text field (§17 #117). Every row ships all three of its spellings so a pin can be matched whatever Google calls the place (§17 #116), and where two rows match one name — Toshkent shahri against Toshkent viloyati, Samarqand tumani against Samarqand shahri — the collision is broken on evidence or the field is left empty, never guessed (§17 #120). Verified against the exact component shapes Google returns, with the geocoder stubbed, because billing is still off. **(3) The map did not come back when the form was re-rendered after a validation error** — the pin survived as two invisible numbers (§17 #118) — and, found while fixing that, the Maps script was `async`, so on any **second** visit it ran from cache before `map.js` and called a callback that did not exist yet: no map, only for returning visitors (§17 #119). **157 tests**, `audit_live` 0 findings across 20 pages × 5 widths × 3 languages, `interact_live` 31 checks, `probe_pin` 14 checks | Phase 12 — reviews |
| 2026-09-14 | Task | 6 | v2.6: **Uzbek moves to `/uz/` — a §3 locked decision amended on Kamronbek's word** (§19 Q25 → §17 #121). It was locked as "Uzbek unprefixed, best SEO for the primary audience", and what that actually bought was a permanent special case: Django forces the default language on every unprefixed path, which is correct behaviour and is precisely what left the switcher one-way (§17 #115). All three languages are prefixed now, so the rule never fires and `/` is free to send a visitor to their own language. **The cost was paid today rather than after launch** — every Uzbek URL changed shape. An old one still works: it 404s inside `i18n_patterns` and `LocaleMiddleware` redirects it, as a **302 and not a 301**, because the destination depends on who is asking and a cached permanent redirect would pin a visitor to one language for good. The sitemap needed nothing — it was already `i18n=True` with alternates. One test failed and it was the right one: `/item/<pk>/` now takes two hops, language then slug, so it is asserted as both. **160 tests**, `audit_live` 0 findings across 20 pages × 5 widths × 3 languages, `interact_live` 31 checks, `probe_pin` 14, and the switcher driven between all three languages on four pages. Billing on the Maps project stays off until deployment, by Kamronbek's decision — the pin-to-fields work is built and tested behind it | Phase 12 — reviews |
| 2026-09-14 | Task | 12 | v2.7: **Phase 12 built — reviews, ratings and the moderation queue behind them.** Only a customer with a `done` order containing that product may review it, once, and `Review.order` records which order granted the right; every rule is a separate function in `product/services.py` and a separate test. Nothing reaches the site until a staff member approves it, and approval goes through the service rather than the admin's `queryset.update()`, **because a bulk update fires no signals and the product rating would otherwise never move** — `recompute_rating` reads the approved rows back and quantizes with `ROUND_HALF_UP`, since Python's `round()` is banker's rounding and made a genuine 4.25 display as 4.2. Photos are re-encoded rather than scrubbed (`product/images.py`): deleting the EXIF tags you know about leaves the ones you do not, and a phone writes the customer's home coordinates into every picture. The product page gained the summary, the five distribution bars, the cards Phase 2 had built and nothing had used, photos in the existing lightbox, and `aggregateRating` + `Review` JSON-LD parsed in the browser rather than matched in the source — a review is a stranger's text inside a `<script>`. The rating block still does not exist at all on a product with no approved reviews. **The star rating has no JavaScript**: five radios, reversed by CSS, `input:checked ~ label` lighting the ones to its left. 31 strings written by hand in three languages, including the project's **first plural entry**, which promptly exposed that the catalogue-completeness test could not read one (§17 #122) and that the fill script's fuzzy stripper was corrupting `#, fuzzy, python-format` into something msgfmt refuses (§17 #123). **Six defects, and the split is the story: two in the site, four in the tools that were supposed to find them.** The distribution bars were 0 px wide at every breakpoint (§17 #125) and the rating link was a 22 px tap target (§17 #127) — and the second one had never been judged before because the audit had no product with reviews on it, which is now the rule (§17 #127). The harness defects: `.sr-only` text failed a contrast check it should be exempt from (§17 #126), a fixture that was idempotent on creation but not on state (§17 #128), a `Cart.delete()` that cascaded away the order it was meant to preserve (§17 #128), and a test that read Uzbek copy from a page rendered in English because `LocaleMiddleware` leaves the last request's language active (§17 #124). **197 tests, `check` clean, `makemigrations --check` clean, `audit_live` 0 findings across 22 pages × 5 widths × 3 languages, `interact_live` 45 checks, `probe_pin` 14** — the review written, submitted, queued, approved through the real admin and then read back off the product page | Phase 7 — admin panel |
| 2026-09-14 | Task | 12 | v2.8: **Phase 12 rechecked line by line at Kamronbek’s request, and the recheck found more than the build did.** Nine defects, none of which any harness had been asked about. **Two were wrong in front of the customer.** `%(n)s yulduz` was a plain string, so the distribution printed “1 звёзд” and “1 stars” five rows at a time and every star label did the same — a count in a sentence is a plural, and Uzbek not inflecting after a numeral is exactly what hides it from the person writing the copy (§17 #129). And **the Uzbek itself was spelt with the wrong letter**: U+02BB builds oʻ and gʻ, the tutuq belgisi in maʼlumot is U+02BC, and five strings across four files from three phases had the first standing in for the second — Phase 12 acquired it by copying its neighbours, which is how a wrong character spreads (§17 #130). **Three were ways in.** The review textarea’s 2 000-character cap lived only in the HTML, with a bare `TextField` behind it (§17 #131); the photo pipeline bounded the file and not the picture, and a 140 KB PNG that decodes to 432 MB walks past a size check — Pillow does not stop it either, it only *warns* at 89 Mpx (§17 #132); and the review POST was **the only write on the site with no rate limit**, on the one endpoint that accepts four uploads and re-encodes them (§17 #134). **Two were things that quietly did not work.** Every refusal redirected instead of re-rendering, so one photograph too many cost the customer the paragraph they had written — §17 #118 extended from “restore the state” to “never redirect away from a refusal” (§17 #133); and the Telegram notification’s “a photograph is attached” line had never once appeared, because it was composed inside the transaction that creates the review and the photographs are written after it (§17 #135). **One was a missing guarantee**: `rating` had `choices` and no constraint, and that column is the input to a public number (§17 #136). **And one was this file, destroyed for the second time** — not overwritten as in §17 #82 but emptied, because `io.open(path, "w")` truncates before it writes and the encode then failed; recovered from the commit, and plan writes now encode first and rename into place (§17 #137). Also folded in: the distribution now divides by the rows it counted rather than by the denormalised column, `reviewable()` stopped querying the same cart twice, and `ALLOWED` no longer lists two formats this Pillow cannot open. **223 tests** (60 of them Phase 12’s, up from 34) — every Definition-of-Done clause now has an assertion behind it, including the rich-result shape, checked against Google’s documented requirements rather than against our own. `check` clean, `makemigrations --check` clean, **Then the pages were photographed and looked at, and that found three more that no assertion would ever have caught.** The date under every Russian review read “14 Сентябрь 2026”, the nominative, where Russian dates take the genitive — `E`, not `F` (§17 #138). The rating control wore the browser’s **default fieldset box**, because nothing on the site had ever used a `<fieldset>` and so nothing had ever reset one, and its five stars were packed against the right edge, because `inline-flex` does not survive a flex parent (§17 #139). And tapping the rating — the one link the whole section exists for — scrolled its heading **five pixels under the sticky header**, because `scroll-margin-top` was a spacing token rather than the header’s height (§17 #140). The file input, the only control still wearing the browser’s grey button, was restyled at the same time. **226 tests, `check` clean, `makemigrations --check` clean, `audit_live` 0 findings across 22 pages × 5 widths × 3 languages, `interact_live` 47 checks, `probe_pin` 14** | Phase 7 — admin panel |
| 2026-09-14 | Task | 7 | v2.9: **Phase 7a — the panel exists.** Three decisions were put to Kamronbek before a line was written, because each changed what gets built: the panel **may assume JavaScript** where the storefront may not (§17 #141), this chat takes the shell, the dashboard and the orders screens rather than all ten, and the status trail gets **a table of its own** rather than Django’s `LogEntry` (§17 #142). Built: a `panel` app under `/boshqaruv/`; a guard that gives a signed-in customer **403 rather than a second login form**, because somebody already signed in has not mistyped a password; a mobile-first shell that loads the site’s own tokens, base and components so it cannot drift into looking like a different product; a dashboard whose every tile is a link to the screen that does the work; and the orders list and detail — filters and search as a **GET form, so a filtered list is a URL** you can bookmark or send, an inline status change over fetch, and the trail of who moved what. **One function writes that trail and the Django admin now calls it too**: the admin could change a status straight from its list and did it silently, which is the hole the log exists to close. **Five defects found while building**, two of them only by photographing the screens: the dashboard rendered the shared order row without its status options, so five dropdowns came out empty on a page that returned 200 (§17 #144); the control showed "Toʻlangan" beside a badge reading "Toʻlanmoqda" whenever the order was in a status the panel will not set (§17 #145); `.skip` lived in `pages.css`, which the panel does not load, so the skip link sat visible above the header on every panel screen; searching by phone matched nothing, because numbers are stored formatted with spaces (§17 #143); and a coordinate rendered as "41,315050" under Uzbek number formatting. **Fixed on the way past, outside the panel:** the six `Order.Status` labels and `PaymentMethod.CASH` were plain Uzbek strings with ASCII apostrophes on a TextChoices that predates §4 — so a Russian customer read "To'lanmoqda" in the middle of a Russian page, on their own orders list. Now translated and respelt. New columns: `panel.OrderStatusChange` and `core.Msg.is_read` (the dashboard counts unread messages, which needs something to count). **267 tests**, `check` clean, `makemigrations --check` clean, `audit_live` 0 findings. **7b–7e remain: products, the reviews queue, the reference screens and the inbox** | Phase 7b — the products screen |
| 2026-09-14 | Task | 7 | v2.10: **Phase 7b — the products screen, which the plan calls the most important one in the phase.** Two screens. The **list** carries the two things that change between parcels: a switch for whether a design is on sale, one price box that sets every size, and a stock box per size that saves on its own — "how many are left" is asked with a parcel in hand and should not mean opening a product. The **create/edit screen** takes the name and description in three languages stacked rather than tabbed (a tab hides the two you have not filled in, and those are the problem), the category, the four spec fields, the tags as chips, the size × price × stock grid, and a gallery that **uploads through the same pipeline as a customer’s review photo** — resized, re-encoded, EXIF stripped, because the owner’s own phone writes GPS into a photograph too. The file is checked in the browser first, so nobody waits thirty seconds for an upload that will be refused, and the server checks again because a browser is not a guard. Photographs reorder by drag, in forty lines of the platform’s own events rather than a library (§3: no build step). Colour appears nowhere: the storefront renders no picker, so the panel asks no question (§17 #23). **Three defects, and the split is familiar.** One was mine and the test I wrote for it caught it: `save_product` and `save_grid` are each atomic, the view called them in a row, and a refused grid left a **live product with no sizes** (§17 #146). The other two were found in a screenshot and would have failed no assertion — **every price on both screens rendered cut in half**, once because `width` on an input counts its padding and once because an auto table gave the price column less room than the word "Sotuvda" (§17 #148, which is §17 #125 again in a different table). Also settled: a size with a blank price is deleted rather than zeroed, unless somebody has ordered it, in which case it is switched off and kept (§17 #147). The Definition of Done’s sentence — a complete product with four photographs, tags, specs and a full grid, created in one sitting — is now a test that drives the real screens. **292 tests**, `check` clean, `makemigrations --check` clean | Phase 7c — the reviews queue |
| 2026-09-14 | Task | 7 | v2.11: **Phase 7 closed — 7c, 7d and 7e, and all ten items are in.** The **moderation queue** shows each review’s photographs at `min(260px, 62vw)` rather than as thumbnails, because a queue you can approve without looking is a queue that approves everything (§17 #150); approving goes through `product.services.moderate`, so the product’s rating moves with the decision and the screen shows it move. The **inbox** marks read and unread both ways, sorted newest first rather than unread first — a list that reshuffles as you read it loses your place. The **reference screens** put delivery tiers, tags and size charts on one page and regions with their two hundred districts on another, and five models edit through **one endpoint behind an allowlist**: `Region.code` is not in it, because it is the SOATO code that ties the row to the classifier (§17 #149). **One defect, found in a screenshot, and it is the same one for the third time in two days**: three name fields sharing a 390 px row showed four characters each. §17 #148 was `width` counting its padding and an auto table starving a column; this is flex items shrinking before they wrap. Three causes, one shape — **a field narrower than its own content fails no assertion** (§17 #151). Also: the suite now runs with `--parallel 4`, which took it from six minutes back to forty seconds; the image tests were what made it slow. **317 tests**, `check` clean, `makemigrations --check` clean | Phase 8 — legal documents and content |
| 2026-09-14 | Task | 7 | v2.12: **Phase 7 rechecked at Kamronbek's request, and the recheck found what the phase's own 91 tests could not.** Fourteen defects. **The first one had never worked at all**: the status control — the panel's most-used button, the thing the whole orders screen exists for — saved nothing in a browser, because `panel.js` disabled the select before building the form data and a disabled field is not in a form's data set (§17 #152). Every test passed because every test posts to the endpoint directly; it took driving a real browser and then asking the database. **The second one makes the panel unreachable**: the OTP middleware exempts `/admin/` by path prefix and the panel is language-prefixed, so a staff account with `phone_verified = False` — which is every `createsuperuser` account — is redirected to the OTP screen forever. Raised rather than changed (§4, auth). The audit fixture had been setting that flag since Phase 6, which is exactly why nobody had met it (§17 #153). **Then the panel was put through the project's own audit for the first time** — `audit_live.py` signs in as a customer, so eleven staff screens had never been swept at all. `audit_panel.py` is its sibling, same checks imported from `audit.py`. **423 findings, and the first three were defects in the checks**: a meta description demanded of a `noindex` page, a file input judged instead of the label that drives it, and then a caption judged as a control. Fixing those turned up a real storefront defect nobody could have seen before: the review form's five star labels ARE the control and were 30 px targets, which is §17 #127 a second time. **The rest were the panel's.** A pasted name longer than its column was a 500 rather than a sentence (§17 #154); a malformed date in the query string was a 500 too; `next` in a POST body went unchecked into `redirect()`; panel pages carrying customers' names and numbers had no `never_cache`. Two dashboard tiles promised numbers their links did not show (§17 #155). An order's items listed unit prices beside "× 2" while the total was a line total, so three numbers on the page did not add up (§17 #156). The tag, region and district rows had `aria-label` and no visible label — three identical boxes in a column at 390 px (§17 #157). Approving a review put the button's verb in the state badge (§17 #158). Eight sentences lived in a .js file where gettext cannot reach them (§17 #159). `Size` had no ordering and the size grid is built from it (§17 #162). Two N+1s on the products list, from `.first` ignoring a prefetch. `--fw-normal` has never existed in tokens.css and was used twice. **And one I caused while fixing another**: widening the grid's size column to fit its heading took thirty-four pixels out of the price column and put a six-digit soʻm price in a 67 px box — §17 #148 for a **fourth** time, in the same edit that fixed the first one. The answer was not better numbers but removing the mechanism: headings wrap, the price column is the `auto` one, and the result is measured in three languages at three widths rather than looked at (§17 #160). **341 tests** (24 new, one per defect that a test can hold), `check` clean, `makemigrations --check` clean, `po_needed` empty for ru and en, `compilemessages` clean, **`audit_panel` 0 findings across 13 screens × 5 widths × 3 languages**, **`audit_live` 0 across 22 pages × 5 widths × 3 languages**, and the drive green: status saved and logged, inline edits saved, a product created with photographs at 390 px, reordered, one deleted, a review approved with the right badge, a message marked read, a reference row renamed, a 200-character name refused with a 400 — 0 console errors, 0 alerts | Phase 8 — legal documents and content |
| 2026-09-14 | Task | 7 | v2.13: **Ten corrections Kamronbek found by using the panel himself, and one of them crossed a locked decision.** The big one: `Tag.kind` and `Product.print_method` were `TextChoices`, so adding a tag kind or a print method meant a migration — on the screens that exist so nothing needs a deploy. Both are tables now, seeded by migration 0019 with exactly the values the code held and swapped through a temporary column so no row lost what it had (§17 #164). **`Product.fit` was left alone on purpose**: §17 #70 settled two cuts, a chart finds its products through that field, and reversing it was his call to make, not mine — he chose to leave it. Turkum was already a table with no screen; it has one now. Delete buttons for tags, kinds, methods, categories and charts; none for regions, districts or delivery tiers, because an order points at all three (§17 #165). The price and stock boxes were `type="text"`, and the stock box quietly turned "sa" into **0** — a size taken off sale with nothing on screen to say why; they are number inputs now and the server refuses what is not a number (§17 #166). A refused save used to empty a form somebody had spent ten minutes on (§17 #167). The moderation queue offered Approve on an approved review (§17 #168). The tag chips are grouped under their axis with a filter above them — readable at eight tags, unreadable at forty. The style guide left the nav and kept its URL. And the language switcher moved out of the footer into the header, as two-letter codes in a pill, hidden on a phone where the drawer carries it (§17 #169). **`audit_live` then found one thing nobody had looked for**: a size chart whose name had been cleared was putting an empty heading on the public size-guide page — the panel let the Uzbek name be emptied and the storefront rendered the hole (§17 #170). **380 tests** (39 new), `check` clean, `makemigrations --check` clean, `po_needed` empty for ru and en, `compilemessages` clean, **`audit_panel` 0 findings and `audit_live` 0 findings**, both across 5 widths and 3 languages, 0 console errors — and every correction driven in a real browser: letters refused by the price box, a tag kind added and a tag filed under it, that kind then refusing to be deleted while the tag was on it, the chip filter narrowing eight chips to one, the header pill switching to Russian and landing on the Russian page | Phase 8 — legal documents and content |
| 2026-09-14 | Task | 7 | v2.14: **four more from the settings screen, and one of them reversed a locked decision.** **Qolip is gone** — `Product.fit` and `SizeChart.fit`, two fixed cuts settled in §17 #70 and deliberately left alone a day earlier. Kamronbek reversed it: a cut is something he wants to *say* about a garment and a tag says it already, at any value he likes, with no schema behind it. A size chart is now a name and a picture (§17 #172). The column could not simply be dropped, because a product with no chart of its own found one *through* it — so migration 0020 resolves that fallback into the data first and 0021 drops the columns. **Splitting it into two migrations was not tidiness**: both in one file raises `ObjectInUse` the moment there is a single row to update, because Postgres will not `ALTER TABLE` a table carrying pending deferred trigger events — and 381 tests passed it, because a test database is migrated from empty and an empty table writes nothing (§17 #173). `verify_qolip_migration.py` now replays the pair against a scratch database filled with rows that look like the live catalogue. **Tartib is gone** from tag kinds and print methods — four rows in each, and a sort number somebody has to invent before he can add a print method is a decision that buys nothing; both read oldest first (§17 #171). **The tag list has a search**, matching all three languages, because the owner writes the tags and the list only grows. Tag kinds and tags are two sections rather than one heading crowding another. The header pill's active language is a circle by construction rather than by arithmetic, and the search field gave back 80 px to make room for it (§17 #174). **And the sweep's one finding was the sweep's own**: a 26 px switch seven pixels above the fold had its probe point land past the bottom of the window, `elementFromPoint` answered null, and a control with a perfectly good 44 px target was called too small — intermittently, because which control sits near the fold changes with the language and the width (§17 #175). **400 tests** (19 new), `check` clean, `makemigrations --check` clean, `po_needed` empty for ru and en, `compilemessages` clean, **`audit_panel` 0 findings and `audit_live` 0 findings**, both across 5 widths and 3 languages, 0 console errors, and the migration pair replayed forward, backward and forward again on a non-empty database | Phase 8 — legal documents and content |
| 2026-09-15 | Task | 7 | v2.15: **five corrections from reading the panel as its owner rather than as its author.** **The dashboard is "Hisobot", not "Bugun"** — half of what is on it is not about today, and a tab named after a day says nothing about the page; three tiles took the words he actually uses, *Jarayonda*, *Yetkazilmoqda*, *Yangi sharhlar* (§17 #178). **"Running low" now has one definition** instead of three near-copies: on sale — the size's own switch AND the product's — and five or fewer left, written once as `Variant.objects.running_low()` and shared by the tile, the list beneath it and the list the tile opens. A size taken off sale can no longer fill the first screen he sees each morning (§17 #179). **A size pill is red, amber or plain**: red when nobody can buy it, amber when it is nearly gone, red when both — the template picks one class, worse first, and the inline save now answers with both facts so the pill recolours as the number is typed (§17 #180). **Sign in and sign up became one centred column** like every other screen in the flow; they were the only two still pushed to the left of a brand mark that the header already carries (§17 #177). **And the button labelled "I can't remember my password" says that it signs you out** — it always did, and a person pressing it was not expecting to lose the page they were on (§17 #176). **Then the sweep found what it had been missing about itself**: `audit_live.py` runs entirely in a signed-in context, so `/login/`, `/signup/` and the reset screen had *never been audited at all* — every one of them redirects an authenticated visitor to `/account/`, the redirect answers 200, and the account page was quietly swept three more times under three wrong labels. Four phases of clean sweeps had never looked at the sign-in page. They have their own anonymous context now, and a page that answers by sending the sweep somewhere else is a finding rather than a silent substitution (§17 #181). **424 tests** (24 new), `check` clean, `makemigrations --check` clean, `po_needed` empty for ru and en, `compilemessages` clean, **`audit_panel` 0 findings across 13 screens and `audit_live` 0 across 22 pages**, both at 5 widths in 3 languages, 0 console errors, and the drive green: both forms centred to the pixel at 390 and 1440, the warning sitting with its button, the tile matching its queryset, and a stock box typed from 40 to 3 to 0 turning amber then red without a page load | Phase 8 — legal documents and content |
| 2026-09-15 | Task | fix | **The checkout asked for the recipient's name and threw it away.** Found while reading the checkout for Phase 8: the view required and validated a name, then never passed it on, so every order went out under the account holder's name — wrong for a gift or a parent, and a branch hands a parcel only to the person named on it. Fixed before Phase 8 started, on its own branch (`fix/checkout-recipient-name`, merged into `main` as c4037bf): `Order.recipient_name` with migration 0017, a 120-character limit refused with a sentence, and the name shown on the order page, the panel's list, detail and search, the Django admin and the Telegram notification. Orders from before show the account's name as they always did (§17 #190). **435 tests** | Phase 8 |
| 2026-09-16 | Task | 8 | v2.16: **Phase 8 complete — the three legal documents, in three languages, and the copy around them.** Kamronbek answered the four questions it waited on: the seller is the registered name and address with the contacts and nothing else — no tax number, no bank details (§17 #184); an uncollected parcel costs the customer 15 000 so'm and the admin refunds the rest (§17 #187); a wrong size is exchanged at the customer's cost (§17 #185); and the status follows the tile to *Yetkazilmoqda* (§17 #189). Q22 he left to me: form controls get a border token of their own in Phase 9 (§17 #188). **Built:** `/privacy/` (new, eleven sections), `/terms/` (seventeen, the public offer among them) and `/yetkazib-berish/` (seven), each written whole per language in `templates/legal/` rather than cut into the catalogue (§17 #182), inside one page that prints the version, the day it took effect, a contents list read out of the text (§17 #192) and the history. Every figure they state — prices, payment methods, the 15 000, every period, every retention time — comes from the row or the constant that enforces it, and a test changes the source and watches the page follow (§17 #183); two values that had no single home got one, and the production log is now rotated and kept thirty days so the policy could say so (§17 #196). The footer, signup and checkout link both documents, and signup asks for consent to processing (§17 #195). About and Contact were rewritten — the same-day Tashkent promise is gone (§17 #194) — and the product form offers the four-part description template in each box's own language (§17 #197). `uzb_dates` is deleted (§18 #25). The research changed two of the plan's own facts: "Resolution 2219" is the Postal Service Rules' Ministry of Justice registration number, and a branch holds a parcel 14 days to a month, not always a month (§17 #186). **Defects found on the way:** the checkout was discarding the recipient's name (fixed first, separately — row above); every home order was labelled a post office (§17 #191); the catalogue tools could not read a msgid with a link in it, and the fuzzy test could not see a wrapped one — two entries were silently Uzbek under `/ru/` and `/en/` while it passed (§17 #198); and the new tests moved the suite's language leak onto a Phase 7 test, where it surfaced as a crashed parallel run with a dropped database in every other line — `core/runner.py` now resets the language per test and reports a failure instead of dying (§17 #199). **Then the pages were driven and photographed, and that found three more:** the Russian privacy policy scrolled sideways on a phone, because its title is one 422 px word (§17 #202); a tap on the terms link in the signup consent opened the privacy policy, because the second link's tap target covered the first (§17 #203); and two fixes made earlier in the phase had never reached the machine at all — the write reported success and the file held its old version (§17 #201). A fourth came from looking at them: a range split after its dash (§17 #204). English now names the carrier one way (§17 #200). 33 strings written by hand in three languages, one of them a plural. **486 tests**, `check` and `makemigrations --check` clean, `compilemessages` clean, `audit_live` 0 findings and 0 console errors across 24 pages × 5 widths × 3 languages · `drive_legal` 61 checks — every link in the signup consent, beside the checkout button, in a document's contents at 390 and 1440, on the order page and on the contact page opens what it says and lands below the sticky header · every changed page photographed at 390 and 1440 and looked at | Phase 9 — performance, SEO and accessibility; before launch, §19 Q27–Q31 |
| 2026-09-16 | Task | 8 | v2.17: **Phase 8 rechecked, four of its last five questions answered, and the Telegram bot wired in.** Kamronbek answered: the seller is a sole proprietor — the terms now say who sells, and the seller block and the contact card carry the form, with no certificate number (§17 #208); the postal index was to be looked up — it is 150700, Qoʻqon's main post office, since nothing public maps Sharq dahasi to a branch (§17 #209); parcels go as ordinary parcels, so a branch holds one a month and every page says one month, not "30 days" (§17 #210); the server is in Warsaw, and the privacy policy now says the site's own data is kept in Poland under the GDPR, while which of ZRU-1125's conditions the host meets goes to the legal review (§17 #211, §19 Q32). Q30 is with the owner. **The grey site was not the site**: Dark Reader in his Brave repainted every page; the pages now lock it out and say they are dark (§17 #205). **The bot:** a friend is building the shop's bot and gave it `WEBSITE_WEBHOOK_SECRET`; with `TELEGRAM_BOT_WEBHOOK_URL` set, the four events go to it as signed JSON, and the contract is `docs/integrations/telegram-bot.md` (§17 #206). Both lines are in `.env`, blank — the secret goes in by hand — and the test run blanks them, so no test can notify the shop (§17 #207). **The two 404s in his log** — `/favicon.ico` and Chrome DevTools' probe — are answered (§17 #213). **The recheck** read every Phase 8 file again and drove the pages in his Brave and in Edge: "back" could lead to the same document in the language just left (§17 #212); the contact card broke the email address inside "com" (§17 #214); the prune command's help said "not touched" of a filter on the creation date; the Russian delivery page linked Uzpost's Uzbek map; and the style guide lacked the dark lock. The cancellation message still names an order by its database id, and an Uzbek ordinal can break after its hyphen — §18 #39, #40. Two strings written by hand in three languages, one of them a plural. **525 tests**, `check` and `makemigrations --check` clean, `compilemessages` clean, no entry empty or fuzzy, `audit_live` 0 findings and 0 console errors across 24 pages × 5 widths × 3 languages, `drive_legal` 65 checks, the changed pages photographed at 390 and 1440 and looked at | Phase 9 — performance, SEO and accessibility; before launch, §19 Q30, Q32, Q33 |
| 2026-09-17 | Task | fix | v2.18: **The backlog rechecked and cleared before Phase 9, and Q32 answered.** Kamronbek asked whether everything was clean and ready. **Q32** — from OVHcloud, where he bought the Warsaw VPS, and from the state: Poland is No. 32 on the Cabinet of Ministers' list of countries that protect personal data equally (Resolution No. 415 of 29.07.2026), which is ZRU-1125's first condition; OVHcloud's data processing agreement keeps the data in the datacentre chosen, and its ISO 27001/27017/27018 scope covers VPS. The privacy policy stays as it is, at his word (§17 #215). **His three:** the panel's date filter is dd/mm/yyyy with the browser's calendar behind a button (§17 #217); Uzbek months are lower case — "16 sentabr 2026" (§17 #218); a cancelled order is named by its GX- number (§17 #216); the ordinal break stays (§17 #224). **The recheck's defects, which he chose to fix now:** a browser's own validation words and file-picker labels now speak the page's language (§17 #222), the review form's file field first (§18 #29); an account with orders can no longer be deleted — `Order.user` is `PROTECT`, migration 0019 (§17 #219); a deleted photograph takes its file with it after the commit (§17 #220); the Django admin cleans uploads like the panel (§17 #221); the share card is redrawn in the brand's type (§17 #223). **A defect nobody had met:** an unverified account on `/ru/verify-phone/` or `/en/verify-phone/` was redirected to the same page for ever, because the middleware knew only the Uzbek paths — a signup in Russian or English could not be finished; fixed in its own commit, the OTP flow untouched (§17 #225). **The documentation:** an audit of this plan and the repo's docs found statements that later decisions had made false — §3's language row, §6's unprefixed tree, §7's home-order rule, the cash line in §11, risk #22, the VPS "not bought", the Maps script's loading, and more — all corrected here; the README is rewritten; the bot contract's example no longer gives a branch order a pin. Two new questions (§19 Q34, Q35) and two backlog rows (§18 #41, #42). 17 strings written in three languages. **571 tests** (46 new), `check` and `makemigrations --check` clean, `compilemessages` clean, no entry empty or fuzzy, `audit_live`, `drive_legal` and a new `drive_backlog` in an English-language browser, the changed pages photographed and looked at | Phase 9 — performance, SEO and accessibility; before launch, §19 Q30, Q33, Q34 |
| 2026-09-17 | Task | 9 | v2.19: **Phase 9 — measured, not asserted.** Kamronbek's instructions first: the repository is renamed to **Graphix** and the remote follows it; the owner's **postal address comes off the contact page and the privacy policy** and stays in the offer alone, where the E-commerce Law wants it (§17 #226); **Q34 is answered by the deploy steps** — `createsuperuser`, then tick `phone_verified` in the Django admin, which the phone wall exempts (§17 #227) — and **Q35 is yes**: a product without a tag is refused (§17 #228). Then the phase. **Performance:** every photograph is delivered as WebP at 400/800/1600 through `srcset`, built when its row commits and backfilled by `manage.py build_renditions`, with the quality stepped down until it fits §5's 250 KB (§17 #230); hashed static filenames in production, off under test (§17 #231); the order page's query-per-line prefetched away; indexes on what listings order by; and `deploy/nginx/graphix.conf` so the compression and the cache headers are reviewable rather than remembered. **SEO:** one canonical per page built from `SITE_URL`, alternates from the path alone, `noindex` on every page behind a login or in the middle of a purchase, a description per page in three languages, and one `@graph` carrying the product, its offer, its reviews and the trail to it (§17 #232, #233). **Accessibility:** the control border token §19 Q22 decided, a zoomable photograph made a real control (§18 #24), a live region for what the page does on its own, and the panel's `window.alert` refusals moved onto the page (§18 #27). **Privacy:** Google Maps is fetched on the first tap of “Xaritadan”, not with the page, and the policy now describes that narrower transfer (§18 #34, §17 #235). **Copy:** a no-break space before every spaced em dash in all three languages, and one English voice — 261 edits and 18 rewritten strings (§18 #36, #37). **The measurement is the phase's own finding:** built production-shaped, it scored 98–99 and then showed two defects nothing else had — a drawer that is off the screen but still in the tab order, and a heart whose accessible name left out the count beside it. Both fixed, both now tests. 110 new tests, 683 in all, green |
| 2026-09-18 | Task | fix | v2.20: **One Telegram message per order, and it goes when the money does.** Kamronbek, looking at what actually arrives on his phone: four events, two of them about the same order, and one of those about orders nobody paid for. Merged (§17 #237) — the checkout sends nothing, the Click callback sends the whole order as `order.paid` with the status it has, and an abandoned or cancelled order notifies nobody. The links in every event now open the **staff panel** instead of the Django admin: the order by its GX- number on the screen that carries the status control, and a message or a review at its own row, which meant giving the two panel lists an anchor per card. The bot's contract is rewritten with it — the flow from the customer's payment to the Telegram message, what changed for a bot written against the older version, and a note that `/start` and `/chatid` are how its developer finds the chat id rather than anything the shop uses. 684 tests || 2026-09-18 | Task | 1b, 10 | v2.21: **Phase 10 opened, audited, and Phase 1b moved in front of it.** Kamronbek asked to move on to Phase 10; the audit found that half its Definition of Done — the backups and their restore, log rotation, uptime monitoring, the rate limiter across workers — needed a server that §17 #36 had scheduled *after* it. He chose to deploy first (§17 #238) rather than split the phase. Three more decisions came out of the same audit: the CSP will be **our own nonce middleware** rather than a static nginx header, which first means moving the `onerror` that `image_tags.py` puts on every photograph into JavaScript (§17 #239); **`redis` joins `requirements.txt`**, because `settings.py` already selects a cache backend whose package was never installed — the server would have raised on its first cache read (§17 #240); and GRAPHIX is installed **beside** whatever 57.128.240.51 is already serving, never over it, with a `pg_dump` taken first (§17 #241). Also found: there is still **no §6 smoke matrix**, `check --deploy` is clean under `DEBUG=False` but nothing asserts it, the suite has now left **703 files in `vm/media/`**, and §18 #20 undercounted inline `style` attributes by twenty-five. **Blocked on §19 Q36** — the target box refuses the current SSH key and serves the old site, so it may not be the VPS the plan thinks it is | Phase 1b — answer Q36, then provision |
| 2026-09-18 | Task | 1b | v2.22: **The repository flattened, documented and put under CI — and a silent translation bug found on the way.** Kamronbek, before pushing to the renamed GitHub repository: clear it up, write docs, polish the structure, and rename `vm`. The flatten (§17 #242) moved 282 files as git renames; four tests failed afterwards and every one of them was right to — `BASE_DIR` is the repository root now, so three paths reached one level too high and two source-scanning tests started parsing `.venv`. Fixed with one shared rule rather than two exclusion lists. Running `makemessages` from the new root then turned up §17 #243: a no-break space in the catalogues that never reached `item.html`, which has been serving the Uzbek meta description to Russian and English visitors on every product page since 2026-09-17. One character, nothing failing, found only by reading a diff. Also: `README.md` rewritten, `docs/ARCHITECTURE.md` and `CONTRIBUTING.md` written, GitHub Actions added (§17 #244) with a step that proves the Redis backend loads, because that is the class of bug §17 #240 was. **685 tests green on the new layout** | Phase 1b — provision the server; waiting on the A record and the credentials |


## 17. Decision log

| # | Date | Decision | Reasoning | Where |
|---|---|---|---|---|
| 1 | 2026-09-08 | Django templates + hand-written CSS/JS, no build step | Deploys unchanged; nothing new on the VPS |
| 2 | 2026-09-08 | ~~Yandex free tier~~ → ~~paid Yandex commercial licence~~ — **superseded by #83: Google Maps** | Free tier is not licensed for commercial sites. Yandex kept for its Uzbek data quality; cost accepted |
| 3 | 2026-09-08 | ~~Separate like and favourite~~ → **one merged "like"** | Two similar hearts confuse shoppers; one action matches how the customer and every fashion store think about it |
| 4 | 2026-09-08 | Evolve in place, one branch per phase | Site stays live; no big-bang cutover |
| 5 | 2026-09-08 | Zero new Python dependencies | Everything needed is installed or standard library |
| 6 | 2026-09-08 · **amended 2026-09-14** | ~~Uzbek unprefixed, `/ru/` and `/en/` prefixed~~ → **all three prefixed: `/uz/`, `/ru/`, `/en/`** | Originally: best SEO for the primary audience. Amended on Kamronbek's decision (§19 Q25, §17 #121) — an unprefixed default is a special case Django works around rather than supports, and it cost us a one-way language switcher for four phases. Old unprefixed URLs redirect into the prefixed tree |
| 7 | 2026-09-08 | Internal package `vm` keeps its name until Phase 11 | Renaming touches wsgi, systemd, nginx, venv |
| 8 | 2026-09-08 | Translation via explicit `_ru` / `_en` fields | No new dependency; existing rows keep working |
| 9 | 2026-09-08 | Base font size 14 px → 16 px | The biggest reason the current site reads as cramped |
| 10 | 2026-09-08 | Map is assistive; the address stays required and authoritative | Checkout must work with no JS, no permission, no map |
| 11 | 2026-09-08 | Keep the six-point asterisk; redraw it geometrically | Already distinctive and vector; the traced path is the only problem |
| 12 | 2026-09-08 | ~~15k flat, free at 2 items~~ → 15k branch / ~~30k~~ door, no free threshold *(the home tier is now 40k — see #85)* | Each tier reflects real cost; simplest possible rule to explain |
| 13 | 2026-09-08 | Delivery configured as `DeliveryOption` rows, not hardcoded | Prices will change; that must not require a deploy |
| 14 | 2026-09-08 | `delivery_price` and a location snapshot frozen on the order *(the snapshot is now `location_snapshot` — see #84)* | Same principle as `CartItem.price_stat` — a later change must not rewrite history |
| 15 | 2026-09-08 | Size guide image-first, with optional structured rows | The owner supplies charts as photos; rows are a bonus for a11y and SEO |
| 16 | 2026-09-08 | Telegram notifications committed, not optional | Highest operational value per line of code in the project |
| 17 | 2026-09-08 | Telegram sends fire on `transaction.on_commit`, never raise | A notification must never fail a checkout or fire for a rolled-back order |
| 18 | 2026-09-08 | Legal documents written in-project; review recommended, not blocking | Owner's call; still written to a real standard |
| 19 | 2026-09-08 | Product creation with photo upload is a first-class admin screen | The owner enters the whole catalogue himself |
| 20 | 2026-09-08 | Planning chat and task chats separated; the plan is shared memory | Keeps many chats consistent over a long project |
| 21 | 2026-09-08 | ~~We own the pickup-point dataset~~ — **superseded by #84** | No public Uzpost API exists; a live lookup would add a checkout failure mode for no benefit |
| 22 | 2026-09-08 | ~~Pickup picker is list-first, map-second~~ — **superseded by #84: there is no picker at all** | A pure-map picker with thirty overlapping pins is unusable at 390 px and fails when the map does |
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
| 36 | 2026-09-09 | **Phase 1 splits into 1a (brand and code) and 1b (deployment), and 1b moves to just before Phase 11** | Kamronbek's push-back was correct: the VPS isn't bought, the work is local, and nothing between here and Phase 10 needs a server. The original "rebrand early" rationale was about external lead times for a *domain move* — and there is no domain move any more (#35). An idle VPS is rent paid for nothing. 1b still runs before Phase 11, whose live payment tests need a live site. ⚠️ **Half superseded 2026-09-18 by #238:** the split stands, but 1b now runs *before* Phase 10 rather than after it. The last clause turned out to be wrong — Phase 10 does need a server |
| 37 | 2026-09-09 | **The mark is redrawn at a true 60° hexagonal asterisk, symmetrising the original** | Measuring the source PNG showed the two diagonals at different slopes — 0.594 and 0.543 dx/dy — which is hand-trace error, not intent; their mean is within 1.5 % of 60°. The redraw uses exact 60°, equal bar weights and a common centre. IoU against the original is 0.943, and the whole residual is a hair-thin sliver along the diagonal edges. 1.9 KB and hundreds of nodes → **225 bytes and three straight-edged subpaths** |
| 38 | 2026-09-09 | **The wordmark lockups move from Phase 1 to Phase 2** | `logo-full.svg` and `logo-stacked.svg` are the mark *set with the wordmark*, and Phase 2 chooses the display typeface. Drawing them in Phase 1 means drawing them in a face we are about to replace, then drawing them again. Nothing in Phase 1 needs them — every icon and the favicon use the mark alone |
| 39 | 2026-09-09 | **"100+ dizayn" is hardcoded in the tagline, not rendered from the live product count** | Kamronbek's call, made with the trade-off stated: the catalogue is currently empty, so the claim is untrue today. Recorded because it is the first sentence a visitor reads. Risk #14 stays open and **Phase 11 item 2 becomes a hard launch gate** — 100+ real designs, or the line changes before launch |
| 40 | 2026-09-09 | **Every raster icon is one identity: a white mark on a solid black tile** | Favicon, apple-touch, both PWA icons and the OG card all read as the same object at every size, and white-on-black is legible on light and dark browser chrome alike. It also matches the existing `theme-color: #000000`. Phase 2 may re-skin them once the palette is chosen; black and white is the lowest-regret choice to ship before that decision exists |
| 41 | 2026-09-09 | **`site.webmanifest` is a rendered template, not a static file** | It has to name the icon files, and Phase 9 introduces `ManifestStaticFilesStorage`, which hashes their filenames. Serving it through `TemplateView` + `{% static %}` — the same pattern `robots.txt` already uses — means the paths keep resolving instead of silently 404ing after that change |
| 42 | 2026-09-09 | **Phase 2 proceeds on drawn garment mockups instead of waiting for photography** | Kamronbek's call, with the trade-off stated. `media/products/` contains no photograph of a t-shirt, and the alternative was parking Phase 2 for an unknown time. A generator (`docs/design/mockup/`) draws a garment with real oversize-tee proportions, fabric shading and a consistent 4:5 crop on one backdrop. **What this buys and what it does not:** layout, crop, hierarchy and typography are judgeable; *"does this shop look professional"* is not, because that question is answered by the photography. §8's warning stands and Phase 11 stays gated on real shots |
| 43 | 2026-09-09 | **The typeface shortlist is fixed to the nine families that contain U+02BB and Cyrillic; `--f-mono` is settled as IBM Plex Mono** | Measured, not assumed: 31 families were downloaded and their cmaps read. 22 fail, including Manrope, Figtree, Outfit, Plus Jakarta Sans, Sora, Space Grotesk, Bricolage, Archivo and Rubik — and Golos Text, which is a Cyrillic-first family built for Russian. IBM Plex Mono is the **only** monospace that passes, so there is no choice to make there. IBM Plex Sans and Mulish pass on coverage but set `O ʻzbekiston` with a visible gap, so they are out on spacing |
| 44 | 2026-09-09 | **All three round-one directions rejected; replaced by a single dark, premium direction rather than another set of three** | Kamronbek rejected all three — thin, sharp type that read "hand made cheap", a desktop layout that was actually broken, and a wish for dark-but-not-black. His feedback was specific enough to design *to*, so offering another menu would have spent his time re-judging instead of getting one thing right. **Three lessons recorded so they don't repeat:** (1) a shortlist drawn from a single type register produces three directions with one voice — screen across registers before shortlisting; (2) an unconstrained product image with a 900 px breakpoint is a bug shipped as a design, not a stylistic choice; (3) light text on a dark ground reads thinner than it measures, so weight and warmth must be raised deliberately |
| 45 | 2026-09-09 | **Palette: warm charcoal layers plus a single brass accent. Never pure black, never pure white** | Kamronbek: *"dark colours including black"* — not `#000`. Ground `#100E0C` with `#17140F` and `#211C15` above it lets panels separate by material instead of by outline, which is what reads as expensive. Ink is warm off-white `#EFE9DE`: pure white on near-black halates and makes type look brittle. Brass `#C6A44E` is confined to price, chosen size and the buy button — one accent, spent in one place |
| 46 | 2026-09-09 | **Type: Playfair Display for display, Onest 500–600 for UI. Body weight is 500 and never 400** | Playfair is the only high-contrast fashion serif found that contains U+02BB, so it is effectively the only way to get a premium editorial voice *and* set `Oʻzbekiston`. Onest stays for UI because it is sturdy at 500+, has tight U+02BB spacing and real Cyrillic. The 500-minimum is a hard rule, not a preference: it is the direct fix for the "thin" complaint |
| 47 | 2026-09-09 | **Desktop product-page contract: two columns from 860 px, sticky gallery with a vertical thumbnail rail, main image capped at `min(76vh, 760px)`** | Written as a rule because the underlying requirement is *one photograph must never take more than one screen*. The round-one page failed it by leaving the image unconstrained, and the 900 px breakpoint meant any frame narrower than that silently fell back to a single column. Both are easy to reintroduce in Phase 5, so the numbers are recorded here rather than left to judgement |
| 48 | 2026-09-09 | **The new stylesheets are loaded only by the style guide until Phase 5** | `main.css` and `components.css` both define `.btn`, `.wrap`, `.nav`, `.foot` and more. Wiring the new system into `base.html` now would have every storefront page loading two conflicting stylesheets for three phases, with whichever loaded last silently winning. The style guide is standalone, loads the new system alone, and `base.html` switches over in Phase 5 when the pages are rebuilt and `main.css` is deleted |
| 49 | 2026-09-09 | **Fonts are subset and self-hosted as variable WOFF2; monospace is declared but never preloaded** | Subsetting to the ranges the site actually prints cuts Playfair 293→56 KB and Onest 188→54 KB while keeping the weight axis, so one file serves every weight. Mono is in `@font-face` but no storefront page sets `--f-mono`, so the browser never downloads it — it costs nothing until Phase 7's admin panel uses it. This also removes the third-party `rsms.me` request that blocked rendering on every page of the old site |
| 50 | 2026-09-09 | **Phase 3 ships the i18n machinery and every Python-side string; template copy moves to Phase 5, per page** | Phase 5 rebuilds all 25 templates from scratch. Wrapping the current ones in `{% trans %}` and writing three languages of copy for them means translating text that Phase 5 deletes — the exact "every template gets written twice" waste this phase exists to prevent. Python strings are different: form labels, validator messages and checkout messages survive the rebuild untouched, so they are translated now (25 strings, three languages, compiled and tested). Phase 5's per-page checklist already demands all three languages, so each page is written once against the finished design |
| 51 | 2026-09-09 | **SMS bodies stay Uzbek-only** | Eskiz moderates message *text*, so three languages means three templates through moderation and three to keep in sync. The password-reset flow also has no language context to work from — it starts from a phone number typed by someone who is not logged in. One moderated Uzbek template is the correct trade until there is evidence of Russian-speaking signup drop-off |
| 52 | 2026-09-09 | **The Click webhook lives in its own `webhook_urlpatterns` list, included outside `i18n_patterns`** | `payment/urls.py` held the callback next to the human-facing checkout pages, which cannot both go in and stay out of the language prefix. Splitting the list makes the boundary explicit at the point someone would edit it, rather than relying on a comment. Five tests assert the path is identical under uz, ru and en and that the prefixed variants 404 — this is risk #2, where the failure is silent |
| 53 | 2026-09-10 | **§7's `name_uz/ru/en` shorthand is implemented as `name` / `name_ru` / `name_en` on every new model** — `Tag.name`, `SizeChart.note`, `Product.material`, `DeliveryOption.name`/`note`, `PickupPoint.name`/`address` | Decision #8 put Uzbek in the *base* column precisely so existing rows keep working, and `core.i18n.tfield` resolves `<field>_<lang>` with a fallback to the bare field. A literal `name_uz` would mean `tfield` had to special-case Uzbek, and the base column would sit unused on every new table. §7's shorthand was describing the three languages, not the column names |
| 54 | 2026-09-10 | **`order_no` is generated in `Order.save()` from the highest number already used that day, with a savepoint retry in `create_order_from_cart`** — not from the PK, and not from a counter table | The PK is exactly what the number exists to hide (§7), so it can't be the source. A per-day counter table would be race-free but adds a table and a lock to the checkout path for a shop taking single-digit daily orders. Generating from the day's maximum is simple and readable; the unique constraint is the real guarantee, and each retry runs in its own nested `atomic()` so a collision rolls back only that savepoint and leaves the caller's transaction — and its `select_for_update` lock — intact |
| 55 | 2026-09-10 | **Slugs are generated in `Product.save()` / `Category.save()` and then frozen: renaming a product never moves its URL** | Found by a failing test, not by design review — `Product.objects.create(name=…)` with a unique non-null slug collides on the empty string the second time. Deriving it in `save()` fixes that and means the owner never *has* to type one. Freezing it on rename is the important half: a slug is a permanent address, and silently changing it breaks every existing link and every indexed search result. The admin still shows the field, prepopulated, so a deliberate change stays possible |
| 56 | 2026-09-10 | **A sold-out design stays listed and keeps its page. `is_active` is the only thing that hides a product; stock is enforced in the cart** | The tempting reading of "purchasable = available AND stock > 0" is to filter the shop on it, which would make a sold-out design vanish — and for a graphic-tee shop that is the opposite of what you want: out-of-stock designs still drive interest, hold their search ranking, and tell a returning visitor the shop is alive. So the listing filters on `available`, the product page greys out the sizes that have run out, and `resolve_variant` / `add_variant` are what refuse the sale. `is_active=False` remains the owner's explicit "take this down" |
| 57 | 2026-09-10 | **`cancel_paid_order` is a separate service from `cancel_order`, rather than teaching `cancel_order` to handle paid orders** | `cancel_order` is reachable from the storefront, and a customer must not be able to cancel an order they have already paid for. Widening it to restore stock would also have widened who can call it. Two functions make the boundary a fact rather than a convention: `cancel_order` stays PAYING-only and touches no stock (an unpaid order never took any), and the restoring path is staff-only, which is where Phase 7 will wire it |
| 58 | 2026-09-10 | **`data/pickup_points.csv` ships with a header row and no data, and the seed command validates coordinates against Uzbekistan's bounding box** | Branch addresses and coordinates are not guessable, and a plausible-looking wrong row sends a real parcel to the wrong place — so nothing was invented to make the phase look finished (§19 Q3/Q4). The command, its validation and its tests are complete and waiting for the data. The bounding-box check exists because swapped latitude and longitude is the one data-entry error that produces a syntactically perfect row pointing at another country; the file is validated whole before anything is written, so a typo in row 400 can't leave the table half-updated |
| 59 | 2026-09-10 | **A `{# #}` comment must never span lines, and a test enforces it across every template** | Django's comment token is matched without `re.DOTALL`, so a comment spanning lines is not matched at all and falls through the lexer as literal page text. It had shipped on `base.html` and `_footer.html` — meaning *every page* carried a developer comment, the footer's inside `<body>` as visible text. The rule is cheap; remembering it is not, and it had already been fixed once in Phase 2 and then reintroduced in Phase 3. So `core/test_templates.py` walks every template and fails on the pattern, on unbalanced `{%`/`{{`/`{#` delimiters, and on any template token reaching rendered output. It also pins Django's own behaviour, so if a future version starts stripping them the guard reports that rather than silently becoming decorative |
| 60 | 2026-09-10 | **A string wrapped in `gettext` without a catalogue entry is a defect, not a to-do: `makemessages` is part of any change that adds one** | Phase 4 added thirteen `gettext_lazy` labels and never extracted them, so `Product.Fit`, `Tag.Kind`, `Review.Status`, `PrintMethod` and the two `Order.clean()` messages rendered Uzbek under `/ru/` and `/en/`. Nothing failed — the site just stopped being trilingual in those places, which is the hardest kind of regression to see. Decision #50 already says Python-side strings are translated *now* rather than deferred to Phase 5; this is the enforcement. `CatalogueCompletenessTests` fails on any msgid with an empty `ru` or `en` translation, on catalogues that have drifted out of step, and spot-checks the labels that were missed. Its `.po` parser reads wrapped continuation lines, because a single-line regex would skip exactly the long strings most likely to be left untranslated — and a separate test asserts the parser found entries at all, so it cannot pass vacuously. Uzbek `msgstr` entries stay empty by design: gettext falls back to the msgid, which *is* the Uzbek source |
| 61 | 2026-09-10 | **Pages not yet rebuilt extend `base_legacy.html`, which keeps `main.css`. The new `base.html` loads only the design system** | Kamronbek's call between three options. #48 says the shell switches over in Phase 5 and `main.css` is deleted — but switching the shell first would leave twenty pages that still use `main.css` class names completely unstyled for the length of the phase, and rebuilding all twenty-five templates before switching anything means nothing is reviewable until the phase is finished. A second base costs one temporary file and keeps every page styled and every page on exactly one stylesheet, which is the part of #48 that actually matters. The same shim exists for the partials the legacy base includes (`_nav_legacy.html`, `_footer_legacy.html`) and for the old script, renamed `legacy.js` so the new shell could take the permanent `main.js` name. **All five files — plus `main.css` — are deleted when the last page moves across**, and that deletion is Phase 5's Definition of Done |
| 62 | 2026-09-10 | **Phase 5 renders the markup; Phase 6 wires the behaviour** | Kamronbek's call. Phase 5's item list wants a search field, a heart and its count, and a guest-usable cart in the shell — while 6b owns likes, 6c owns search and 6g owns the anonymous-cart merge. Splitting on markup-versus-behaviour matches §13's reasoning that features attach to pages already in final form, and it means neither the shell nor the product page gets opened twice. In practice: the heart and share buttons render complete and are inert until 6b; the header search posts to the shop's existing `?q=` until item 5 ships `/qidiruv/`; the `Ommabop` and `Reyting` sort options are absent from the control until 6b adds the sorts behind them, because an option that does nothing is worse than one that isn't there. **Nothing here is customer-facing before Phase 11**, so an inert control cannot reach a real shopper in the meantime |
| 63 | 2026-09-10 | **A fuzzy catalogue entry is a defect, and a test fails on any of them** | `makemessages` marks an entry fuzzy when it guesses a translation from a similar old msgid — and gettext then *ignores* that entry and renders the source Uzbek. Four Phase 5 strings shipped that way, including **`Savatga qoʻshish`, the add-to-cart button**, guessed from `Yangi parol` and friends. The empty-`msgstr` test from #60 cannot catch it, because the entry is filled — just inert. Found by reading a Russian screenshot and noticing one dropdown option in the wrong language. The check is three lines and belongs beside the other catalogue tests |
| 64 | 2026-09-10 | **The home hero's mobile dimensions are a budget, not a taste decision, and `.git/fold.py` measures it** | Decision #29 requires a product row to be at least partly visible at 390 × 844 without scrolling. The first build of the home page missed it by 108 px — the hero art at 42vh plus generous padding put the first card at 952 px, which is precisely the full-viewport hero #29 calls a known conversion killer. Nothing looked wrong in a full-page screenshot, because a full-page screenshot has no fold. The art is now capped at 28vh with tighter padding, putting the section heading at 750 px and 36 px of the first card on screen; the numbers are commented in `pages.css` as a budget so the next person nudging that padding knows what they are spending. `.git/fold.py` checks it in all three languages and needs a browser, so it lives with the render script rather than in the Django suite |
| 65 | 2026-09-10 | **A single-column mobile grid gets `minmax(0, 1fr)`, and a long unbreakable string gets `overflow-wrap: anywhere` — not `break-word`** | The contact page scrolled 21 px sideways at 360 px because of one email address. The obvious fix, `break-word` on `a`, did not work, and understanding why is the point: `break-word` breaks the *rendering* but leaves the element's min-content width at the full unbroken word, while a grid item defaults to `min-width: auto` — so the column kept sizing to the whole address and took the page with it. Only `anywhere` actually reduces min-content width. Both halves are needed: `anywhere` on `a`, `address` and `dd`, and `minmax(0, 1fr)` declared explicitly on every page grid that is one column on mobile. Paragraphs keep the gentler `break-word`, since a long word in prose is not a layout risk. Recorded because the wrong fix looks right and reads right, and the next person will reach for it too |
| 66 | 2026-09-11 | **The error pages are rendered with DEBUG off, by `.git/render_errors.py`, because that is the only condition under which Django uses them** | `render_all.py` fetched `/definitely-not-a-page/` with DEBUG on, so the file it saved as `notfound.<lang>.html` was Django’s yellow technical-404 page — and the six-breakpoint sweep checked that page and passed it. `404.html`, `403.html` and `500.html` had therefore never been rendered at all. 403 and 500 have no URL that reaches them, so the script calls Django’s own default handlers directly, which is what Django does when a view raises. DEBUG is flipped with `override_settings` rather than in the environment, because `settings.py` turns on `SECURE_SSL_REDIRECT` when DEBUG is off at import and the test client would then answer every request with a 301 to https. **Rendering them found a real defect:** `server_error` renders `500.html` with no context at all — no request, no context processors — so the footer’s language switcher came out as an empty box above a form with no CSRF token and no `next`. It is now guarded on `languages`. The rule this leaves behind: **nothing in `base.html` may depend on context being present**, and the 500 render is what proves it |
| 67 | 2026-09-11 | **`--c-fg-subtle` is for decorative and disabled text only. Quiet-but-readable text gets a new token, `--c-fg-hint`** | Phase 2 checked every foreground token and recorded that the lowest contrast in the system is 3.34:1 *on a decorative token*. That was true; what nobody checked is where the decorative token was being used. The footer’s copyright line and its delivery note were both set in `--c-fg-subtle` at 4.18:1, under the 4.5:1 §9 requires — and no value of that token clears 4.5 on any ground in the system, so it was never a text colour. The fix is a fourth neutral, `--c-fg-hint` `#958A79`, at 4.53:1 on the darkest ground and 5.68:1 on the page; it carries placeholders, timestamps and fine print, and `--c-fg-subtle` keeps disabled states, separators and empty-state art. **The token was not wrong, its use was**, which is why nothing in the signed-off palette changed |
| 68 | 2026-09-11 | **A tap target is measured by hit-testing, and where growing the box would cost the typography the hit area grows instead** | §9 sets 44 × 44. Measuring an element’s own rectangle gets this wrong in both directions: a 22 px radio inside a 44 px label is easy to hit, and a chip carrying an expanded pseudo-element is fine at 29 px tall. `audit.py` probes four points around each control with `elementFromPoint` and asks whether a fingertip would land on it, which is the actual question. Where the fix would have cost the design — standalone text links, breadcrumbs, tag chips — an absolutely positioned `::after` grows the target and leaves the text exactly where it was. Where it cost nothing — the nav icons, the drawer’s 20 px close button, small buttons, footer links, the language switcher — the control itself grew |
| 69 | 2026-09-11 | **The size guide is one image the owner uploads at `static/img/size_guide.png`. Until it exists the page 404s and every link to it is hidden** | Kamronbek’s call, and the sharper half of it is the second sentence: *if there is no guide, nobody should learn that there was meant to be one*. So there is no “coming soon” state — the footer link, the product page’s link and the sitemap entry all disappear together, keyed off one `finders.find()` in a context processor. A negative result is deliberately not cached, so uploading the file is enough: no restart, no deploy. The `SizeChart` model stays and renders underneath the image once Phase 6 seeds it (§19 Q9). `.git/render_size_guide.py` renders the page against a stand-in image so its layout is checked before the real file ever arrives |
| 70 | 2026-09-11 | **`Product.Fit` is `regular` and `oversize`. `boxy` is gone** — ⚠️ **reversed 2026-09-14 by #172: the field is gone entirely** | Kamronbek: *“for now just take regular and oversize only”*. Phase 4 shipped three, taking `boxy` from the tag examples in §7 rather than from anything the catalogue needed. Migration `0014` folds any row carrying it into `oversize` and narrows the choices. Done now, before the catalogue exists, because after that it stops being a schema change and becomes a data problem. The `boxy` *tag* is untouched — fit and style are different axes, and tags are the owner’s to keep or delete (#71) |
| 71 | 2026-09-11 | **There is no fixed tag taxonomy. The owner writes tags when adding a product** | Kamronbek: *“tags for clothes will be written by admin when adding product”*. The eight seeded in Phase 4 are a starting set, not a contract, and §19 Q6 is closed by that answer rather than by a list. The consequence worth remembering: the Phase 13 recommender reads these tags, so recommendation quality is downstream of how consistently they get typed — Phase 7’s admin should make picking an existing tag easier than typing a new one |
| 72 | 2026-09-11 | **A rule that styles a whole group of controls is written with `:where()`, so a rule aimed at one of them still wins** | `.nav__actions button, .nav__actions a { display: grid }` scores (0,2,1). Every `display: none` written for an individual icon scores (0,1,0) and lost, silently, for the whole of Phase 5: the hamburger and a redundant search icon sat on desktop beside the links and the field they exist to replace, and a fifth icon sat on mobile beside the drawer that already holds it. Nothing looked broken, so nothing was reported — it was found by counting icons in a screenshot. `:where()` drops the group rule to zero specificity and the specific rules take over. **A rule that exists to be overridden should not be able to win** |
| 73 | 2026-09-11 | **An overlay that covers the page owns the keyboard until it closes** | The drawer moved focus in and gave it back, which read as complete — but Tab walked straight out of it onto links behind the panel, and the filter sheet never took focus at all. Focus you cannot see is worse than no focus management, because the visitor is typing into a page they are not looking at. `main.js` now has one `trapFocus` used by both, one counted scroll lock so closing one overlay cannot unlock the page underneath the other, and Escape everywhere. Proved by `interact.py` pressing Tab twenty-four times and checking where focus ended up |
| 74 | 2026-09-12 | **A rule that duplicates what a breakpoint sets must come before that breakpoint, never after it** | The sharpest lesson of the rebuild so far, because the cost was invisible and large. A one-line fix for a 360 px overflow added a shared `grid-template-columns: minmax(0, 1fr)` for six layouts, and placed it after `.pdp`’s and `.shop`’s own media queries. Media queries carry no specificity, so from that moment the product page and the shop had one column at every width — on a 2000 px monitor as much as on a phone. **No test caught it**: nothing scrolled sideways, nothing was clipped, no control was too small; the pages were simply the wrong shape, and the screenshots were read as “mobile-ish” rather than wrong. The minmax now lives in each layout’s own base rule, and `interact.py` asserts the column count of every multi-column page. The general rule, which also covers §17 #72: **a rule that exists to be overridden must not be able to win** |
| 75 | 2026-09-12 | **A photograph never sizes its own frame** | Every image box — the product frame, the thumbnails, the card media, the cart thumbnail, the hero art — holds the catalogue ratio and pins its image with `position: absolute; inset: 0`, so the image is out of flow and cannot contribute to layout at all. Before this the product frame changed size with the source: a tall image shrank it by 45 px, because `height: 100%` against a parent whose height came from `aspect-ratio` and a `max-height` resolved into the image’s own intrinsic ratio. The frame’s width is now derived from the height cap and the ratio rather than from the column. This matters more than it sounds: the catalogue will be filled from mixed sources by whoever is adding products, and a grid whose tiles change shape with the photograph is the single most reliable way to make a shop look amateur. Asserted by `interact.py` with 3000×500, 500×3000 and 900×900 sources |
| 76 | 2026-09-12 | **The shop is a sticky sidebar and an independently scrolling results column. The product gallery does not travel at all** | Kamronbek’s call on both. The sidebar needed a wrapper to work: a stretched grid item fills its own grid area exactly, and `position: sticky` has nowhere to travel inside a containing block it already fills — so the wrapper takes the stretch and the sidebar sticks inside it. Its `top` had never applied either: `inset: auto`, written on the line after `top`, reset it, so the “sticky” sidebar had been an ordinary block since Phase 5. It now pins under the header for as long as there are products to scroll past, and scrolls on its own when the filter list outgrows the screen. The gallery went the other way: sticky is what made the photograph slide down the page, so it is gone |
| 77 | 2026-09-12 | **On mobile the hero is type and two buttons; the photograph and the supporting line move** | Kamronbek: remove the picture below the second button and put the “Premium sifat…” line there instead. The order is eyebrow, headline, buttons, supporting line — done with flex `order` so the desktop hero keeps one source of truth, and the image is hidden rather than removed, marked `loading="lazy"` so a phone never downloads it. The effect on §17 #29 is larger than the request: the first product card sits 283 px above the fold instead of 36 |
| 78 | 2026-09-12 | **The demo catalogue is seeded data in the real local database, not a fixture that only exists inside a test run** | The review screenshots, the 342 breakpoint checks and every interaction check are measured against eight specific products — one with four photographs, one with a sold-out size, prices long enough to test the thin-space grouping, names long enough to wrap. Until now those rows lived only in a database `render_all.py` created and destroyed, so a developer opening the site saw whatever scratch rows were lying about instead. **Verification and development were looking at different sites**, and that gap is what let a product page with no second column go unnoticed. `manage.py seed_demo_catalogue` puts the same eight in the real database; the photographs are tracked in `docs/design/demo-catalogue/` and copied into the gitignored `vm/media/` when missing, so the command is all a fresh clone needs. It refuses a non-local `DB_HOST`, because "reset the catalogue" must never be able to reach production by accident |
| 79 | 2026-09-12 | **A checklist item the phase cannot honestly meet is moved to the phase that can, not ticked** | Four of Phase 5's items were unmet, and leaving them as unticked boxes under a "Done" phase is how a plan stops being trusted. Gallery **pinch-zoom** and the shop's **skeleton loading** go to Phase 6: the zoom because one full-screen viewer should serve both the chart and the photograph and 6a is already building it, the skeleton because the grid is server-rendered and there is no loading moment for it to fill until 6b fetches asynchronously. **`srcset`** goes to Phase 9 with the rest of the image pipeline (§18 #14 said so already; the checklist did not). **Lighthouse** goes to Phase 9 because the score is mostly the image pipeline. And Phase 5 item 6 claimed a cart that **works for anonymous visitors** while `cart`, `cart_update` and `cart_remove` are `@login_required` — Phase 4 built the model, §9 Phase 6g owns the views, and the item now says so |
| 80 | 2026-09-12 | **A string the site flashes at a visitor is copy, wherever it lives** | §4's "no hardcoded user-facing strings" was read as being about templates. It is not: twenty messages in `cart/views.py`, `payment/views.py`, `user/views.py`, `user/password_reset.py` and `user/models.py` had never been marked, so a Russian or English visitor got Uzbek when they added to the cart, verified a phone, reset a password, cancelled an order, or signed up with a number already on file. Now wrapped, respelt with U+02BB, and written in all three languages — and guarded by a test that parses the source with `ast` rather than grepping it, because the question is *which argument* carries the string: `add_error('code', _("…"))` is correct and `add_error('code', "…")` is not, and no regex tells those apart reliably. **The SMS bodies are deliberately excluded**: Eskiz moderates the exact message text, so translating one stops it sending until re-moderated (§19 Q17) |
| 81 | 2026-09-12 | **CSS keeps a rule with no markup only when the plan names the phase that adds the markup** | 23 classes were defined and unused. Two whole sections were **superseded duplicates** and are deleted: `.gallery__*`, which the product page stopped using when it became `.pdp__*`, and `.hero__*`, replaced by `.home__hero*` — dangerous rather than merely dead, because the next person to restyle the gallery would have edited the wrong rule and seen nothing happen. Four unused utilities went with them, and `--container-wide` with `.wrap--wide`. The rest stay, because a phase is named for each: `.toast*` and `.modal__*` in Phase 6, `.review__*` and `.stars--input` in Phase 12, `.skel*` with 6b's first async fetch. Also folded in: three hand-written `color-mix(… #000 …)` scrims, already drifted to two different values, are now one `--c-scrim` token — the last hardcoded colour outside `tokens.css` |
| 82 | 2026-09-12 | **Any script that writes `PLAN.md` asserts its version string first** | The file on disk had been reverted to v1.5 — the end of planning, before a line of Phase 0 — while git held v1.18. §18 #17's failure mode, on the one file that is the project's memory between chats, and `git status` reported it as one modified file among the session's own edits. The cost if a chat had read it instead of noticing: every locked decision after #22 and the entire Phase 2–5 record, silently absent. `.git/plan_v119.py` opens with `assert "**Plan version:** 1.18" in s`, and every later one does the same with its own predecessor. A plan amendment that cannot see the version it expects must stop, not write |
| 83 | 2026-09-12 | ~~Yandex~~ → **Google Maps Platform** | Owner's decision. Yandex was chosen for Uzbek street data, and that advantage is real — but it came with a commercial-site licence that needed a sales conversation and an unknown monthly cost (the old §19 Q1), and it was blocking a locked decision. Google bills per use against a monthly free allowance, which suits a map that now appears on **one form**: #84 removed the branch picker, so the only map left is the home-delivery pin. The `GX.map` wrapper (#27) is why this cost nothing — the provider changed and there was no code to rewrite. Needs an API key restricted to the site's domains, on a project with a billing alert |
| 84 | 2026-09-12 | **Branch delivery is region + district + a typed 6-digit postal index. `PickupPoint` is dropped** | Owner's decision, and the most valuable one in the project so far, because it dissolves a dependency rather than working around it. There is no public Uzpost branch list (§3 research), so owning a `PickupPoint` table meant owning data we could not obtain: Phase 4 shipped the loader, the validation, the tests and an **empty** CSV, and it had become the blocker on all of Phase 6 (old Q3/Q4, now closed). The customer knows their own postal index — so they supply the one field we cannot, and we own only what is published: two small SOATO-derived reference tables, 14 regions and ~210 districts and cities. `pickup_snapshot` becomes `location_snapshot`; `requires_pickup_point` becomes `requires_branch`. **The retirement is Phase 6d work, not a rewrite of Phase 4's record** |
| 85 | 2026-09-12 | Home delivery ~~30 000~~ → **40 000 so'm** | Owner's pricing decision. **The code still says 30 000** — the seed migration, the product page, the delivery page, the style guide and three catalogue entries — so plan and site currently disagree, and the site is what a customer reads. Phase 6e changes all six places together (§18 #18). Risk #6 and §19 Q5 both move to 40 000 |
| 86 | 2026-09-12 | **The postal index is validated against the chosen region's prefix, in the view *and* in `Order.clean()`** | A six-digit index is easy to mistype and a wrong one sends a real parcel to the wrong place. The first two digits encode the province, and that is knowable from the region the customer already picked — so the one class of error worth catching automatically, a parcel leaving for another province, is caught. The `Boshqa` region skips the prefix check and keeps the format check, so an address the classifier does not cover is still orderable. Enforced in both places because the checkout view is not the only thing that will ever build an order |
| 87 | 2026-09-12 | **Region and district are drawers; the district list is scoped to the region, grouped by kind, and changing the region clears it** | The first version of this said drawers were needed because "210 districts is unusable in a native picker", which is nonsense once the list is scoped to one region and holds 10–30 entries — Kamronbek caught it. The real reasons are that a native `<select>` cannot **group** (*Tumanlar* then *Shaharlar*, because someone in Angren is looking for a city, not scanning an alphabetical mix) and cannot carry a **search field only where one is warranted** — above about fifteen entries, so the largest regions only; over twelve items a search box is clutter. Catching that error also exposed a modelling one: `District` held only *tumanlar*, so Nurafshon, Angren, Olmaliq and every other regionally-subordinate city had no row and their residents would have been pushed onto `Boshqa` — hence `kind` (#84). **Changing the region clears the district**, because a stale district from the previous region submits silently, and a wrong address that looks completely plausible is the worst kind there is. Both drawers degrade to plain selects with JavaScript off |
| 88 | 2026-09-12 | **`address_source` records whether a home address came from the map or was typed** | One column, and it answers the question the courier actually has: are these coordinates the customer's own or a geocoder's guess? A typed address stores no coordinates at all, so the absence is meaningful rather than missing data |
| 89 | 2026-09-12 | **The plan forked, and the merge renumbers rather than reconciles numbers** | Two chats amended this file from different bases on the same day: a planning chat turned v1.3 into its own v1.4 and v1.5 (#83–#88 above), while task chats carried the same file from v1.6 to v1.19. Both numbered new decisions from #23, so **the same number meant two different things** — the planning line's #33 was the delivery redesign and #37 the 40 000 price, while this line's #33 is the footer context processor and #37 the geometric mark. Renumbering the planning line's decisions into this sequence is the only safe merge: a cross-reference must resolve to one thing forever. The planning file itself was lost — overwritten by a `git checkout` during the gate review, by me, after I read its lower version number as a stale revert — and its decisions were rebuilt from the gate-review session's transcript, which held the parts of it I had read. **What that means for anyone reading this:** #83–#88 are faithful to the decisions and the reasoning, but the §7 `Region` / `District` field list is a reconstruction and should be checked against the planning chat before 6d builds it. §0 now carries the four rules that prevent a second fork |
| 90 | 2026-09-12 | **`data/regions.csv` is built from the official SOATO / MHOBT classifier. The public compilations are a cross-check, never a source** | Three exist on GitHub. The most complete — 14 regions, 210 cities, 2 641 districts, SOATO codes, three languages, updated April 2025 — is **GPL-3.0**, and the other two carry **no licence at all**, which is legally worse: no licence means all rights reserved. Copying either into a commercial repo is the kind of risk nobody notices until it matters. The divisions themselves are government-published facts and nobody owns them; a compilation of them may be owned. We need two levels and no mahallas, which is an afternoon of careful work |
| 91 | 2026-09-12 | **The address field stays required for home delivery even when a pin is dropped** | A courier delivers to an address, not to a coordinate — the pin adds precision on top of one, it does not replace it. Dropping a pin reverse-geocodes into the address field, which the customer can then edit, and `address_source` (#88) records which path they took. It also means a failed geocode, a denied permission or a blocked script costs the customer nothing, which is §3's rule that checkout works without the map |
| 92 | 2026-09-12 | **A customer who does not know their postal index is sent to Uzpost's own branch map — in a new tab, with the form state saved first** | `uz.post/uz/map` is a clustered national map that searches by address *and* by index and filters by branch type; it answers the one question our form cannot. Sending someone off-site in the middle of checkout is a real drop-off risk, so both mitigations are part of the decision rather than polish: **new tab**, and the checkout form written to `sessionStorage` before they leave — the same pattern the signup form already uses for its terms link |
| 93 | 2026-09-12 | **Every external credential ships as a blank `.env` variable, and the code is written as though it were set** | Kamronbek's instruction for the Google Maps key and the Telegram token, and it is already how Eskiz and Click work, so it becomes the rule for all of them. Nothing is stubbed, commented out or left half-built waiting for a secret: the feature is finished, `.env.example` documents the variable, and an empty value takes the degraded path the plan already requires — no map block, no Telegram send, a logged warning and a working page (§4's external-calls rule). **Turning a feature on is then a paste into the server `.env`, not a deploy**, and a missing key can never be the reason a page 500s |
| 94 | 2026-09-12 | **Online payment only. No cash, for delivery or for the goods** | Kamronbek's call (§19 Q13). The storefront offers Click and nothing else, and the checkout view rejects any other `payment_method` rather than falling through to a default. The disabled "Naqd pul" control is deleted rather than left looking imminent. The model keeps its `CASH` choice — removing it is a destructive migration for no gain, and the admin may need to record an exception one day — but nothing in the storefront can reach it. This also removes the cash-collection risk that Q24's partner programme was partly attractive for |
| 95 | 2026-09-12 | **We draw the size charts; the owner replaces them when he wants to** | §19 Q9 had been blocking Phase 4's carried item since it was written, on the assumption that the charts had to come from the owner. They do not: one diagram per fit — regular and oversize, which is the whole range (#70) — drawn to the design system with the four measured lines and a `SizeChartRow` table for S/M/L/XL. **The numbers are the part that must be real**, so Phase 11 verifies them against actual stock before launch; a chart that disagrees with the parcel is worse than no chart. The image is a file the owner can overwrite with no deploy (#69), so this unblocks the phase without taking the decision away from him |

| 96 | 2026-09-13 | **`SizeChart` gains a `fit`, and `resolve_size_chart` falls back to it: product's own chart → its category's → the standard chart for its cut → none** — ⚠️ **retired 2026-09-14 by #172: the fallback is resolved into the data and the column is gone** | An addition to §7, raised here rather than made silently. Without it the seeded charts are invisible on every product until the owner links one by hand, and 6a's Definition of Done — the guide shows on every product — cannot pass. Measurements are a property of the cut and the catalogue has exactly two cuts (§17 #70), so the fit *is* the right key. A product with no fit and no explicit chart still gets nothing, which is correct: a chart that might not match the garment is worse than no chart |
| 97 | 2026-09-13 | **The `Boshqa` escape is a row, not a UI option: one escape region plus a `kind='other'` district under every region** | §17 #87 requires the escape on both drawers, and an order points at a district through a PROTECT foreign key — so it has to exist as a row for `location_snapshot` to be able to freeze it. `kind` therefore takes a third value so the drawer can keep it out of the *Tumanlar* and *Shaharlar* groups instead of filing a non-district under one of them. The free text the customer types lands in a new `Order.location_note` rather than being folded into `address`, which for a branch order means something else entirely. The escape region has **no postal prefix**, and that is the mechanism that switches the region check off for it while the six-digit format check still applies |
| 98 | 2026-09-13 | **`data/regions.csv` is generated from the classifier by a script, not transcribed** | §19 Q23 said we verify it; the way to make that true is to make the mapping from source to file reproducible. `.git/build_regions_csv.py` reads stat.uz's own `soato-20_04_2022.xlsx` — parsed with the standard library, because an .xlsx is a zip of XML and §4 forbids a new dependency — and applies exactly three things by hand, each written out in the script: the postal prefixes (the one table the classifier does not contain, cross-checked against the UPU addressing sheet and the published ranges), the English names, and six spellings where the 2022 classifier predates current orthography. `.git/verify_regions_csv.py` then checks the result mechanically. The sources and the method are in `data/README.md` so the next person can re-check rather than re-trust. **The classifier is dated April 2022**; anything created or renamed since is not in it, which is what the escape is for |
| 99 | 2026-09-13 | **Cash is kept and switched off, not deleted — amending #94. Payment methods become rows** | Kamronbek's call, mid-build: *"don't remove cash. keep it but disable it. admin can turn it on if he wants."* So `PaymentOption` joins `DeliveryOption` as configurable rows (§17 #13): whether the shop takes cash is a commercial decision and a commercial decision should not need a deploy. Cash ships `is_active=False`. **An inactive method is absent from checkout rather than greyed out** — that half of #94 stands, because a disabled control reads as "coming soon" and invites the customer to wait for something that may never arrive — and the checkout refuses any method it is not currently offering rather than defaulting past it. §11's "cash is out of scope" becomes "cash is off by default" |
| 100 | 2026-09-13 | **A string JavaScript can put on the page is passed in from the template as a data attribute** | §17 #80 established that a string the site flashes at a visitor is copy wherever it lives, and it was written about Python. The same rule reaches JavaScript, which gettext cannot see at all: the heart's two labels and its failure message, the drawer's *Tumanlar* and *Shaharlar* headings, the index errors, the copied-link confirmation. A literal in a `.js` file renders Uzbek to a Russian visitor and no test catches it, which is exactly how the OTP resend label shipped (§17 #64). Where no attribute is supplied the script shows **nothing** rather than falling back to a hardcoded string |
| 101 | 2026-09-13 | **The viewer opened empty, and only rendering the page showed it** | It clones a block the page renders hidden so the measurements sit in the document for a screen reader — and the clone kept its `hidden` attribute, so the overlay was a full-screen dark panel with nothing in it. The source reads as a viewer that works. This is §17 #74's lesson again in a different costume: nothing scrolled, nothing was clipped, no control was too small, and the feature simply did not do its job. Recorded because the fix is trivial and the class of bug is not — anything that clones markup has to decide what the clone is *for*, not just copy it |
| 102 | 2026-09-13 | **Seeded reference data must survive a demo-catalogue reset** | `seed_demo_catalogue` deleted every `SizeChart`. It was written in Phase 5 when the table was empty and correct then; the moment Phase 6 seeded the charts, resetting the demo catalogue silently took the size guide away from the local site — which is precisely the "verification and development looking at different sites" problem that command was written to prevent (§17 #78). It now keeps the charts and rebuilds their rows against the new sizes. The measurements moved to `product/size_charts.py` so there is one table rather than two copies; the migration keeps its own copy on purpose, because a migration is a frozen snapshot (the same reasoning as `unique_slug`) |
| 103 | 2026-09-13 | **Uzpost's own figures, quoted — and two of them are uncomfortable** | §19 Q10 answered from uz.post directly. Ordinary parcels: **1–6 days anywhere in Uzbekistan**. "Bir Qadam" between designated branches: **1 day** from Tashkent to any regional centre, **2–3 days** between regions. Both are now quoted at checkout, on `/yetkazib-berish/` and on the confirmation. Two findings that are not copy: **Bir Qadam's branch-to-branch tariff is 15 000 so'm for the first kilogram**, +3 000 per further kilogram and +7 000 to Nukus, Termiz and Urganch — which is *exactly* our branch price, so that tier breaks even at one kilogram and loses money above it (risk #6). And Bir Qadam holds a parcel at the destination branch for **14 days**, not the month Resolution 2219 gives ordinary post — so §19 Q11's refund decision has two different clocks to reconcile depending on which service actually carries the parcel |
| 104 | 2026-09-13 | **The Eskiz SMS bodies are NOT moderated, and a test proved it** | A Phase 6 test that posted the signup form made a real call to Eskiz, which answered: *"Этот смс текст еще не прошёл модерацию."* The signup OTP therefore **does not send today**. This is §19 Q17's residual check, and it is no longer a precaution — it is a live defect that would make signup silently fail from the first minute of traffic. Phase 1b item 10 stops being a confirmation and becomes a task with a known answer: submit both bodies, changed in Phase 1a, through Eskiz moderation before launch. (The test now patches the send, because a test suite must not depend on a live gateway) |

| 105 | 2026-09-13 | **A `<select>` the drawer replaces needs its own hiding rule — `.sr-only` alone loses to `.select`** | `checkout.js` hides the native select behind the drawer by adding `.sr-only` to it. The element also carries `.select`, which sets a width; the two tie on specificity, `.select` wins, and the "hidden" select stayed **1 425 px wide and absolutely positioned** — 144 px of horizontal scroll on the checkout page at 1440, and 44 px at 375. Nothing looked wrong: the drawer worked, the form submitted, the page simply scrolled sideways. **The third time this exact pattern has cost us** (§17 #72 the nav icons, #74 the grid columns), and the lesson is the same one written down twice already — *a rule that exists to be overridden must not be able to win*. Found by measuring `scrollWidth` against `clientWidth` on the real page, which is the check `audit.py` already makes and which this phase had not yet re-run |

| 106 | 2026-09-13 | **Both delivery methods carry a region and a district; the home address field is the street and the house only** | Kamronbek's instruction, and it makes the two halves of the form one shape: everyone picks *where* from the same two drawers, and only the last field differs — a six-digit index for a post office, a street and a house for a courier. A courier needs the province and the district as much as a counter does, and a customer who picks them from a drawer cannot misspell them, which is exactly what a free-text address invites. `Order.clean` now requires region and district for both, rejects an index on a courier order, and requires an address on one; `location_text` freezes *region · district · index* or *region · district · street*, so an order record reads the same way whichever method was used. The address is also cleared server-side on a branch order — it belongs to the other half, and a stale one submitted from a hidden field must not reach the database |
| 107 | 2026-09-13 | **Neither half of the delivery form ships with a `hidden` attribute; the script hides the half that does not apply** | Both halves carried `hidden` in the markup and `checkout.js` removed it on load — so with JavaScript blocked the customer got a delivery choice and no fields at all, on the one page that most needs to work everywhere. The template comment claimed the opposite. Hiding now happens in one place, in the script, which means a script that never runs leaves a complete working form — the rule §3 already required and the markup quietly broke. Found by reading the template while moving the fields, not by any check we had |
| 108 | 2026-09-13 | **The admin's map is read-only by construction, not by configuration** | `GX.map.show()` is a separate call from `init()` rather than `init()` with dragging switched off. The checkout's map is a control a customer operates; the admin's is a picture of what they chose. Keeping them as two calls means the admin page has no code path that can move a pin, so it can never record a coordinate the customer did not drop — a property of the design rather than of an option somebody could flip later. Both still go through the `GX.map` wrapper (#27), so the provider is still one file |
| 109 | 2026-09-13 | **A layout must not assume a child the template can decide not to render** | `.pdp__gallery` became a two-column grid at 1024 — `64px minmax(0, 1fr)`, thumbnails then photograph. But `item.html` omits the thumbnail rail for a product with one photograph, so the frame became the *first* grid item and `width: min(100%, …)` resolved 100% against the **64 px thumbnail column**: a 760 px photograph rendered 64 px wide with the rest of the column empty. **Seven of the eight catalogue products have exactly one image**, so this was the normal case, not the edge case, and it had been live since Phase 5. The grid now lives on a `--rail` modifier the template adds only when it renders a rail. Found by Kamronbek looking at the page |
| 110 | 2026-09-13 | **A tap target is declared as a height, never as a negative inset** | `a.link::after { inset: -9px -4px }` gave a 27 px link a 45 px target and a `.small` 24 px link a 42 px one, which is how the product page's "Oʻlcham jadvali" link ended up two pixels short of a thumb. A hit area derived from the text size is only ever correct for one text size. It is now `top: 50%; height: 44px; transform: translateY(-50%)`, which is right at any font size; `a.card__name` keeps the inset because it can wrap to two lines and a fixed 44 px would make a *tall* target smaller |
| 111 | 2026-09-13 | **Prices and payment methods are read from their rows, never written into copy** | The footer said "Eshikkacha — 30 000 soʻm" on **every page of the site**, including the checkout page whose own form said 40 000 a few hundred pixels above it, for as long as #85 had been in effect. The terms page had the same stale figure and, worse, promised payment "naqd pulda" — cash on delivery — which has been switched off since #99. §18 #18 had closed the product and delivery pages and missed these two, which is the argument: a price written down twice is a price that will disagree with itself, and a terms page that promises a payment method the checkout does not offer is worse than a wrong number. A `delivery_tiers` context processor (cached 60 s) now feeds the footer and the terms page, and the terms' payment sentence was rewritten to say "the methods shown on the checkout page", which stays true when the owner switches one on or off |
| 112 | 2026-09-13 | **The verification harness starts its own server; it never audits whatever happens to be listening** | Two invisible things made a browser sweep lie in the same afternoon. **Django 6 caches templates even with `DEBUG=True`** — the cached loader used to be off in debug, and since Django 5.1 it is always on and relies on the autoreloader to clear it, so under `--noreload` every template edit is invisible until the process restarts; pages that had already been fixed were being measured in their previous form. And **four `runserver` processes were alive at once**, the oldest holding port 8011, so a context processor that demonstrably worked in `manage.py shell` rendered nothing in the page. `.git/serve.py` now kills whatever holds the port, starts a server, waits for it to answer and stops it again, and both harnesses call it. A check that can silently measure the wrong build is not a check |
| 113 | 2026-09-13 | **`ModelAdmin.Media` scripts run before the body exists** | Django puts them in the head with no `defer`, so `admin_map.js` looked for its element, found nothing, returned, and left an empty 320 px box — indistinguishable from a map that failed to load. It waits for `DOMContentLoaded` now. Worth remembering for every future admin script: the admin's own JS is written to cope with this and ours has to be too |

| 114 | 2026-09-13 | **`width: 100%` on a Django admin readonly field resolves to zero — and "the map exists" is not the same check as "the map is visible"** | The admin's map div was `width: 100%; max-width: 640px`. Django renders a readonly field inside a flex row, and a flex item with no content of its own resolved 100% to **0 px**: Google built its map, the DOM had exactly the children it should, every assertion passed, and the page showed an empty strip. It was caught by *looking at the screenshot*, which is the point — the check asked whether a map had been created and never whether it had a size. Fixed with `width: 640px; max-width: 100%`, and the check now measures the box as well as counting its children. The general lesson is the one worth keeping: **a check that confirms a thing was constructed has not confirmed anyone can see it** |

| 115 | 2026-09-14 | **Each language button posts its own already-translated URL; `set_language` cannot do it** | Switching language worked once and then stopped: from any `/ru/` or `/en/` page, every button reloaded the same page in the same language. The cause is a Django 5.1 change interacting with `prefix_default_language=False`. `LocaleMiddleware` now forces the **default** language on any request whose path carries no language prefix — and `/i18n/setlang/` carries none — so `set_language` always executes with Uzbek active. `translate_url()` resolves a path against the *active* language's prefix, so under Uzbek it cannot resolve `/ru/shop/` at all, gives up, and redirects to the `next` it was handed. One `next` for all three buttons therefore meant "go back where you came from" for two of them. The page now renders **one form per language**, each carrying the URL of the current page in that language — which the `languages` context processor already computes correctly, because it runs during a request where the active language does match the path. The mobile drawer had its own copy of the control and its own copy of the bug. **Nothing in the suite noticed for four phases** because the switcher had only ever been rendered, never operated; `core/test_phase6h.py` now drives it between all three languages on four pages |
| 116 | 2026-09-14 | **Every region and district ships all three of its spellings to the browser, so a dropped pin can be matched to a row** | Google names places in its own words: Chilonzor comes back as "Chilanzar District" in English and "Чиланзарский район" in Russian, while the SOATO classifier we built `regions.csv` from spells it "Chilonzor tumani". Matching on the one name the page happens to be showing would fail for the other two languages. So each row carries `name`, `name_ru` and `name_en`, and the comparison strips the words that say what *kind* of place it is (tumani, shahri, район, District) before allowing an edit distance of two. The Maps script is loaded with `language` and `region=UZ` so the names come back in the page's own language in the first place |
| 117 | 2026-09-14 | **A dropped pin fills the region, the district AND the street line — amending #91** | #91 said the pin never overwrites the address and only fills it when empty. That was right when the address was one free-text field; it is wrong now that the form has three. Moving the pin is a deliberate act by the customer, and asking someone who has just pointed at their own front door to then find their district in a list of two hundred is work the map exists to remove. All three fields stay editable afterwards. What #91 still governs is unchanged and is the important half: **the address remains required**, because a courier delivers to an address and not to a coordinate |
| 118 | 2026-09-14 | **A form re-rendered after a validation error must be put back into the state it was in, not just refilled** | Submit the checkout with a field missing and the server re-renders it with `address_source` still `map` and the coordinates still in their hidden inputs — but nothing had put the *map* back on screen, so the customer saw the manual form and their pin survived only as two numbers they could not see. Reported by Kamronbek. The fix is three lines, and the general form is worth keeping: restoring a form means restoring the state its controls were in, and a hidden input that describes a mode is state |
| 119 | 2026-09-14 | **The Maps script is `defer`, never `async` — a callback that runs before the code defining it is a bug that only appears on the second visit** | `async` runs a script the moment it arrives, which on a first visit is after our own deferred files and on every visit afterwards is straight out of the HTTP cache — *before* them. Google then called `GXMapReady`, which `map.js` had not defined yet: "GXMapReady is not a function", no map, and only for people who had been to the checkout before, which is exactly the case nobody tests. `defer` executes in document order, still without blocking parsing or first paint. Found by driving a second page load rather than a first |
| 120 | 2026-09-14 | **Where two of our rows match one of Google's names, the pin fills nothing unless the evidence separates them** | "Toshkent" matches both *Toshkent shahri* and *Toshkent viloyati* once the word *viloyat* is stripped; almost every province has a *tuman* and a *shahar* of the same name. Guessing here produces a form that looks perfectly filled in and a parcel that goes to the wrong post office, so the collision is broken on evidence or not at all: the province wins when Google said *Region*, the city wins when the name it gave for the region is also the name it gave for the locality — which happens only inside a city that is its own region — and for districts the row's own `kind` column decides, a `locality` being a city and an administrative area a district. `kind` was added in Phase 6d for the drawer's headings (§17 #87) and turns out to be exactly the right evidence here. Anything still ambiguous leaves the field empty for the customer: one tap, against a misrouted parcel |

| 121 | 2026-09-14 | **Uzbek takes a `/uz/` prefix like the other two languages — amending the §3 locked decision** | Kamronbek's call, answering §19 Q25. Uzbek was served at `/` from the start, on the reasoning that the primary market should have the clean URLs. What that actually bought was a permanent special case: **an unprefixed default language is something Django works around rather than supports.** `LocaleMiddleware` forces the default language on every request whose path carries no prefix — which is correct, since one URL must not serve three different languages — and that rule is exactly what left the language switcher one-way for four phases (§17 #115), because `/i18n/setlang/` is unprefixed too. Every language now has a prefix, that rule never fires, and `/` is free to send a visitor to their own language instead of always answering in Uzbek. **The cost was paid today rather than after launch:** every Uzbek URL changed shape, and an old one still works — it 404s inside `i18n_patterns` and `LocaleMiddleware` redirects it to the prefixed path. That redirect is a **302, not a 301**, and deliberately so: its destination depends on who is asking, and a browser that cached it as permanent would pin a visitor to one language for good. The sitemap needed no change — it was already `i18n=True` with alternates, so it simply emits `/uz/` where it used to emit `/`. `core/test_i18n.py` now asserts the new shape, that `/` leads somewhere, and that both an old unprefixed URL and the old `/item/<pk>/` link still reach their page |
| 122 | 2026-09-14 | **The catalogue-completeness check reads plural entries, not just `msgstr`** | Phase 12 added the project's first `{% blocktrans count %}`, and the test that has guarded the catalogues since Phase 4 reported it untranslated in both Russian and English while all six forms were sitting there filled in. Its parser recognised a line beginning `msgstr "` and nothing else, so a plural entry — which writes `msgstr[0]`, `msgstr[1]` … and never a bare `msgstr` — looked like an entry with no translation at all. It now collects every form and treats the entry as translated only when **all** of them are filled, so a half-written plural still fails. The general shape is worth keeping: **a checker that has only ever seen one kind of input has not been tested, it has been lucky** — this one had guarded 220 strings correctly and was wrong about the first one of a new shape |
| 123 | 2026-09-14 | **A fuzzy-stripping script rebuilds the flag line; it never deletes it** | The `.git` script that writes hand-written copy into the catalogues removes the `fuzzy` flag as it goes, and did it by dropping any line starting `#,`. gettext writes `#, fuzzy, python-format` for a string with a placeholder, so dropping the line also dropped `python-format`, and the repair attempt that followed left `#, python` behind — which msgfmt rejects outright: `keyword "python" unknown`, and `compilemessages` refused Russian and English entirely. A flag line is a **comma-separated list**, so the script now splits it, removes `fuzzy`, and writes back whatever is left (or nothing, if that was all there was). Same family as the §17 #80 defect, which matched a bare `#, fuzzy` and missed the same line |
| 124 | 2026-09-14 | **A test that asserts on translated copy pins the language; `LocaleMiddleware` leaks it** | A Phase 12 test fetched `product.get_absolute_url()` and asserted the Uzbek badge text. It passed alone and failed in the full suite, because **`LocaleMiddleware` activates a language per request and never deactivates it** — the last request of whatever test ran before leaves its language active for the rest of the process, so `reverse()` built `/en/…` and the page came back in English, correctly. The test now reverses inside `translation.override('uz')`. Worth remembering for every future test that reads copy off a page: **the active language in a Django test is a leftover, not a default**, and test order decides it |
| 125 | 2026-09-14 | **A table column whose cells have no intrinsic width gets no width** | The five distribution bars under the review average were **0 px wide at every breakpoint in every language.** The CSS was right, the percentages were right; the cell holding them was not. The bar is an empty `<span>` inside a `<td>`, so that column's max-content width is zero — and an `auto` table with `width: 100%` hands its leftover width out **in proportion to content**, which gives a zero-content column zero. Fixed by making that cell claim `width: 100%`, so it is the column that absorbs whatever the label and the count do not need. The reason no harness caught it is instructive: the bars were present, visible, correctly coloured and inside the viewport — nothing was clipped, nothing escaped, nothing was unlabelled. **An element can pass every check in the audit and still be a rectangle with no width**, which is §17 #114 in a different costume |
| 126 | 2026-09-14 | **`.sr-only` is exempt from the contrast check as well as the clipping check** | The review form produced 75 contrast findings, every one of them a `.sr-only` span inside a star label. Screen-reader-only text is clipped to one pixel and never painted, so its contrast is meaningless — and it inherits its parent's colour, which for an *unlit* star is deliberately muted. The geometry check had carried this exemption since Phase 5; the contrast check had never needed it, because until now every `.sr-only` on the site happened to sit inside something with body-coloured text. Exempted now. A harness that reports 75 findings nobody will act on is worse than one that reports none: **the cost of a false positive is that the next real finding is skimmed past** |
| 127 | 2026-09-14 | **The audit fixture creates every conditional state, or the markup behind it is never judged** | The rating link under a product title is 22 px tall and had been a failing tap target from the day it was written — but it only renders on a product with approved reviews, and until this phase no product in the dev database had any, so **the audit had swept it twenty times and never once loaded it.** Same for the whole reviews section and the review form. `audit_fixture.py` now builds the state as well as the account: a delivered order, three approved reviews with a photograph on one, and a pending review that must stay invisible; `audit_live.py` reads the ids back out of `fixture.json` and sweeps two more pages. The tap target is fixed the §17 #110 way — a fixed 44 px height, not a negative inset. The rule: **a block that renders only under a condition is unaudited until the fixture creates that condition**, and "0 findings" means nothing about markup the sweep never reached |
| 128 | 2026-09-14 | **A verification fixture is idempotent on state, not on creation — and never deletes a row something else points at** | Two ways the Phase 12 fixture lied on its second run. It **skipped rows that already existed**, so once `interact_live.py` had approved the moderation queue through the admin, the deliberately-pending review stayed approved and the "a pending review is invisible" check would have failed for entirely the wrong reason; it now *resets* each review to the status it is supposed to have. And it did `Cart.objects.filter(user=user).delete()` to clear the shopping cart — but an `Order` holds a foreign key to the cart it was placed from, so that cascaded away the delivered order the review form is driven against, which is why the order id changed on every run. It deletes only the open cart now. Also fixed here: both harnesses reconfigure stdout to UTF-8, because a finding whose detail was Uzbek crashed the report on cp1252 **after** a five-minute sweep had finished — the work was done and the answer thrown away on the last line |
| 129 | 2026-09-14 | **A number inside a sentence is a plural, and the rule is the language’s, not ours** | `%(n)s yulduz` was a plain string. Uzbek does not inflect after a numeral, so it read correctly in the language it was written in and **wrongly in the other two**: the distribution under every reviewed product printed “1 звёзд” and “1 stars”, five rows at a time, and so did the label on every star of the rating control. It is a `blocktrans count` now, with Russian’s four forms and English’s two written by hand. Two things follow from it. A plural needs a **number**, so the rating radios iterate integers supplied by the view instead of the characters of the string `"54321"` — a template loop over a string yields text, and text cannot be pluralised. And the catalogue tests were not enough on their own: they check that every form is *filled*, which says nothing about whether it is the *right* form, so `core/test_phase12.py` now renders each one and reads it |
| 130 | 2026-09-14 | **The tutuq belgisi is U+02BC; U+02BB is only ever part of a letter** | Uzbek Latin uses two modifier letters that look almost identical and are not interchangeable. U+02BB, the turned comma, **builds the letters oʻ and gʻ**. The glottal stop in maʼlumot, sanʼat, maʼno is the tutuq belgisi, **U+02BC**. The catalogue had 225 correct uses of the first and five places where it was standing in for the second — in about.html, terms.html twice, `user/views.py` and Phase 12’s own photo hint, which is to say across three phases, because Phase 12 got it by copying the spelling of its neighbours. That is the part worth keeping: **a wrong character propagates by imitation**, and nothing in four phases of tests could see it. Fixed in all five, with the Russian and English carried onto the new msgids rather than re-guessed (their text does not change — the mark exists only in the Uzbek), and now asserted: the turned comma may only ever follow an o or a g, in any of the three catalogues |
| 131 | 2026-09-14 | **A limit that exists only in the HTML is not a limit** | The review textarea carried `maxlength="2000"` and the field behind it was a bare `TextField`, so the cap held for anyone using our page and for nobody else — a POST does not have to come from our form, and `DATA_UPLOAD_MAX_MEMORY_SIZE` would have allowed about 2.5 MB of text onto a public product page. What makes it worth a decision rather than a fix is that the correct treatment was three lines away: `MAX_PHOTOS` is checked server-side and its comment says in as many words that the `multiple` attribute is a convenience and not a limit. The number now lives in the view as `MAX_TEXT`, the template renders `maxlength` **from it**, and a test asserts the two agree — §17 #111 again: a number written down twice will eventually disagree with itself |
| 132 | 2026-09-14 | **A file’s size tells you nothing about a picture’s size** | The photo pipeline refused anything over 12 MB and thought that was the ceiling. It is not: a 12 000 × 12 000 PNG of one flat colour is **140 KB on the wire and 432 MB of pixels**, and it walks straight past a size check. Pillow does not stop it either — measured rather than assumed: `MAX_IMAGE_PIXELS` only *warns* at 89 Mpx and raises at twice that, so 144 megapixels per file, four files per submission, was reachable by any customer with a delivered order. The dimensions are read from the header now, **before `verify()` and before anything decodes a pixel**, and refused above 50 Mpx. Found in the same pass: `ALLOWED` listed HEIF and HEIC, which this Pillow has no codec for, so an iPhone upload would have been refused with “that is not an image” rather than anything true. **A format we accept but cannot decode is a promise we cannot keep** — the list is now checked against Pillow’s own registry by a test, and AVIF, which it can open, was added |
| 133 | 2026-09-14 | **A refusal re-renders the form; it never redirects away from it** | Extends §17 #118, which says a form re-rendered after an error is put back into the state it was in. The review form was not re-rendered at all: every refusal — wrong rating, five photographs instead of four — was a redirect, which discards the state rather than restoring it. A customer who wrote three hundred words and attached one photograph too many got an empty form and a sentence. The rating and the text come back now; the file input cannot, because no browser lets a page refill one, and that is worth saying out loud rather than leaving as a silent gap |
| 134 | 2026-09-14 | **Every write on the site is rate limited, and most of all the one that accepts uploads** | The heart, the login, the signup, all four OTP flows and the password reset each take a limit from `core.ratelimit`. The review POST was the only write without one — and it is the only endpoint on the site that accepts files: four uploads of up to 12 MB, each decoded and re-encoded by Pillow. Because the eligibility check runs *before* the photographs are read, a repeat submission for an already-reviewed product is cheap; a submission whose photographs are refused is not, and it can be retried forever. Ten per hour per user, which no real customer will ever meet: reviewing ten delivered orders in an hour is not a thing that happens |
| 135 | 2026-09-14 | **A notification composed inside the transaction that creates its subject sees a half-built row** | `notify_review` says “a photograph is attached” when the review has images. It never said it. `create_review` writes the review and *then* its photographs, both in one transaction, so at the moment `post_save` fires there are no images yet — and the owner was never told about the one kind of review that most needs a human to look at it. `core.telegram.notify` already deferred the **send** to commit; what had to be deferred was **reading the row**. The signal queues the whole composition now. The general form: deferring the delivery of a message does not defer the evaluation of it, and inside a transaction those are different moments |
| 136 | 2026-09-14 | **`choices` is not a constraint** | `Review.rating` carried `choices=[(1..5)]`, which Django enforces in forms and in the admin and nowhere else — nothing that writes through the ORM validates it. That column is the input to `Product.rating_avg`, a public number on a public page, so a single six-star row would have skewed it with nothing anywhere to notice. There is a `CheckConstraint` now, in its own migration, and every existing row already satisfied it. The view still validates the rating, because the customer needs a sentence rather than an `IntegrityError`; the constraint is the guarantee behind it |
| 137 | 2026-09-14 | **Opening a file for writing destroys it before the write is attempted** | This is the second time a script has destroyed this plan, and the mechanism was cruder than the first. `io.open(path, "w")` **truncates the file as it opens it**, so when the encode of the text raised — a lone surrogate written into one of the rows above — 257 KB of plan had already become zero bytes, and the traceback was about Unicode, which is not what had just happened. It was recoverable only because it was committed. §17 #82 added a version assertion after the *first* loss; that would not have helped here, because the guard ran and passed and the loss came afterwards. Plan writes now go through `.git/planfile.py`, which **encodes first** (so a bad character raises while the file is still on disk), writes to a temporary file beside it, and `os.replace`s it into position — atomic on Windows and on POSIX, so the file is either the old one or the new one and never an empty one. It also refuses to write anything under 200 KB or anything that does not still look like the plan. Two losses, two different mechanisms, one rule worth keeping: **a guard that runs before the dangerous operation does not protect the operation itself** |
| 138 | 2026-09-14 | **A month after a day number takes the alternative form, which is `E` and not `F`** | The date under every Russian review read **“14 Сентябрь 2026”** — the nominative, which is what you call the month, not how you date something in it. Correct Russian is “14 сентября 2026”, and Django ships the alternative form for exactly this: `E` reads `MONTHS_ALT`, `F` reads `MONTHS`. It is the kind of mistake that tells a reader the site was translated rather than written, which is precisely what §3 says not to let happen. Checked in all three languages before changing it, because `E` falls back to the English msgid where a locale has no alternative: Uzbek and English are byte-for-byte unchanged. One template on the whole site formats a textual month, and it is this one, so the fix is Phase 12’s alone |
| 139 | 2026-09-14 | **The first `<fieldset>` on a site finds two things at once: the UA’s box, and blockification** | The rating control looked wrong in the screenshot and there were two separate causes under it, neither visible in the markup. **One:** nothing in `base.css` ever reset `fieldset`, because nothing had used one until now, so the browser drew its default **2 px groove border and 12 px of padding** around the stars — an outlined box in a design where no other field has one. **Two:** `.stars--input` is `display: inline-flex`, and `.field` is a **flex** container, which blockifies its children: the row became `display: flex`, stretched to the full field width, and `flex-direction: row-reverse` then packed the five stars against the **right** edge. `align-self: start` makes it shrink-wrap again. The reset also drops `min-inline-size: min-content`, the other half of the UA default and a well-known overflow trap inside flex and grid. Both were invisible to every automated check the project has — nothing was clipped, nothing escaped the viewport, nothing was unlabelled, the contrast was fine. **They were found by looking at a picture**, which is the third time in two phases (§17 #114, §17 #125). Folded in while there: the file input was the one control on the site still wearing the browser’s own grey button, restyled through `::file-selector-button` so the real control keeps working with JavaScript off |
| 140 | 2026-09-14 | **A spacing token is a guess about the header; the header’s height is a token of its own** | `.pdp__reviews` carried `scroll-margin-top: var(--s-8)` — 64 px, against a header that measures **69 px**. So tapping the rating, which is the one link the whole reviews section exists to serve, scrolled its heading five pixels *underneath* the sticky nav, at every width and in every language, and had done since the day it was written. The rule was present and looked deliberate, which is why nobody had measured it. There is a `--nav-h` token now, `.nav` pins its own `min-height` to it so the token cannot drift from the thing it describes, and the scroll margin is `calc(var(--nav-h) + var(--s-4))`. `interact_live.py` clicks the rating at 390 and 1440 and asserts the heading lands below the nav, because **a rule being present says nothing about it being enough** |
| 141 | 2026-09-14 | **The staff panel may assume JavaScript; the storefront still may not** | Kamronbek’s call, asked before 7a was built. §4 says everything works with JavaScript off, and that rule earns its keep on a storefront where a customer’s browser is somebody else’s choice. The panel is a tool one person uses on a known device, and the things that make it usable on a phone — saving without a reload, dragging images into order, checking an image before a 30-second upload — are JavaScript or they are nothing. So the panel is the exception, and **only the panel**. Where degrading costs nothing it still degrades: the status control is a real form with a real submit button that the script upgrades, so it works either way; that was free, and free is the test |
| 142 | 2026-09-14 | **The status trail is a table of its own, not `LogEntry`** | The Definition of Done says status changes are logged with who and when. Django already has ``django.contrib.admin.models.LogEntry``, and it is the wrong tool: it records a free-text change message against a generic object, which answers "somebody edited this" and cannot answer "every order that went from paid to cancelled last week" without parsing prose. `panel.OrderStatusChange` stores the two statuses as **plain text rather than as choices**, so renaming a status label in a year cannot rewrite what happened, and `changed_by` is SET_NULL so a staff member leaving does not take the history with them. More important than the table: **one function writes it**, `panel.services.set_status`, and the Django admin now routes through it too — it could change a status from its list view and did it silently, which is the hole the log exists to close. The function locks the row, because two people on two phones looking at the same order is the ordinary case in a shop |
| 143 | 2026-09-14 | **A phone number is stored formatted, so a search for one has to compare digits** | `normalize_uz_phone` stores the canonical `+998 90 122 00 07` — **with spaces** — and the panel’s search box is where a staff member types the number they are reading off a parcel. A plain `icontains` therefore matched almost nothing: "901220007" is not a substring of anything with spaces in it, and neither is any other grouping a person might use. Both sides are reduced to digits before they are compared. Worth remembering wherever a formatted value is stored: the format is for reading, and a search is not reading |
| 144 | 2026-09-14 | **A shared partial needs its context asserted on every screen that includes it** | The order row is included by the dashboard and by the list. The list passed it the status options; the dashboard did not, so its five most recent orders each rendered a `<select>` with **nothing in it** — a box with an arrow and no text — on a page that returned 200 and passed its tests. Found in a screenshot, which is now three phases running (§17 #114, #125, #139). The test that would have caught it asserts the row’s requirements on *every* screen that includes it, which is the general form: **a partial with a required context variable has as many call sites as it has includes, and each is a separate chance to forget** |
| 145 | 2026-09-14 | **A control must not contradict the badge sitting next to it** | An order waiting for payment is in a status the panel will not let anybody set by hand, so nothing in the status dropdown matched it and the browser did what browsers do — showed the first option. The result was a row whose badge read "Toʻlanmoqda" beside a dropdown reading "Toʻlangan": two different answers to the same question, side by side, on the screen somebody packs parcels from. The select now carries a disabled, valueless first option naming where the order actually is, so moving it is a deliberate choice rather than something that looks like it has already happened |
| 146 | 2026-09-14 | **Two functions that are each atomic are not atomic together** | The product screen writes a product and then its size grid. Both are `@transaction.atomic`, which is right — either can be called on its own — and it is exactly what made the view wrong: the product **committed**, the grid was then refused for having no prices in it, and the catalogue was left holding a live product with no sizes. Unbuyable, and visible to customers. The view wraps both in one transaction of its own. The general form is worth keeping because it reads as if it should be fine: **`atomic` composes by nesting, not by adjacency** — two calls in a row are two transactions, and the second failing does not undo the first |
| 147 | 2026-09-14 | **A size with no price is a size the product is not made in** | The grid could have treated a blank price as zero, or as "leave this one alone". It deletes the variant instead, because that is what clearing a row **means** to the person clearing it: the size should stop appearing on the product page. The exception is a variant somebody has already ordered — a cart line points at it, so it cannot go — and that one is switched off and emptied rather than deleted. Losing the record of what a customer actually bought in order to tidy a form is not a trade worth making, and it is the kind of delete that looks harmless until the order page starts raising |
| 148 | 2026-09-14 | **`width` on an input counts its padding, so a number field can be too small for its own number** | Every price on the panel's catalogue list rendered cut in half — "18500" where the price was 185 000 — and every price in the size grid did the same. Two causes, one shape. The list's field was `width: 8ch` on a control with 16 px of padding each side: `width` is border-box, so eight characters of box is about four characters of room. The grid's was an **auto table**, which hands its width out in proportion to content, and the widest thing in the price column is an empty input — so the column with the numbers in it lost to the column headed "Sotuvda". That is §17 #125 for the second time, in a different table. Panel number fields now carry less padding and a width measured against what they hold, and the grid's columns are declared rather than guessed at. **Both were found by looking at a screenshot**, and neither would have failed any assertion: the value was in the DOM, correct, and unreadable |
| 149 | 2026-09-14 | **One endpoint may edit five tables only because a table says which fields** | Regions, districts, delivery tiers, tags and size charts are all "a list of rows with a few fields editable in place", and writing five near-identical endpoints would have been five places for the same mistake. There is one, and what makes it safe is the allowlist in `panel/reference.py`: a model, a field name and a reader for the value, and **anything not named there cannot be written whatever arrives in the POST.** Without it, an endpoint that takes a model, a field and a value is a way to set anything on any row — a delivery price to zero, a product to inactive. The most load-bearing omission from the list is `Region.code`: it is the SOATO code that ties the row to the classifier `data/regions.csv` was built from, and editing it would detach the two quietly |
| 150 | 2026-09-14 | **A moderation queue shows the photographs at a size somebody will actually look at** | The queue is the whole reason a stranger’s photographs are safe on a public product page (§17 #25), and the only thing it has to get right is that a human really looks. So the images are `min(260px, 62vw)` and scroll sideways, not 72 px thumbnails in a row. **A moderation screen with thumbnails is a screen where everything gets approved**, because nobody squints at a thumbnail before tapping a green button — and the failure is invisible, since the queue empties either way. A test asserts the size, which is an odd thing to assert until you notice that the alternative is a screen that looks fine and does nothing |
| 151 | 2026-09-14 | **Flex children shrink before they wrap, so a row of text fields is not a row on a phone** | Three name inputs in a `.row` at 390 px showed about four characters each — "Boxy" as "Box". This is §17 #148 for the third time and the third distinct cause: there it was `width` counting its own padding and an auto table handing a column less than its content, here it is that a flex item’s default `min-width: auto` loses to `flex-wrap` — items shrink to nothing before the line breaks. `.row--fields` is a grid of one column until 640 px. The pattern behind all three is worth stating once: **a field narrower than its own content fails no assertion.** The value is in the DOM, correct, and unreadable, and only a screenshot shows it |
| 152 | 2026-09-14 | **A disabled control is not in its form's data, so the panel's most-used button had never once worked** | `panel.js` set `select.disabled = true` and then built `new FormData(form)`. A disabled field is excluded from a form's data set, so the POST carried no `status` at all: the endpoint answered 400, the alert said "this status cannot be set by hand", and the fall-back full post was just as empty because the select was still disabled. Every one of the phase's tests passed, because they post to the endpoint directly. Build the body first, and re-enable before any `form.submit()`. **The rule: a control the script disables is a control the script has already read.** | `static/js/panel.js` |
| 153 | 2026-09-14 | **The panel is unreachable for a staff account whose phone was never verified** | `PhoneVerificationMiddleware` exempts `/admin/`, `/static/` and `/media/` by path prefix. The panel is language-prefixed (`/uz/boshqaruv/`), so no prefix matches, and `phone_verified` defaults to False — which is what every `createsuperuser` account has. The owner on a phone is redirected to the OTP screen forever. **Not changed here**: §4 says auth is not changed alone. The audit harness had been setting `phone_verified = True` on its throwaway superuser since Phase 6, which is why nobody had met it. | raised with Kamronbek |
| 154 | 2026-09-14 | **A field that is not a search box gets a length its column can honour** | `reference.set_field` wrote straight to Postgres, so a pasted name longer than `varchar(60)` was a 500 and the screen said only "could not save". Now `set_field` reads `max_length` off the model field and refuses with a sentence, and every reference input carries a matching `maxlength`. The same guard is on the product form's text fields. | `panel/reference.py`, `panel/catalogue.py` |
| 155 | 2026-09-14 | **A tile's number and the list behind it count the same orders** | The dashboard's "to pack" counted `paid` + `processing` and linked to `?status=paid`, so the number promised more rows than the list showed; "running low" counted variants and opened the unfiltered catalogue. The orders filter now accepts a comma-separated status and the products list a `low=1`. **A number with a link is a promise about what is behind it.** | `panel/views.py`, `boshqaruv/dashboard.html` |
| 156 | 2026-09-14 | **An order's three numbers have to add up on the screen** | `CartItem.price_stat` is the price of ONE, frozen at checkout; the order's total is the sum of price × quantity. The detail page printed the unit price beside "× 2" and the total below, so 189 000 + 40 000 read as 418 000. The line now shows its own total, with the unit price in the label. | `panel/views.py`, `boshqaruv/order.html` |
| 157 | 2026-09-14 | **An in-place editor without visible labels is a guessing game** | The tag rows, the region row and 221 district rows each carried three name fields with `aria-label` only — three identical boxes in a column at 390 px, and only the Cyrillic one identifiable. The delivery tiers on the same screen had labelled theirs all along. Every field carries a visible label now. **`aria-label` names a control for a screen reader; it does not label it for the person looking at it.** | `boshqaruv/settings.html`, `boshqaruv/regions.html` |
| 158 | 2026-09-14 | **A badge says what a thing IS; the button says what you are about to do** | Approving a review copied the button's own text into the badge, so the card read "Tasdiqlash" — approve — where "Tasdiqlangan" belongs, and the rating line lost its "ta" because the script was assembling that sentence too. Both come from the server now, through the same `{% trans %}` string the template uses. | `panel/views.py`, `static/js/panel.js` |
| 159 | 2026-09-14 | **A string typed into a .js file cannot be translated** | Eight sentences lived in `panel.js` — "Saqlanmadi", "Yuklanmadi", the four upload refusals — on a panel read in three languages (§4). They are written in `panel/templatetags/panel_i18n.py` now and handed to the script as one `json_script` block. A dangling `select.dataset.error` read, which nothing ever set, was the evidence the intent had been there and had not been finished. | `panel/templatetags/panel_i18n.py` |
| 160 | 2026-09-14 | **A table with a fixed layout is sized for its data; its headings are allowed to wrap** | The size grid clipped "Oʻlcham" into "Narx" at 5ch. Widening that column to 8ch fixed the heading and put a six-digit soʻm price in a 67 px box — §17 #148 for a fourth time, self-inflicted in the same edit that fixed the first one. The fix is not a better set of numbers: the headings are `overflow-wrap: anywhere` at `--fs-xs` so nothing can clip again, and the price column is the `auto` one, because it holds the longest value. Measured, not eyeballed, in three languages at 360/390/768. | `static/css/panel.css` |
| 161 | 2026-09-14 | **An expanded tap area is an overlay, never padding** | The panel's inline links were 18–25 px tall, the tap-to-call number in the Definition of Done among them. Padding an inline-flex link to 44 px moved its underline to the bottom of the padded box; an absolutely positioned `::after` adds the hit area and changes no layout at all. Every control on the products row is now hit-tested after the change, because an expanded area can steal its neighbour's taps. | `static/css/panel.css` |
| 162 | 2026-09-14 | **`Size` had no ordering, and the panel's most important grid is built from it** | `Variant` orders by `size`, so the storefront was fine; `Size.objects.all()` had no `Meta.ordering` at all. Postgres may return an unordered scan in any order and moves a row it has updated, so the size/price/stock grid was one edit away from coming back S, XL, M, L. `ordering = ['id']` + migration 0018 — the order everything else already assumed. | `product/models.py`, migration 0018 |
| 163 | 2026-09-14 | **The panel had never been through the audit the storefront gets** | `audit_live.py` signs in as a customer and lists storefront paths, so eleven staff screens shipped without one sweep. `audit_panel.py` is its sibling: same checks, imported from `audit.py`, staff session. First run: **423 findings**. Three were defects in the checks themselves — a meta-description demanded of a `noindex` page, a file input judged instead of the label that drives it, a caption judged as a control — and fixing those uncovered a real one on the storefront: the review form's five star labels are the control and were 30 px targets (§17 #127 again). | `.git/audit_panel.py`, `.git/audit.py` |
| 164 | 2026-09-14 | **A list the owner has to ask a developer to extend is not a list he owns** | `Tag.kind` and `Product.print_method` were `TextChoices`: adding a value meant a migration, which is the thing the panel exists to avoid (§9 Phase 7 items 7–8). Both are tables now — `TagKind` and `PrintMethod` — seeded by migration 0019 with exactly the values the code held, and swapped through a temporary column so no tag and no product lost what it had. `Product.fit` was deliberately NOT among them — and a day later he said otherwise, so it is gone entirely (#172). | `product/models.py`, migration 0019 |
| 165 | 2026-09-14 | **Reference rows that nothing points at can be deleted; rows an order points at cannot** | Tags, tag kinds, print methods, categories and size charts gained a delete button. Regions, districts and delivery tiers did not, and the reason is that an order points at all three — the history of where a parcel went is not something a tidy-up gets to remove. Of the five, two are `PROTECT`ed by the database (a kind with tags on it, a method a product is marked with) and refuse with a sentence rather than cascading. | `panel/reference.py` |
| 166 | 2026-09-14 | **A number field is `type="number"`, and the server refuses what the browser would have** | The price and stock boxes were `type="text"`, so "wqe" could be typed into a price and "sa" into a stock — and `_int` turned the second one into **0**, which took the size off sale silently. The boxes are number inputs now (spinners suppressed: a scroll over a focused one changes it), and `_count` refuses a non-number instead of rounding it down to nothing. **A count somebody mistyped is a question, not a zero.** | `panel/catalogue.py`, `boshqaruv/product_form.html` |
| 167 | 2026-09-14 | **A refused save gives back what was typed** | One wrong price emptied a form somebody had spent ten minutes on: the view re-read the row from the database and rendered that. It re-renders the POST now — §17 #133 on a form ten times longer than the review box that finding came from. | `panel/views.py` |
| 168 | 2026-09-14 | **A button that cannot change anything is not on the screen** | The moderation queue offered "Tasdiqlash" on an already-approved review and "Rad etish" on a rejected one. Both are rendered and the one that does not apply is hidden, so the script can swap them when the other decision is made without a reload. | `boshqaruv/reviews.html`, `static/js/panel.js` |
| 169 | 2026-09-14 | **The language switcher belongs in the header** | It was at the bottom of the footer, on a page somebody has to scroll to the end of. It is in the header now, as two-letter codes in a pill — there is room for six characters beside the cart and not for "Oʻzbekcha" — and hidden below the desktop breakpoint, where the drawer carries it and the header row already holds five controls at 390 px. One partial (`partials/_lang.html`) rather than the three copies it was heading for. | `partials/_lang.html`, `partials/_nav.html` |
| 170 | 2026-09-14 | **The Uzbek name is the source, so it cannot be cleared** | A size chart whose name had been emptied put an empty `<h2>` on the public size-guide page — found by `audit_live`, not by a person. `set_field` refuses a blank `name` (ru and en may be blank; they fall back), and the template no longer renders a heading it has nothing to put in. | `panel/reference.py`, `core/size_guide.html` |
| 171 | 2026-09-14 | **A sort order for four rows is a decision that buys nothing** | `TagKind` and `PrintMethod` carried an `order` column and a "Tartib" box, and it was the *first* field on the create form: a number with no obvious right answer, standing between the owner and adding a print method. Both tables have four rows. Both order by `id` now — oldest first, the order he added them in — and the box is gone from the row partial, the create partial, the allowlist and the Django admin. Kamronbek: *"no need to order them. there are only few, so order doesn't matter."* | `product/models.py`, `panel/reference.py`, migration 0021 |
| 172 | 2026-09-14 | **Qolip is gone. A cut is something you say with a tag** | This reverses §17 #70 and retires #96, on Kamronbek's word: *"i decided to remove qolip completely. this is just useless. admin can indicate by tags if it is oversize or slim and etc."* `Product.fit` and `SizeChart.fit` are dropped. Two fixed choices had been buying a select on the product form, a select on every size chart, a column on two tables, a spec row on the product page and a third cut that would have been a migration — while the tag system already says *oversize* or *slim* at any value he likes, with no schema behind it. **A size chart is now a name and a picture.** `resolve_size_chart` loses its third step and is the product's own chart → its category's → none; migration 0020 writes the resolved chart onto every product that was relying on the fallback first, so nothing on the shelf lost its size guide. | `product/models.py`, migrations 0020/0021, `panel/`, `product/item.html` |
| 173 | 2026-09-14 | **A data migration and a schema change on the same table are two migrations** | The first draft wrote the resolved charts and dropped the columns in one file. Postgres refuses to `ALTER TABLE` a table carrying pending deferred trigger events, so it raised `ObjectInUse` — **the moment there was a single row to update.** 381 tests passed it, because a test database is built by migrating from empty: no rows, no writes, no trigger events. Django wraps each migration in one transaction, so two files are two transactions and the schema change starts clean. The broader lesson is the one Phase 4 already learned: a data migration that has only ever run against an empty table has not been tested. `.git/verify_qolip_migration.py` replays this pair against a scratch database seeded to look like the live catalogue, forward, backward and forward again. | migrations 0020/0021, `.git/verify_qolip_migration.py` |
| 174 | 2026-09-14 | **A circle is made by construction, not by arithmetic** | The header's active language read as an oval: a minimum width plus horizontal padding gave "uz" a box wider than it was tall, and no amount of tuning the padding makes that reliable across three languages and two scripts. It is a fixed square with the minimums cleared and no padding, so it is round at any font size, and the pill around it gained padding of its own so the fill no longer touches the border. The search field went from 440 px to 360 to give it the room — search is the main job on this site, but at 440 the header read as one long box with three icons crowded after it. | `static/css/components.css`, `static/css/pages.css` |
| 175 | 2026-09-14 | **A probe that cannot be taken is not a probe that failed** | `audit.py` skips an element whose box is off-screen, because it cannot be hit-tested — but not one whose 44 px *band* runs past the window. A 26 px switch sitting seven pixels above the fold is entirely visible; the probe below it lands at y = 881 in an 880 px window, `elementFromPoint` answers null, and a control with a perfectly good target is reported as too small. It moved between widths and languages on identical code, which is what sent it to be measured rather than fixed: **which control sits near the fold is a function of how long a word is in each language.** The guard now covers the band. This is the fourth defect found in the checks themselves (§17 #163), and they are worth finding: a sweep that cries wolf is a sweep nobody reads. | `.git/audit.py` |
| 176 | 2026-09-15 | **A button that signs you out says so before it is pressed** | "Joriy parolni eslay olmayapman" on the account screen logs the user out and sends them into the phone-OTP reset, because that flow requires being anonymous. Nothing said so. Somebody who cannot remember their current password is not expecting to lose the page they are on as well, and a warning after the fact is not a warning. The line sits with the button rather than at the bottom of the card, because a note somewhere else on the page is a note nobody reads in time. | `user/account_settings.html` |
| 177 | 2026-09-15 | **Sign in and sign up are one centred column, like every other screen in that flow** | They were the only two pages still using the two-column `.auth` layout: from 1024 px the form sat in the left half and the brand mark filled the right, which pushed the one thing on the page with a job off to the side and made a decoration the largest object on screen. Every other screen in the same flow — the OTP step, the three reset steps, both payment results — was already `auth--narrow`. The mark is in the header on every page; it did not need repeating at 220 px. `.auth__art` and the desktop grid are deleted rather than left unused. | `user/login.html`, `user/signup.html`, `static/css/pages.css` |
| 178 | 2026-09-15 | **"Hisobot", not "Bugun" — and tiles named for what they are** | Kamronbek: *"bugun doesn't mean anything and that page is dashboard."* He is right, and it is worse than meaningless: half the screen is the week's takings, the moderation queue and the parcels still to pack, none of which is about today. Three tiles took his words too — *Yigʻiladi* → **Jarayonda**, *Yoʻlda* → **Yetkazilmoqda**, *Sharhlar navbatda* → **Yangi sharhlar**. The tiles that really are daily kept "Bugungi". Russian and English are written, not translated: *Сводка* / *Overview*, because that is what a shop's back office calls this screen in each language. | `boshqaruv/base.html`, `boshqaruv/dashboard.html` |
| 179 | 2026-09-15 | **"Running low" is defined once, on the model, or the tile and its list disagree** | Three screens asked the question and three queries answered it: the dashboard tile, the list of sizes under it, and the products list the tile links to. Kamronbek asked for a rule — *on sale, five or fewer* — and a rule written three times is a rule that drifts, which is §17 #155 waiting to happen again. `Variant.objects.running_low()` is now the only definition: `available` AND the product's `is_active` AND `stock <= LOW_STOCK`, with the threshold on the model because it is a fact about the catalogue and not about the panel. **Zero is included on purpose** — a size on sale with nothing behind it is the most urgent row on the list, not an excluded one — and a size he has switched off never appears, so the first screen he sees each morning stops filling with stock nobody is waiting to sell. | `product/models.py`, `panel/views.py` |
| 180 | 2026-09-15 | **Three states on a size pill, and the worse one wins** | Red already meant "nobody can buy this" — off sale, or nothing left. Amber is new and means "still selling, nearly gone", which is a different fact the owner acts on differently: red is a size missing from the shop today, amber is a reprint to order this week. A size that is both wears red, because the worse fact is the one to act on; the template picks one class rather than stacking them, and the inline save answers with `purchasable` **and** `low` so the script paints what the server decided instead of deciding for itself. | `boshqaruv/_product_row.html`, `static/css/panel.css`, `static/js/panel.js` |
| 181 | 2026-09-15 | **A sweep that signs in has never seen the pages you can only reach signed out** | `audit_live.py` opens one browser context, signs in through the real form and audits everything from inside it. `/login/`, `/signup/` and the reset screen were in its page list — and every one of them redirects an authenticated visitor to `/account/`. The redirect answers 200, so nothing ever failed: the account page was swept three extra times under three wrong labels, and **four phases of clean sweeps had never once looked at the sign-in page.** They now run in a second context with no session in it, and a page that answers by sending the sweep somewhere else is a `redirected` finding rather than a silent substitution. Fifth defect found in the instrument rather than by it (§17 #163, #175) — and the most expensive, because this one was hiding whole screens rather than inventing findings. | `.git/audit_live.py` |
| 182 | 2026-09-15 | **A legal document is written whole, once per language — not cut into the catalogue** | A legal text is read, reviewed and amended as one piece. In a `.po` file it becomes a couple of hundred fragments, each of which falls back to Uzbek on its own whenever its source sentence changes (§17 #63), so a Russian reader could get a contract that changes language mid-paragraph and nobody reviewing the catalogue would ever see the document. So nine files, `templates/legal/<doc>.<lang>.html`, inside one shared `legal/document.html`. **An exception to §4's "everything through `{% trans %}`", agreed with Kamronbek** — the page around the text (title, contents, history, buttons) still goes through gettext. Uzbek is authoritative, because the E-commerce Law wants contract terms in the state language; the Russian and English files say so at the top, and a missing translation falls back to the Uzbek file. Tests hold the three languages of each document to the same sections in the same order | `core/views.py`, `templates/legal/` |
| 183 | 2026-09-15 | **A figure a legal page states is read from the code that enforces it** | Nine files would state every period nine times, and a number written twice eventually disagrees with itself (§17 #111). `core/legal.py` holds the facts that are policy — the 15 000 kept, the refund, exchange and claim periods, the hold range, the delivery deadline — and reads the rest from where the code keeps them: the OTP lifetime and attempts, the review limits, the guest-cart age, the cookie lifetimes, the rate-limit ceiling, the log retention. Prices are the `DeliveryOption` rows and payment methods the active `PaymentOption` rows. Two values had no single home and got one: `GUEST_CART_DAYS` (now the prune command's default) and `MAX_WINDOW` (an AST scan fails if any `is_rate_limited` call counts longer than the hour the policy promises). **None of these is a panel setting, on purpose**: changing one changes terms a customer agreed to, so it lands with a new `VERSIONS` row in the same commit | `core/legal.py`, `core/templatetags/legal_tags.py` |
| 184 | 2026-09-15 | **The seller is named by registered name, address and contacts — no tax number, no bank details** | Kamronbek's answer to Q12 and his choice of block. The E-commerce Law requires an offer to say who it is from, and the domain registration record gives the registered name — **Boboyev Abdurahmon Furqat oʻgʻli** — and an address in Qoʻqon; GRAPHIX stays the name the shop uses everywhere else. The tax number, the personal number, the account and the MFO are on no public page, and a test fails if any of those labels appears in any language. The record's postal index is left out because it cannot be right (Q28), and the legal form is not stated until it is confirmed (Q27) | `core/legal.py` |
| 185 | 2026-09-15 | **A wrong size is exchanged at the customer's cost both ways; a defect is at ours** | Kamronbek's choice. The Consumer Protection Law gives ten days to exchange goods of proper quality (art. 18) and does not make the seller pay postage for a size the customer picked; paying it would make every exchange on the 15 000 tier a loss. Unworn, unwashed, labels on, and write first; if the size is gone the price is refunded. A defect is the seller's fault: six months to claim where no warranty is set (art. 13), a replacement within seven days (art. 14), and every delivery cost is ours | `core/legal.py`, `templates/legal/` |
| 186 | 2026-09-15 | **"Resolution 2219" is the Postal Service Rules' registration number, and a branch holds a parcel 14 days to a month** | The plan called it "Cabinet of Ministers Resolution 2219" from v2.1 on. 2219 is the Ministry of Justice registration number (18.04.2011) of the Postal Service Rules, and it is what a legal page has to cite. What the plan took from it stands — an uncollected item goes back to the sender at the sender's expense, and storage may be charged after the second notice — but the holding period is not one month for everything: a month for an ordinary parcel, 14 days on Bir Qadam (§17 #103). **The pages state the range rather than promise the longer figure**, until §19 Q29 says which service we use | `core/legal.py` `BRANCH_HOLD_DAYS` |
| 187 | 2026-09-15 | **An uncollected or refused parcel costs the customer 15 000 so'm; the admin refunds the rest within ten days** | Kamronbek's answer to Q11 — "can be changed later", which is exactly what a new `VERSIONS` row is for. 15 000 is the branch tier, about what the return leg costs us. The refund is made by hand, and ten days (`REFUND_DAYS`) is also the period for a paid order cancelled before dispatch and for an accepted return. Stated in the terms, on the delivery page, and in two sentences on the order page of every branch order — where the customer checks the index that decides whether it happens at all | `core/legal.py`, `payment/order_detail.html` |
| 188 | 2026-09-15 | **Form-control borders get a token of their own, `--c-line-control: #756853`; `--c-line-strong` keeps its job** | Q22, left to me. WCAG 1.4.11 asks 3:1 for the boundary that identifies a control, and a field's fill is too close to the page to count as one. Raising `--c-line-strong` would also brighten every panel edge and divider, which the palette chose to keep quiet (§17 #45). A separate token touches only inputs, selects, textareas and checkboxes: **3.54:1 on the page, 3.38:1 on a panel, 3.11:1 against the field's own fill.** The same move as §17 #67 — a token for a purpose rather than an existing one bent. Built in Phase 9, with the rest of the contrast audit | Phase 9 item 16 |
| 189 | 2026-09-16 | **The order status reads "Yetkazilmoqda", like the tile** | Q26. The status, the customer's timeline and the dashboard tile share one msgid, so one change moves all three. The stored value stays `on_the_way`; migration 0018 changes only the choice label. Russian stays «В доставке». **English becomes "In transit"**: "Out for delivery" means a courier is on your street today, which is wrong for a parcel one to six days from a branch | `payment/models.py`, migration 0018 |
| 190 | 2026-09-15 | **The checkout's name field is the recipient's, and the order keeps it** | Found reading the checkout for Phase 8: the name was required, validated and discarded, so an order carried only the account holder's name — and a branch hands a parcel to the person named on it. Fixed on its own branch before the phase began: `Order.recipient_name`, 120 characters, refused with a sentence rather than cut; shown to the customer, in the panel (and searchable), in the admin and in the Telegram message. **Not a behaviour change so much as the behaviour the form always claimed**; older orders fall back to the account's name | migration 0017, `payment/views.py` |
| 191 | 2026-09-16 | **Branch or door is the delivery option's to say** | The order page chose between "Pochta boʻlimi" and "Manzil" by `region_id` — which every order has carried since §17 #106 — so every home order called its street address a post office. It reads `delivery_option.requires_branch` now, and only a branch order carries the hold-and-refund paragraph. The first test of it passed for the wrong reason: the footer lists "Pochta boʻlimigacha" on every page, which contains the label's words, so the assertions are on the label element | `payment/order_detail.html` |
| 192 | 2026-09-15 | **A document's contents list is read out of its rendered text** | Written out beside the text, it could name a section the text does not have. `legal.contents()` takes the `<section id>` and `<h2>` pairs from the rendered body. The list is printed twice — folded above the text on a phone, a sticky rail beside it from 1024 px — and CSS shows exactly one at any width, so nobody, with or without a screen reader, meets it twice | `legal/document.html`, `static/css/pages.css` |
| 193 | 2026-09-15 | **Contact details are written once and asked for by a template tag** | The footer, the contact page, the terms and the privacy policy print one phone, one email and one Telegram from `legal.SELLER`. A simple tag, `{% get_legal as legal %}`, not a context processor: an error page can render without any context processor (§17 #66), and the phone number in the footer matters most on exactly that page | `core/templatetags/legal_tags.py`, `partials/_footer.html` |
| 194 | 2026-09-15 | **The About page says only what the shop can back up** | It promised that every design sat in a Tashkent stockroom and could leave the same day. Nothing guarantees that, and the terms now carry a real delivery deadline. The rewrite says what is true and checkable — one product, the photograph first, specs stated separately, charts measured from the garments, reviews only from buyers and read before they go up, delivery price and time shown before ordering. A test fails if the same-day promise comes back | `core/about.html` |
| 195 | 2026-09-15 | **Consent is asked for where the data is given, and says what it covers** | The signup checkbox linked "the terms" only. The Personal Data Law wants consent that is specific and informed, so it now names both documents and consents to processing under the privacy policy; the checkout says beside its button that placing the order accepts both — which is how a public offer is accepted. **What is not built:** a server-side record of which version a customer accepted, and when (§18 #32) | `user/signup.html`, `payment/checkout.html` |
| 196 | 2026-09-15 | **The production log is rotated daily and kept thirty days, because the policy has to say how long** | It was one file growing for ever, holding IP addresses and phone numbers the privacy policy must give a retention period for. `TimedRotatingFileHandler` at midnight with `LOG_RETENTION_DAYS = 30` backups, and the policy prints that constant. nginx's access log needs the same on the server (Phase 1b item 13) | `vm/settings.py` |
| 197 | 2026-09-15 | **A product description has four parts, and the panel inserts the template in each box's own language** | Item 7: design, print, fit, care — and nothing the spec strip already prints (§17 #111). The template is four gettext strings in `panel/catalogue.py`, rendered under each description box's language rather than the screen's, so the Russian box gets Russian while the panel is in Uzbek. The button fills only an empty box and hides while the box has text, so it can never overwrite what the owner wrote. `docs/content/product-copy.md` explains each part with an example | `panel/catalogue.py`, `static/js/panel.js`, `docs/content/product-copy.md` |
| 198 | 2026-09-16 | **The catalogue tools had to learn to read a catalogue** | Two blind spots, both exposed by Phase 8's strings. `po_fill.py` and `po_needed.py` read a quoted string with `"([^"]*)"`, which stops at the first escaped quote — the consent sentences carry links, so they were cut short in the report and could not be filled at all. `.git/p8_po.py` parses entries properly — continuation lines, escapes, plurals, flags — and refuses a translation whose placeholders or links differ from the msgid's. **And the fuzzy-entry test read only the first line of a msgid**: gettext writes a long one as `msgid ""` plus continuation lines, so every wrapped fuzzy entry looked like the header and was skipped. Two were live — the checkout's transit sentence and the About lede, both rendering Uzbek under `/ru/` and `/en/` — while the test passed. It joins the lines now, and against the unfilled catalogues it finds ten where it found eight | `core/test_i18n.py`, `.git/p8_po.py` |
| 199 | 2026-09-16 | **Every test starts in Uzbek, and a failure under `--parallel` is reported instead of ending the run** | Phase 8's tests request `/ru/` and `/en/` pages and left those languages active for whatever the pool handed that worker next; a Phase 7 dashboard test with a bare `reverse()` then read an English page. That is §17 #124 again, surfacing wherever class order happens to put it. And without tblib — a dependency the project does not take — the first failing assertion killed the worker pool, so every queued test reported a dropped test database and the real failure was one line in several hundred. `core/runner.py`, set as `TEST_RUNNER`, activates the default language as each test starts and sends a failure home as the text of its own traceback; `--debug-sql` and `--pdb` still work. Proved with a throwaway module that failed, errored and failed a subtest on purpose under `--parallel 2`: the run finished and reported all three, and a test that activated English did not leak into the next | `core/runner.py`, `vm/settings.py` |
| 200 | 2026-09-16 | **English calls the carrier "Uzpost" everywhere** | The documents define Uzpost (Oʻzbekiston pochtasi JSC) and use it throughout, while the footer said "via Uzbekiston pochtasi" — two names for one company in one language. The footer and the checkout sentence say Uzpost now. Russian keeps «Узбекистон почтаси» and Uzbek «Oʻzbekiston pochtasi»: each language consistent with itself | `locale/en` |
| 201 | 2026-09-16 | **A file written to the machine is checked by its hash, not by the write reporting success** | Two Phase 8 fixes — the chevron on the folded contents and two English labels in the terms — were written to the machine, reported as written, and were not there: each file held its previous version, and the pages were audited without them for an hour. Both had been sent within five seconds of being saved in the container, and what arrived was what the file held before the save. It is §18 #17's second rule with a concrete way to fail. **Every file written to the repo from the container is now checked with `Get-FileHash` against the hash it was written with**, and a second version goes out under a fresh path rather than over the first | process |
| 202 | 2026-09-16 | **A title that is one long word is wider than a phone** | «Политика конфиденциальности»: the second word is 422 px at the display size and a 390 px phone has a 351 px column, so the Russian privacy policy scrolled sideways at 360 and 390 — the only finding in a sweep of 270, every one of them this. §17 #148's shape in type: a word does not wrap. A document's title steps down on a phone (`clamp(var(--fs-2xl), 7.5vw, var(--fs-5xl))`) and may break below 320 px rather than overflow (§17 #65). `.git/p8_probe_width.py` names the culprit directly — it measures every word on the page with a Range and lists the widest | `static/css/pages.css` |
| 203 | 2026-09-16 | **Two links on neighbouring lines: the second one's tap target covered the first** | The signup consent names two documents now. `a.link::after` grows a standalone link's hit area to 44 px and running text is excluded — `p`, `li`, `td`, `.prose` — but a checkbox's label was not, so at 390 px the privacy link's area lay over the terms link and **a tap on the terms opened the privacy policy**. The audit hit-tests each link's own band and saw nothing wrong; `.git/drive_legal.py` clicks the links and asserts where they land, and found it on its first run. `.check` joins the exclusions | `static/css/components.css`, `.git/drive_legal.py` |
| 204 | 2026-09-16 | **A range is one value, so the dash may not break it** | In the photographs the terms put "1–" at the end of one line and "6 kunda" at the start of the next: an en dash is a line-break opportunity. `legal_range` prints a range with a WORD JOINER on each side of the dash; the six templates and the two catalogue sentences that printed one use it, and a test fails if a template types a dash between two variables again. The two sentences' msgids changed and were rewritten in all three languages | `core/templatetags/legal_tags.py` |

| 205 | 2026-09-16 | **The site says it is dark, and tells Dark Reader to leave it alone** | Kamronbek saw every page in grey. It was not the site: his Brave runs the Dark Reader extension in its dynamic mode, which repaints every colour on every site — the gold included — into its own greys. `<meta name="darkreader-lock">` is the switch Dark Reader honours for a page that is dark by design, and `<meta name="color-scheme" content="dark">` gives the browser's own scrollbars and form controls the dark palette. Both are in the three templates that have a `<head>` — the storefront shell, the panel shell and the style guide — and a test fails if a new one lacks them. Checked in his Brave: the gold is back, the ground is `#100E0C`, and the page carries no Dark Reader attributes. Other sites stay grey until Dark Reader is switched off for them; that setting is the extension's, not ours | `templates/base.html`, `templates/boshqaruv/base.html`, `templates/boshqaruv/style.html` |

| 206 | 2026-09-16 | **Notifications can go through the shop's own Telegram bot, signed with a shared secret** | A friend of the owner is building the bot, and it expects the site to push events to it with `WEBSITE_WEBHOOK_SECRET`. With `TELEGRAM_BOT_WEBHOOK_URL` set, each of the four events is POSTed there once, after commit: the finished Uzbek message and the same facts unformatted — nothing the message does not already say — with the secret in `X-Webhook-Secret` and an HMAC-SHA256 of the timestamp and body in `X-Webhook-Signature`, so the bot may check either. Nothing is sent without the secret, to anything but HTTPS or this same machine, or through a redirect, which would carry the secret along. With the URL blank, Phase 6f's direct route works as it did; neither route raises. The contract for the bot's developer is `docs/integrations/telegram-bot.md`, and a test holds it to the headers the code sends **Amended 2026-09-18 (#237): three events, not four — an order is announced once, when it is paid.** | `core/telegram.py`, `vm/settings.py`, `.env.example`, `docs/integrations/telegram-bot.md` |

| 207 | 2026-09-16 | **No test can notify the real shop** | Once the bot's address and secret are in a developer's `.env`, every test that places an order would relay it — the existing tests stub the Bot API call, which the relay does not make. `core/runner.py` blanks the four notification settings before the suite is built, both in the process and in the environment the parallel workers inherit (python-dotenv never overrides a variable that is set, even to an empty value). A test that needs one sets it | `core/runner.py` |

| 208 | 2026-09-16 | **The seller is a sole proprietor, and the pages say so and no more** | §19 Q27, answered by Kamronbek: YaTT. `SELLER['legal_form']` is a translated label in lower case, because the documents use it mid-sentence. The terms' §1 now says who sells — "yakka tartibdagi tadbirkor Boboyev …", with GRAPHIX as the store's name — §17 and the contact card carry the form as a line of its own, and the privacy policy names the controller by it. No certificate number: he said the detail is not needed | `core/legal.py`, the terms and privacy templates, `templates/core/contact.html` |

| 209 | 2026-09-16 | **The seller's address carries Qoʻqon's index, 150700** | §19 Q28. The registration record's 700000 cannot be Qoʻqon's. The published list of Uzbekistan's postal indexes gives 150700 to Qoʻqon's main post office, beside branches 150701–150712, and no public source says which branch serves Sharq dahasi. The city's index is correct and delivers; if the owner's papers name the branch, it is one line in `core/legal.py` | `core/legal.py` |

| 210 | 2026-09-16 | **A branch holds a parcel one month, and the pages say "one month", not "30 days"** | §19 Q29: parcels go as ordinary parcels, which the Postal Service Rules hold for a month (¶190). `BRANCH_HOLD_MONTHS = 1` replaces the 14-to-30-day range, in the Rules' own unit — thirty days would promise two days that February does not have. The terms, the delivery page and the order page print it; the order page's sentence is a counted plural now, so Russian and English put the month in the form its number takes. Version 1.0 was edited in place, because nobody has been shown it (Phase 11 item 8) | `core/legal.py`, the terms and delivery templates, `templates/payment/order_detail.html` |

| 211 | 2026-09-16 | **The server is in Warsaw, and the privacy policy says where the data is kept** | §19 Q31. Section 4 says where the host is, and section 5 that the site's own data is stored and processed in Poland — an EU member, where the GDPR applies — beside the Google and Telegram transfers. ZRU-1125 keeps only biometric, genetic and telecom-operator data inside Uzbekistan, and the shop collects none of it; other data may go abroad under one of three conditions: a country recognised as equally protective, standard contract terms, or international standards the operator follows. The policy states the facts and claims none of the three: which one the Warsaw host meets is for the legal review (§19 Q32) | the privacy templates |

| 212 | 2026-09-16 | **"Back" never leads to the document the reader is on, in any language** | The language switcher is a link, so reading the terms in Uzbek and switching to Russian arrived with the Uzbek terms as the referrer — and a text match against `/ru/terms/` let "Назад" lead to the Uzbek copy of the same page. The referrer is resolved now, under its own language, because a prefixed path resolves only while its language is active; a path that is not a page is not somewhere to go back to either. `drive_legal` switches the language on a document and checks | `core/views.py`, `.git/drive_legal.py` |

| 213 | 2026-09-16 | **`/favicon.ico` redirects to the icon, and Chrome DevTools' probe gets an empty answer in development** | The two 404 warnings in Kamronbek's runserver log. Browsers ask for `/favicon.ico` whatever a page's `<head>` says; it is a 301 to the static icon now, worked out per request. `/.well-known/appspecific/com.chrome.devtools.json` is DevTools asking whether the site is a local workspace; 204 means no, and the route exists only with `DEBUG` on, because nobody debugs the live site with DevTools often enough for its 404 to matter | `vm/urls.py`, `core/views.py` |

| 214 | 2026-09-16 | **A long email address wraps before its @** | Seen in the browser: links may break anywhere rather than overflow (base.css), and the contact card broke the seller's address inside "com". `email_break` puts a `<wbr>` before the @ wherever the address is printed as text; copying it still gives the address | `core/templatetags/legal_tags.py` |
| 215 | 2026-09-17 | **Q32: the Warsaw host meets ZRU-1125's first condition — Poland is on the Cabinet of Ministers' list. The privacy policy is not changed** | Kamronbek bought the VPS from OVHcloud and asked for the answer from there. It comes from two places. **The state:** Cabinet of Ministers Resolution No. 415 of 29.07.2026, in force 03.08.2026, approves the list of foreign states that protect personal data equally, and Poland is No. 32 on it — which is the first of ZRU-1125's conditions for keeping ordinary personal data abroad. **The host:** OVHcloud's data processing agreement makes it a processor, keeps data in the datacentre the customer chose and does not move it without approval (§6.1), covers its own non-EEA subsidiaries with the EU standard contractual clauses (§6.4), and leaves transfer formalities to the customer (§6.6); its ISO/IEC 27001, 27017 and 27018 certificates cover VPS in every datacentre outside the US. **The policy stays as it is**, at Kamronbek's word: it already says the data is kept in Poland (§17 #211), and the legal basis is not something customers ask about. Recorded here so the legal review starts from it | §19 Q32 |
| 216 | 2026-09-17 | **A cancelled order is named by its GX- number** | §18 #39, Kamronbek's choice. The message said "#45 bekor qilindi" — the database id, which §7 says is never shown and no other screen shows. It is now "GX-260917-0001 raqamli buyurtma bekor qilindi.", written in all three languages; the old msgid is obsolete in the catalogues | `payment/views.py` |
| 217 | 2026-09-17 | **The panel's date filter is typed and shown dd/mm/yyyy; the browser's calendar stays one tap away** | §18 #38. Kamronbek saw mm/dd/yyyy in the panel: a native date input draws the browser's own format, and an English browser's is American whatever the page's language — nothing on the page can change that. So the two fields are text: day first (a dot is read too), a pattern that refuses anything else before it is sent, and the format in each language as the placeholder (*kk/oo/yyyy*, *дд/мм/гггг*, *dd/mm/yyyy*). A calendar button opens the browser's own picker through `showPicker()` on a native input hidden under the field, and the date picked is written back day first; a browser without `showPicker()` shows no button and the field is typed. The view still reads an ISO date, so a link made before the change keeps working, and it refuses 09/16/2026 rather than guess. `calendar` joins the icon sprite and the style guide | `panel/views.py`, `boshqaruv/orders.html`, `panel.js`, `panel.css` |
| 218 | 2026-09-17 | **An Uzbek month is written in lower case — "16 sentabr 2026" — by one filter** | §18 #38. Django's Uzbek month names are capitalised mid-line. Kamronbek accepted "16 sentabr 2026" rather than the documents' "2026-yil 16-sentabr", so the date formats stay and `month_case` (`core/templatetags/date_tags.py`) lowers the result when the page is Uzbek; Russian and English are untouched. Every template date that prints a month's name goes through it, and a test fails for one that does not. The day is the shop's own: Django's `date` filter converts to Tashkent time before formatting, which was the other half of #38 | `date_tags.py`, seven templates |
| 219 | 2026-09-17 | **An account with orders cannot be deleted — `Order.user` is `PROTECT`** | §18 #33, brought forward from Phase 10. It was `CASCADE`, so deleting a customer deleted their sales records — which the Tax Code keeps and the privacy policy promises to keep. The database now refuses, and the admin lists the orders that block the delete and deletes nothing. Closing such an account means clearing its name and phone by hand until an "anonymise" path exists. The abandoned-signup clean-up already refused to delete an account with an order (§12 risk #4) and is unchanged | `payment/models.py`, migration 0019 |
| 220 | 2026-09-17 | **A deleted photograph takes its file with it — after the commit, and only if no row still names it** | §18 #28, brought forward from Phase 10. Django stopped deleting files with their rows in 1.3 for two reasons, and both are real here: a rolled-back delete needs its file, and two rows may name one file — the demo seed deletes the catalogue and recreates rows over the same photographs in one transaction. So `product/signals.py` queues the delete for the commit and first checks `ImageP`, `ReviewImage` and `SizeChart` for the name; a file that will not delete is logged and left. It covers product photos, review photos and size charts, deleted one by one, in bulk (the panel) or by cascade. A picture *replaced* in the Django admin still leaves its old file (§18 #41) | `product/signals.py` |
| 221 | 2026-09-17 | **The Django admin cleans an uploaded picture the way the panel does** | §18 #23. The admin's product-photo, review-photo and size-chart forms put a new upload through `images.sanitise` — the re-encode that strips GPS and shrinks the file — at the sizes the site already uses: 2000 px for product photos and size charts, 1600 for review photos. A file that is not an image is refused on the field; an unchanged or cleared field is left alone | `product/admin.py` |
| 222 | 2026-09-17 | **What a form's native controls say is in the page's language** | Found in the pre-Phase 9 recheck; Kamronbek chose to fix it now. A required field on an Uzbek page said "Please fill out this field." and a file input "Choose Files / No file chosen" — the browser's words, in the browser's language. `forms.js`, loaded by both shells, answers each validation check with a sentence written in all three languages and rendered into the page by a tag, so it works on the 500 page too (§17 #66); a field that states its own format — a `title`, or the checkout index's `data-error-format` — says that instead. A field marked `data-file-field` becomes a translated button and a line naming what was picked; without JavaScript the native control stays. The review form is the first (§18 #29), and `.field__file` moved to `components.css` so both shells share it. It is the only script that sets a custom validity message | `forms.js`, `form_tags.py`, `_form_messages.html`, `review_form.html` |
| 223 | 2026-09-17 | **The share card is redrawn in the brand's own type** | §18 #8, open since Phase 2. `docs/brand/og-card.html` is the source: the header's lockup, the about page's line in Playfair Display and the delivery line in Onest, on the site's ground, with no accent and no figure that could go stale (§17 #39). Edge renders the PNG from it with one command, written in the file | `docs/brand/og-card.html`, `static/img/og-image.png` |
| 224 | 2026-09-17 | **An Uzbek ordinal may break after its hyphen, and it is left as it is** | §18 #40, Kamronbek's call. §18 #37's dash pass in Phase 9 leaves ordinals alone. §18 #26 closes with it, as already done: the chart upload has used the styled label since Phase 7 | — |
| 225 | 2026-09-17 | **An unverified account can reach the code page in every language** | Found in the pre-Phase 9 recheck, reading the middleware against §17 #121 and then driving it. `PhoneVerificationMiddleware` resolved its exempt pages once, at startup, in the default language — so only `/uz/verify-phone/` and its siblings were exempt, and an unverified account on `/ru/verify-phone/` or `/en/verify-phone/` was redirected to the page it was already on, for ever. A signup in Russian or English could not be finished, and the account could not even sign out. The exempt names are now resolved in every language, and `/i18n/` joins the exempt prefixes so the language can be changed on the code page. The OTP flow itself — codes, expiry, attempts, rate limits, the clean-up — is unchanged, and the fix is its own commit because §4 treats anything touching auth with care | `user/middleware.py` |
| 226 | 2026-09-17 | **The seller's postal address is printed in one place: the terms' seller block** | Kamronbek: *“remove address of owner from website. there is no need for that. only name, phone, telegram and email is enough.”* The E-commerce Law (art. 16) wants a postal address inside the public offer, so it stays there; the Personal Data Law (art. 22) asks the operator's address to be *provided*, which a link to the offer does. So the contact card carries the name, the phone, the Telegram handle and the email, and the privacy policy points at the terms instead of repeating the address | `core/legal.py`, `core/contact.html`, `legal/privacy.*.html`, `core.test_phase9.SellerAddressTests` |
| 227 | 2026-09-17 | **Q34: a staff account is verified from the Django admin — no code change** | Kamronbek: *“i can createsuperuser first, enter admin panel and verify that admin myself.”* It works because the phone wall exempts `/admin/` and `phone_verified` is an editable field on the user, so the owner's own account can be let through without letting *every* staff account through, which is what changing the middleware would have done. The README's deploy steps say so, with the trap named: an unverified account left sitting on the code page until the window lapses is deleted, superuser or not | `README.md`, `core.test_phase9.StaffVerificationTests` |
| 228 | 2026-09-17 | **A product must carry at least one tag** (§19 Q35) | Kamronbek: *“make it require at least one.”* Tags are what the shop's filters and the Phase 13 recommender read, so a product with none is invisible to both — §12 risk #22 planned this and the Phase 7 form saved without one. The tags are read *before* the row is written, so a refused save leaves nothing behind, and `blank=False` makes the Django admin ask too | `panel/catalogue.py`, `product/models.py`, `boshqaruv/product_form.html`, `core.test_phase9.TagRequiredTests` |
| 229 | 2026-09-17 | **Two rows in one reference list may not share a name** (§18 #31) | Kamronbek chose refusing over warning. Compared without case, and a tag only against the tags of its own kind — a colour called Qora and a collection called Qora are two things, but two identical chips in one filter group is a question the owner would have to answer later. The rename path is guarded as well as the create form, since a rename can make the twin the form refused | `panel/reference.py`, `panel/views.py`, `core.test_phase9.DuplicateNameTests` |
| 230 | 2026-09-17 | **Photographs are stored once and delivered as WebP at 400 / 800 / 1600 px** | §5 caps one delivered image at 250 KB and the catalogue held a 3.8 MB PNG. Renditions are written beside the original under `w/`, never wider than the source, keyed by the original's stored name so a replaced file is rebuilt rather than described by the old one's; the quality steps 80 → 48 until the file fits, and a source too detailed to fit keeps the smallest rather than being refused. Built on commit — the row is not visible until then and a rollback must not leave orphans — and backfilled by `manage.py build_renditions` | `product/images.py`, `product/signals.py`, `product/templatetags/image_tags.py` |
| 231 | 2026-09-17 | **Hashed static filenames in production; plain ones in development and under test** | `ManifestStaticFilesStorage` is what lets nginx serve every asset with a year's cache and still have a deploy reach the browser. It cannot be on under test: the manifest is written by `collectstatic`, the test runner turns DEBUG off, and without a manifest every `{% static %}` raises. `settings.TESTING` reads the command line, because settings are imported before the runner exists and a spawned `--parallel` worker is handed the parent's argv | `vm/settings.py`, `core.test_phase9.IndexTests` |
| 232 | 2026-09-17 | **One canonical per page, built from `SITE_URL`; alternates from the path alone; `noindex, follow` on everything private** | The site answers on more than one host, so the canonical names one; a filtered or sorted catalogue canonicalises to the catalogue, because forty ways to sort one shop are not forty pages, while page two keeps its number. Alternates drop the query for the same reason. The cart, the checkout, the account, the saved page, a search result and the error pages say `noindex` — Lighthouse scores them 66–69 for SEO *because* of it, which is the correct answer for those pages | `core/seo.py`, `core/context_processors.py`, `base.html`, `core.test_phase9.CanonicalTests`, `RobotsRuleTests` |
| 233 | 2026-09-17 | **One `@graph` of structured data per page** | Two `Product` nodes on one page is one product described twice, and Phase 12's test already said there may be only one block. So the product, its `offers` (§18 #22 — a single `Offer`, or an `AggregateOffer` when the sizes differ in price), its rating and reviews, and the breadcrumb trail all go in one graph; the home page carries `Organization` and `WebSite` with the search action, and nowhere else repeats them | `product/views.py`, `core/seo.py`, `core.test_phase9.StructuredDataTests` |
| 234 | 2026-09-17 | **The panel says a refusal in a toast, not in an error line** (§18 #27 asked for a line) | The five refusals that used `window.alert` are not tied to a field: a status save on a list of twenty orders, an inline number, a reference row, a moderation decision, a delete. A line has nowhere to live on those screens, and the storefront already shows transient failures as a toast in a polite live region — so the panel uses the same component, and the stock box that was refused keeps a red border until the next try | `static/js/panel.js`, `boshqaruv/base.html`, `core.test_phase9.PanelRefusalTests` |
| 235 | 2026-09-17 | **Google Maps is fetched on the customer's first tap, and the privacy policy says so** (§18 #34) | The script loaded with the checkout page, so Google received the IP address of everyone who reached it — including everyone who types their address and never opens a map. The page now carries the provider's URL in `data-map-src` and `GX.map.load` fetches it when “Xaritadan” is pressed; if it never arrives the toggle goes back to manual entry and says why. The policy's 1.0 wording is edited in place in all three languages, which §9 Phase 11 item 8 allows while nobody has been shown it | `payment/views.py`, `checkout.html`, `static/js/map.js`, `static/js/checkout.js`, `legal/privacy.*.html` |
| 236 | 2026-09-17 | **The site is measured the way the server will serve it, and §5's budgets are read per page** | Lighthouse scores what the browser receives: in production that is compressed text, hashed assets with a year's cache and TLS terminated in front of Django, and `runserver` is none of those. The harness builds that shape — `collectstatic`, DEBUG off, a sixty-line Node front door that mirrors `deploy/nginx/graphix.conf` — and only then measures. The budgets are read off each page's own transfer, not off the sum of every file in the project: nothing loads the panel's script and the checkout's map wrapper together, and the summed figure (35 KB of JavaScript) describes a page nobody ever opens. Per page: 21 KB of CSS, 6–16 KB of JavaScript | `.git/p9_measure.py`, `.git/p9_proxy.js`, `.git/p9_axe.py`, `.git/p9_drive.py` |
| 242 | 2026-09-18 | **The repository is flattened and `vm` becomes `config`** | Kamronbek, before the first push to the renamed GitHub repository: *“clear repo … polish structure … it should be shown as created by professional … if possible, change vm to graphix. vm was meant valleymade.”* §18 #9 had parked the package rename in Phase 11 because it can break a deploy — which is the argument for doing it **now**, before the first deploy, rather than later when systemd units, nginx paths and a venv all point at the old name. `vm/` held both the project folder and, inside it, a second `vm/` holding the settings: one word meaning two things, twice. Offered three shapes, he chose the flat one: the apps, `manage.py`, `templates/`, `static/`, `locale/` and `data/` moved to the repository root beside `docs/` and `deploy/`, and `vm/vm/` became `config/`. `DJANGO_SETTINGS_MODULE` is `config.settings`. All 282 files moved as git renames, so the history follows them. **What it cost, and is worth knowing:** `BASE_DIR` is now the repository root rather than one level below it, so three places that reached the root as `BASE_DIR.parent` were looking one level too high, and two tests that read “the project's own source” by walking `BASE_DIR` started parsing `.venv` and `.git` — they now ask Django which apps are direct children of the root (`core.runner.project_python_files`, one rule instead of two exclusion lists). `makemessages` and `compilemessages` both need `--ignore` flags they did not need before, documented in `CONTRIBUTING.md` and used identically in CI so the two cannot drift | everything; `core/runner.py`, `config/`, `CONTRIBUTING.md` |
| 243 | 2026-09-18 | **A one-character msgid mismatch had been serving Uzbek to Russian and English visitors on every product page** | Found by running `makemessages` after the flatten and reading the diff, which is the only thing that would have found it. `templates/product/item.html` builds the meta and og descriptions with `{{ name }} — GRAPHIX original…` using a **plain space** before the em dash; every catalogue holds that sentence with a **no-break space**, because §18 #37's typography pass rewrote the catalogues' msgids and missed these two `blocktrans` blocks. A msgid that differs by one character is a different msgid, so the Russian and English translations were unreachable and a product with no description of its own served the Uzbek sentence to everyone, in every language, since 2026-09-17. Nothing failed, because nothing compares the two. Fixed in the template, which restores the translations *and* applies #37's rule; proved by resolving the string in all three languages before and after. **The general lesson, now in `CONTRIBUTING.md` and `ARCHITECTURE.md`:** Uzbek is the source language, so changing an Uzbek string by one character silently orphans its Russian and English. Run `makemessages` after touching copy and read the diff | `templates/product/item.html` |
| 244 | 2026-09-18 | **CI runs the suite against a real PostgreSQL, and proves the Redis backend loads** | Kamronbek asked for the repository to read as professional work; a green badge is the clearest signal that it is maintained, and a broken `main` can no longer reach the server. `.github/workflows/ci.yml` runs `check`, `check --deploy` with `DEBUG` off — the only run in which the production security settings are checked at all — and all 685 tests, on every push and pull request. One step exists for a specific reason: it sets `REDIS_URL` and reads and writes the cache, because #240's defect survived for weeks precisely because no test and no local run ever executed that branch. A bug that can only appear in production should at least be reachable in CI | `.github/workflows/ci.yml` |
| 238 | 2026-09-18 | **Phase 1b runs before Phase 10, not after it** (amends #36) | Kamronbek's call, asked because the conflict was in the plan rather than in the code. Phase 10's operations block — the nightly `pg_dump` **and a verified restore**, the off-server copy, the `media/` backup, log rotation, uptime monitoring — and its "rate limiter correct with Redis across multiple gunicorn workers" are all server work, and #36 had put the server *after* them. So Phase 10's Definition of Done named four things that could not be done in Phase 10's own slot. Two ways out: split Phase 10 and carry the ops half forward, or deploy first. Deploying first is the better one, and for the same reason §17 #236 gave for Phase 9 — hardening measured against `runserver` is hardening measured against something the visitor never gets. The rent argument that justified #36 has expired: the VPS was bought on 2026-09-12 and is billed whether or not it serves anything. New order: `0 → 1a → 2 → 3 → 4 → 5 → 6 → 12 → 7 → 8 → 9 → 1b → 10 → 11 → 13` | §13, §15, §9 Phase 1b and Phase 10 |
| 239 | 2026-09-18 | **The Content-Security-Policy is our own middleware with a per-request nonce, not a static nginx header** | §9 Phase 10 item 2 asks for CSP and the site has none — `deploy/nginx/graphix.conf` sets cache headers and nothing else. nginx cannot mint a per-request nonce, so a static policy would need `script-src 'unsafe-inline'`, which is most of what a policy is for. Django ships no CSP support and `django-csp` is a dependency we are not taking (#240 is the one exception, and it is not this). So: a small middleware in `core/`, one nonce per request, carried by the single inline `<script>` on the site — the JSON-LD block in `base.html`. **Two inline event handlers have to move into JavaScript first**, because a nonce does not cover an inline handler: `image_tags.py` line 86 emits `onerror="…"` on *every photograph on the site*, and `cart/cart.html` has `onchange="this.form.submit()"`. Both become delegated listeners in `main.js`. `style-src` keeps `'unsafe-inline'`: the rating bar's width is a `style="--…"` binding and CSS cannot know it. Verified in Phase 10 against the Phase 9 production-shaped harness, not asserted | Phase 10 · `core/middleware.py`, `product/templatetags/image_tags.py`, `templates/cart/cart.html`, `static/js/main.js` |
| 240 | 2026-09-18 | **`redis` joins `requirements.txt` — the first and so far only exception to §4's zero-new-dependencies rule** | `settings.py` selects `django.core.cache.backends.redis.RedisCache` the moment `REDIS_URL` is set, and that backend imports the `redis` package, which was neither installed in the venv nor pinned in `requirements.txt`. The server would therefore have raised on its **first cache read** — the rate limiter, the delivery-tier cache, every page that touches either — the moment Phase 1b did what Phase 1b was told to do. Nothing caught it because no test and no local run ever sets `REDIS_URL`, so the branch has never executed. Found by auditing Phase 10, which is the argument for auditing. Kamronbek was offered both dependency-free alternatives that meet the actual requirement (a counter shared across workers) — `DatabaseCache` on the PostgreSQL that is already there, or a file cache — and chose real Redis. **§4 now reads: zero new Python dependencies, except `redis`, added 2026-09-18 under this decision.** Risk #15 amended | `requirements.txt`, `vm/.env.example`, §4, §12 risk #15 |
| 241 | 2026-09-18 | **GRAPHIX is installed beside whatever the box is already running, never over it** | 57.128.240.51 answers on 443 and serves valleymade.uz today. #34 said there was nothing to migrate and #35 said the old site was abandoned — both may still be true, but *abandoned* is not *switched off*, and the machine also holds the database behind it. So GRAPHIX gets its own nginx `server_name`, its own PostgreSQL database and role, its own gunicorn unit and socket and its own directory; no running service is edited, disabled or removed, and **a `pg_dump` of what is already there is taken before PostgreSQL is touched at all** — the standing rule in the project instructions, which does not care that the data is thought to be worthless. Turning the old site off is a separate decision for a later day, made deliberately and not as a side effect of a deploy | Phase 1b · `deploy/` |
| 237 | 2026-09-18 | **One Telegram message per order, sent when it is paid, linking to the panel** | Kamronbek: *“can you merge order created and paid … with this, unpaid or cancelled orders doesn't bother owner.”* The site sent two messages per order — the long one when the row was written, a short one when the payment landed — so every abandoned checkout and every payment that fell through reached his phone, and he had to work out which notifications were parcels. Now `create_order_from_cart` sends nothing and `apply_successful_payment` sends the whole order as **`order.paid`**, with the status it actually has; the message is the one the creation used to send, headed “toʻlandi”. Nothing else changes shape, so the bot keeps parsing what it parsed. The links in all three events now lead to the **staff panel** rather than the Django admin — the panel's order screen carries the status control, and the message and review lists carry an anchor per row — built in Uzbek, because every URL carries a language prefix and a notification has no language of its own. The JSON key stays `admin_url`: renaming it would break the bot for nothing | `core/telegram.py`, `payment/services.py`, `boshqaruv/messages.html`, `boshqaruv/reviews.html`, `docs/integrations/telegram-bot.md`, `core.test_phase6.TelegramDeliveryTests`, `core.test_phase8_recheck.RelayedEventTests` |

## 18. Backlog

Ideas raised but not yet placed in a phase. Reviewed in the planning chat, then scheduled or moved to
§11. A task chat that hits a new idea adds it here and keeps going.

| # | Idea | Raised | Notes |
|---|---|---|---|
| 1 | Uzpost tracking-number integration — attach a tracking number to an order and show it to the customer | 2026-09-08 | Currently §11 out of scope; revisit once order volume justifies the integration work |
| 2 | Branded `info@graphix.uz` email forwarding to the Gmail address | 2026-09-08 | Free with the domain; reads considerably more credible on a contact page. Phase 1 if wanted |
| 3 | Debounced search suggestions in the header field | 2026-09-08 | Phase 6c ships the results page; suggestions are a later nicety |
| 4 | ~~Drop `django-environ` from `requirements.txt`~~ **✅ Done 2026-09-13** | 2026-09-08 | Brought forward from Phase 10 at Kamronbek's request. Removed, and nothing imports it — the four files that matched "environ" all match `os.environ`. The rewrite was also checked for a BOM: PowerShell adds one by default, and Phase 0 re-encoded this file precisely because `pip install -r` cannot read every encoding |
| 5 | ~~Rename the git branch `Kamron's`~~ **✅ Done 2026-09-13** | 2026-09-08 | Confirmed merged into `main` with `git branch --merged`, then deleted. It turned out not to exist on the remote at all — `git ls-remote` shows only `main` — so what looked like a remote branch was a stale tracking ref, pruned. The apostrophe did break the delete command exactly as predicted, which is why it was on this list |
| 6 | Give the commit history real messages going forward | 2026-09-08 | ✅ **Closed 2026-09-12 — already the practice.** Kamronbek: the convention applies from Phase 0 onward; the `.` commits are the old ValleyMade history and stay as they are. Nothing to do |
| 7 | ~~**Instagram and TikTok links** — need the real handles~~ **✅ Closed 2026-09-11: there are no accounts** | 2026-09-09 | Both were `href="#"` in the footer and were removed in Phase 1a rather than shipped dead. Instagram matters: §9 Phase 9 calls it out as a primary sharing surface alongside Telegram. Kamronbek: *“just delete them, there is no insta or tiktok”*. The footer already shipped without them, so nothing changes in the markup; this row and §19 Q16 are closed rather than deferred. If accounts are opened later it is a one-line edit to `_footer.html` |
| 8 | ~~Redraw the OG card once the display typeface exists~~ **✅ Done 2026-09-17 (§17 #223)** | 2026-09-09 | The Phase 1a card was set in Poppins Bold, a placeholder that lacks U+02BB. Redrawn in Playfair Display and Onest from `docs/brand/og-card.html` |
| 9 | ~~Rename the GitHub repository `ValleyMade` → `graphix`~~ **✅ Done 2026-09-17 — the repository is `Graphix`** | 2026-09-09 | Kamronbek renamed it on GitHub and gave the new address; `git remote set-url` followed, and the README's clone line with it. The **package** rename (`vm/` → `graphix`) is the half that can break a deploy and stays in Phase 11. The local working folder is still `D:\phyton\ValleyMade\`, which is only a folder name |
| 10 | **Dev PostgreSQL dies with the laptop's sleep cycle** | 2026-09-09 | Diagnosed during the Phase 3 verification pass. The Windows event log shows sleep/resume and kernel-shutdown events that line up exactly with PostgreSQL restarting; its own log shows **clean shutdowns, no crash, no FATAL**. Anything holding a connection across a sleep — a test run, a `runserver` — dies with *"server closed the connection unexpectedly"*. It is environmental and a retry always works. If it becomes annoying, set the machine not to sleep while a dev server is up, or point local dev at a PostgreSQL in Docker that restarts with the daemon. **Not a code defect — do not chase it as one.** |
| 11 | ~~Wrap the service-layer messages in `cart/services.py` with `gettext`~~ **✅ Done 2026-09-10 (Phase 5)** | 2026-09-10 | §4 says no hardcoded user-facing strings after Phase 3, and Phase 4 added two more raw Uzbek `CartError` messages next to the two that were already there — deliberately consistent with their neighbours rather than half-converting the file. These four are `messages.error()` text, so they *are* user-facing. Done: all five raises wrapped (three distinct messages), the Uzbek respelt with U+02BB, Russian and English written by hand. One came back from `makemessages` fuzzy — caught by the §17 #63 test |
| 12 | ~~`Order.clean()` is written but nothing calls it yet~~ **✅ Closed 2026-09-13** | 2026-09-10 | The Phase 6 checkout calls it, and calls it as *the* validator rather than repeating the rules, so the view and the model cannot disagree about what a valid order is. Original note: | The delivery-option / pickup-point validation exists and is tested directly, but `Order.save()` doesn't call `full_clean()` and the checkout view doesn't yet build an order with a delivery option. Phase 6e wires the checkout picker and is where the call belongs — noting it so the validation isn't assumed to be enforcing anything in the meantime |
| 13 | ~~`vm/core/forms.py` is tracked and completely empty~~ **✅ Deleted 2026-09-10 (Phase 5)** | 2026-09-10 | Found by the Phase 4 verification sweep. It has been a zero-byte file since before this project started (its history is the old `.` commits) and nothing imports it. Phase 5 built the contact form as markup against the existing view rather than a `Form` class, so the file stayed empty and unimported — `git rm`'d. If Phase 9 or a later refactor wants a real `Form`, it creates the file then |
| 14 | ~~Product images have no `srcset` and no intrinsic dimensions~~ **✅ Done 2026-09-17 (§17 #230)** | 2026-09-10 | Every photograph carries `srcset`, `sizes` and its own `width`/`height`, from one template tag; the sizes mirror the CSS that lays each place out. CLS measured 0.000 on all five pages |
| 15 | `docs/design/phase5/` renders are gitignored scratch | 2026-09-10 | `.git/render_p5.py` rebuilds them on demand from a throwaway test database seeded with the Phase 2 mockups, which is how the six-breakpoint screenshots get taken. Kept out of git because they are 22 KB of generated HTML each and go stale the moment a template changes |
| 16 | ~~Returns and uncollected-parcel policy is still the pre-rebuild text~~ **✅ Superseded 2026-09-16** | 2026-09-10 | `terms.html` is deleted. Phase 8 wrote the terms whole, in three languages, against the decided rules (§17 #182, #185, #187) |
| 17 | **Writing a repo file from a snapshot staged earlier silently reverts everything edited since** | 2026-09-11 | Cost about an hour in the Phase 5 polish pass, twice. Files reach the repo by being staged up from the machine, edited in the container, and written back — and a stale staged copy carries the file as it was *when it was staged*, so writing it back throws away every later edit. Nothing errors; the change simply is not there any more, and the next screenshot shows an old defect that was fixed an hour ago. Two rules that would have prevented both: **re-stage a file immediately before editing it**, and **verify by marker on the machine after writing, not by the fact that the write reported success**. `.git/reapply.py` is the recovery pattern — every edit guarded by its own marker so re-running it is safe and it reports which edits it had to put back |
| 18 | ~~**The product page and the delivery page state the delivery prices as copy**~~ **✅ Closed 2026-09-13, reopened and closed properly the same day** | 2026-09-12 | The first pass missed the **footer**, which is on every page, and the **terms page** — both still said 30 000, and the terms page also promised cash on delivery. A `delivery_tiers` context processor now feeds both (§17 #111). Both pages now render the figures from the rows, and the seeded home price is 40 000. Original note: | `item.html` and `delivery.html` each hardcode "15 000" and "30 000". §17 #13 made delivery configurable precisely so a price change is not a deploy — but a change in the admin would now leave two pages quietly lying. It has already drifted once: an earlier plan version had the door tier at 40 000 and the code never followed (§17 #37 was reverted, so 30 000 is correct *today*, which is luck rather than design). Phase 6d/6e render both from the rows |
| 19 | **Admin `help_text` strings are untranslated Uzbek** | 2026-09-12 | Eight fields carry `help_text="Oʻzbekcha — asosiy matn"` and similar. They are admin-only, the owner works in Uzbek, and Phase 7 replaces this admin with a custom panel — so this is deliberately *not* fixed now, and is noted so the §17 #80 sweep does not read as complete for every string on the project |
| 20 | **One inline `style` attribute remains, in `_icons.svg.html`** | 2026-09-12 | The sprite root carries `style="position:absolute"`. It is the standard idiom for an inline SVG sprite; noted so "no `style` attribute" in the Phase 5 checklist is read as "one, deliberately, on a container that renders nothing" rather than as an oversight. ⚠️ **Corrected 2026-09-18 — there are 26, not one.** Twenty-four of them are in `boshqaruv/style.html`, the staff-only style guide, where they are hand-written `flex`/`max-width` helpers for laying out specimens rather than design-system values; one is this sprite root; and one is `product/_reviews.html`'s `width: {{ row.percent }}%`, the rating bar, which is a real dynamic binding and the reason `style-src` keeps `'unsafe-inline'` in §17 #239. The style-guide page's twenty-four are worth moving into the stylesheet; they are staff-only, so they are noted rather than scheduled |
| 21 | **UzPost partner programme** | 2026-09-12 | Promoted to §19 Q24, with the contact details and what it could change — better rates, payment collected at handover, possibly tracking numbers. Left here so the idea is findable from both places |
| 22 | ~~**`offers` is missing from the Product structured data**~~ **✅ Done 2026-09-17 (§17 #233)** | 2026-09-14 | A single `Offer`, or an `AggregateOffer` with a low and a high price when the sizes differ; availability is purchasability, so a size still listed but out of stock reads as out of stock. In the same graph as the rating, the reviews and the breadcrumbs |
| 23 | ~~**Photographs uploaded through the Django admin bypass `images.sanitise`**~~ **✅ Done 2026-09-17 (§17 #221)** | 2026-09-14 | The customer’s upload path strips EXIF by re-encoding (§9 Phase 12 item 5). A staff member adding a photograph to a review — or to a product, which has always been the case — goes straight to the `ImageField` and keeps whatever metadata the file carried, including GPS. It is staff-only and so not the untrusted path, which is why it is noted rather than fixed at the end of a phase; **Phase 7 replaces this admin**, and the custom panel should run every image through the same function. Worth doing there for products as much as for reviews |
| 24 | ~~**A zoomable image cannot be reached from a keyboard**~~ **✅ Done 2026-09-17** | 2026-09-14 | `viewer.js` gives every zoomable photograph a role, a tab stop and a name, and answers Enter and Space — one place for every one of them, rather than a button in nine templates. The name is the picture's own `alt` plus a word saying what pressing it does, both translated |
| 25 | ~~**`payment/templatetags/uzb_dates.py` prints Uzbek months in every language**~~ **✅ Done 2026-09-16 (Phase 8)** | 2026-09-14 | Both templates use Django's `date:"j E Y"`, the file is deleted, and a test fails if anything loads it again. The order page's date is checked in Russian |
| 26 | ~~The size-chart upload on `/boshqaruv/sozlamalar/` uses a bare file input, so it shows the browser's own English "Choose File" on an Uzbek screen. The panel's gallery already uses the pattern that avoids it — a visually-hidden input driven by a styled `<label>`. The review form has the same bare input, so this is one change in two places.~~ **✅ Closed 2026-09-17 — already done:** the chart upload has used the styled label since Phase 7 (§17 #224) | 2026-09-14 | Phase 9 |
| 27 | ~~`panel.js` says three things with `window.alert()`~~ **✅ Done 2026-09-17 (§17 #234)** | 2026-09-14 | Five, in the end, all now said on the page as a toast in a polite live region. A refused stock box also keeps a red border, so a number that did not save is still findable in a grid of twenty | Phase 9 |
| 28 | ~~Deleting a product photograph removes the row but leaves the file on disk. Nothing reads it again, so it is storage rather than correctness, but it accumulates.~~ **✅ Done 2026-09-17** — the file goes with its row, after the commit (§17 #220) | 2026-09-14 | Phase 10 |
| 29 | ~~The review form's file input is still a bare `type="file"`, so it shows the browser's own English "Choose File". The panel's chart upload and its gallery both use the styled-label pattern that avoids it; this is the last place that does not.~~ **✅ Done 2026-09-17** — a translated button and a line naming the files (§17 #222) | 2026-09-14 | Phase 9 |
| 30 | ~~`Product.fit` is still `TextChoices` — two cuts, by §17 #70~~ **✅ Closed 2026-09-14 — the field is gone (§17 #172).** A cut is a tag now, so a third one is a row the owner types, not a migration. | 2026-09-14 | — |
| 31 | ~~Two reference rows may share a name (their slugs differ)~~ **✅ Done 2026-09-17 (§17 #229)** | 2026-09-14 | Refused rather than warned, on Kamronbek's call: case-insensitive, per list, and a tag only against the tags of its own kind. The rename path is guarded too | Phase 9 |
| 32 | Record which version of the terms and the privacy policy a customer accepted, and when — at signup and with each order | 2026-09-16 | The consent is asked for and the documents are versioned (§17 #195), but nothing stores the pair. If a dispute ever turns on what a customer agreed to, the answer today is "whatever the site said that week". Two nullable columns and a `VERSIONS` lookup **Phase 10.** |
| 33 | ~~**Deleting a user deletes their orders**~~ **✅ Done 2026-09-17 — `Order.user` is `PROTECT` (§17 #219)**. The privacy policy promised the opposite | 2026-09-16 | `Order.user` is `on_delete=CASCADE`. The policy says order records are kept for the tax period even after an account is deleted, and the Tax Code wants them. Until an "anonymise this account" path exists, **a deletion request must never be handled with the admin's delete button**: clear the name, username and phone by hand and keep the orders **Phase 10.** |
| 34 | ~~Load the Google Maps script only when the map is about to be used~~ **✅ Done 2026-09-17 (§17 #235)** | 2026-09-16 | Verified in a browser with the network watched: nothing goes to Google when the checkout opens, and the provider arrives on the first tap of “Xaritadan”. The privacy policy describes the narrower transfer in all three languages | Phase 9 |
| 35 | The three-week "your parcel is waiting" reminder in risk #25 is not built | 2026-09-16 | It needs to know when a parcel reached its branch, which today means a tracking number (§18 #1, §19 Q24) or a status the owner sets by hand, and an SMS body Eskiz has moderated **After launch.** |
| 36 | ~~English copy is not consistent with itself~~ **✅ Done 2026-09-17** | 2026-09-16 | Eighteen strings rewritten: the typographic apostrophe throughout, and one word for the garment — “T-shirt”, including the one place that said “tee”. The pass skips template markup, because `{% url 'terms' %}` is not English and the possessive rule broke it the first time | Phase 9 |
| 37 | ~~A spaced dash can begin a line~~ **✅ Done 2026-09-17** | 2026-09-16 | A no-break space before every spaced em dash: 261 edits — the translatable strings in the templates and the Python, the nine legal documents, and every `msgstr` in the three catalogues, which were carried onto their new msgids rather than re-translated. Comments and docstrings are untouched; the pass only edits inside translation markup and document prose | Phase 9 |
| 38 | ~~Uzbek dates outside the documents read "16 Sentabr 2026"~~ **✅ Done 2026-09-17** — "16 sentabr 2026", Kamronbek's choice (§17 #218), and the panel's date fields day first (§17 #217) | 2026-09-16 | Django's Uzbek `E` capitalises the month mid-line and has no *-yil* form. `legal_date` already writes "2026-yil 16-sentabr" for the documents; the order pages and the review dates should share one filter — and it must convert to local time first, because a date taken from UTC names the wrong day for the five hours after midnight in Tashkent (a Phase 8 test met exactly that) **Phase 9.** |
| 39 | ~~Cancelling an unpaid order says "#45 bekor qilindi" — the database id, where every other screen and the terms call an order by its GX- number~~ **✅ Done 2026-09-17** — named by its GX- number (§17 #216) | 2026-09-16 | Found in the Phase 8 recheck. One message in `payment/views.py`, and its msgid changes with it, so it is copy work in three languages **Phase 9.** |
| 40 | ~~An Uzbek ordinal breaks after its hyphen: "369-" at the end of a line and "moddasi" at the start of the next (the terms, 390 px)~~ **✅ Closed 2026-09-17 — left as it is**, Kamronbek's call (§17 #224) | 2026-09-16 | The same kind of break §17 #204 closed for ranges. A word joiner after the hyphen, or a no-break hyphen if the fonts carry one, in the same typography pass as #37 **Phase 9.** |
| 41 | A picture replaced in the Django admin leaves its old file on disk | 2026-09-17 | §17 #220 removes a file when its row is deleted. Replacing the file on a row that stays happens only in the Django admin — the panel adds and deletes pictures, never replaces them — so it is rare and staff-only. The same on-commit, still-named check from a `pre_save` receiver would cover it **Phase 10.** |
| 43 | **The catalogues carry obsolete entries — 197 lines in Russian, 195 in English** | 2026-09-18 | Counted by a full `makemessages` run during the flatten. An obsolete entry (`#~`) is a translation whose msgid the source no longer produces: usually a string that was deleted, harmlessly. But §17 #243 was one that was *not* — a live string whose msgid drifted by one character, leaving the translation stranded and the page silently Uzbek. So the pile needs reading once, not deleting: any obsolete entry whose text still appears on the site is another #243. The regenerated catalogues were reverted rather than committed, because the only functional change in them was that one msgid and the rest was re-wrapping churn **Phase 10.** |
| 42 | Tests write photographs into `vm/media/` | 2026-09-17 | The panel's photo tests (`test_phase7b`) and the review tests (`test_phase12`) save through the real storage, so every run leaves files in the developer's media folder — 438 in `products/` and 137 in `reviews/` on 2026-09-17, most of them test output. The newer tests use a throwaway `MEDIA_ROOT`; the older ones should too, and the leftovers need clearing without touching the demo catalogue's photographs. It matters more now that a deleted row deletes its file (§17 #220): a test that deletes a row after a commit must never point at the real folder **Phase 10.** |

## 19. Open questions

| # | Question | Needed by | Status |
|---|---|---|---|
| 1 | A Google Maps Platform API key | Phase 1b | ✅ **Answered 2026-09-12**, and **a key was supplied 2026-09-13**. It is in `vm/.env` (gitignored) and the map renders. **Two things are still outstanding on the Google project and only Kamronbek can do them:** (a) **billing is not enabled**, so the *Geocoding* API answers `REQUEST_DENIED` — the map works, the pin is stored, but it cannot fill the address field, and the customer types it instead (which is the degradation §17 #91 already required, so nothing is broken); (b) the key is **unrestricted** — it ships in the page by design, so it needs an HTTP-referrer restriction to `graphix.uz` and `www.graphix.uz` plus a budget alert, on the day it goes to the server (§12 risk #5). **Everything downstream of the geocoder is built and tested** (§17 #116, #117, #120): a dropped pin fills the region, the district and the street line, verified against the exact component shapes Google returns for Tashkent city, Tashkent region and Samarkand. Enabling billing turns that on with no deploy |
| 2 | Telegram bot token and chat ID | Phase 1b | ✅ **Answered 2026-09-12** — same as Q1: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` ship blank, 6f is built and tested as though they were set, and an unset token logs a warning and sends nothing (§17 #93) |
| 3 | ~~Can Uzpost supply an official branch list (index codes, addresses, coordinates, hours)?~~ | — | ✅ **Closed 2026-09-12 — the question no longer needs an answer.** §17 #84 replaced the branch table with region + district + a customer-typed postal index, so nothing waits on a dataset we cannot obtain. `PickupPoint`, `seed_pickup_points` and the header-only CSV are retired in Phase 6d |
| 4 | ~~Pickup-point launch scope — Tashkent only, regional capitals, or nationwide?~~ | — | ✅ **Closed 2026-09-12** — there are no pickup points to scope. Every Uzpost branch is reachable from day one, because the customer supplies its index (§17 #84) |
| 5 | Is 40 000 so'm home delivery the right price? | Phase 6e | ✅ **Answered 2026-09-12** — **40 000 nationwide, confirmed.** The cost question behind it stays live as §12 risk #6, not as an open question: check it against Uzpost's tariffs before launch and use Q24 if the margin is thin |
| 6 | Tag taxonomy — **who defines the style/theme tags, and what is the starting list?** Phase 4 seeded exactly the eight §7 names — style: `oversize`, `boxy`; theme: `anime`, `streetwear`, `music`, `sport`, `minimal`, `vintage`. No `collection` tags: those are per-drop and the owner creates them as drops happen. **The list needs extending by whoever knows the catalogue** — it is what the Phase 13 recommender reads, so a thin taxonomy means weak recommendations. | Phase 7 | ✅ **Answered 2026-09-11** — the owner writes tags when adding a product; the seeded eight are a starting set, not a taxonomy (§17 #71) |
| 7 | ~~Fit range — regular and oversize only, or more?~~ | — | ✅ **Answered 2026-09-11** — regular and oversize only (§17 #70). ⚠️ **Moot since 2026-09-14:** the question no longer has anything to range over. `fit` is gone and a cut is a tag, so the answer is whatever the owner types (§17 #172) |
| 8 | **Were the designs in the customer's mockup placeholders?** If any reproduce other brands' marks and are intended for sale, that is worth reviewing before listing. | Phase 11 | ⏳ Open |
| 9 | Size-chart images — do they exist, or do they need producing? | Phase 6a | ✅ **Answered 2026-09-12** — produce them. One chart per fit, drawn in-project with a `SizeChartRow` table, replaceable by the owner at any time (§17 #95). Phase 4's carried item 11 unblocks with it; the measurements are verified against real stock in Phase 11 |
| 10 | ~~Expected delivery timeframes to quote~~ | — | ✅ **Closed 2026-09-13 — looked up and quoted.** 1–6 days nationwide for an ordinary parcel; Bir Qadam is 1 day Tashkent→regional centre and 2–3 days between regions. Now stated at checkout, on `/yetkazib-berish/` and on the order page. Two findings came with them and are **not** closed — see §17 #103 and risk #6 |
| 11 | ~~**Returns window, and the refund rule for an uncollected parcel.**~~ | — | ✅ **Answered 2026-09-15** — 15 000 so'm is kept and the admin refunds the rest within ten days (§17 #187); a wrong size is exchanged at the customer's cost, a defect at ours (§17 #185). Stated in the terms, on the delivery page and on every branch order's page. "Can be changed later" — by a new version of the terms |
| 12 | ~~Legal entity name and details for the terms and privacy policy~~ | — | ✅ **Answered 2026-09-15** — from the domain registration record: the registered name and address, with the shop's contacts, and no tax or bank details on any page (§17 #184). GRAPHIX stays the shop's name. Two details in that record need confirming: Q27, Q28 |
| 13 | Cash-on-delivery limits — any order-value cap, or regions excluded? | Phase 6e | ✅ **Answered 2026-09-12 — there is no cash at all.** Online payment only, for the goods and the delivery alike, so there are no limits to set. The disabled control comes out of checkout (§17 #94) and cash joins §11 |
| 14 | Earlier notes said "BTS pochta"; one carrier or two? | Phase 8 | ✅ **Answered 2026-09-12** — **Uzpost only.** There is no BTS involvement; treat any surviving mention as stale. `terms.html` section 3 was already corrected in Phase 5 |
| 15 | When is the VPS bought? | Phase 1b | ✅ **Answered 2026-09-12 — it is bought.** Ubuntu 24.04, 2 vCore, 4 GB RAM, 40 GB SSD, exactly the settled specs. Phase 1b is unblocked and still runs in its §13 slot, after Phase 10 |
| 16 | Instagram and TikTok handles for the footer (§18 #7) | — | ✅ **Answered 2026-09-11** — there are no accounts; the links are dropped, not deferred |
| 17 | Eskiz sender name and the two SMS bodies | Phase 1b | ✅ **Answered 2026-09-12** — the **GRAPHIX sender is approved**. The residual check moves into Phase 1b item 10 rather than staying a question: both message bodies changed in Phase 1a and Eskiz moderates text, so confirm they are moderated before the first live signup |
| 19 | Product photography — when can real shots exist? Not blocking now (§17 #42), but it gates Phase 11 and it is what decides whether the chosen direction actually looks professional. | Phase 11 | ⏳ Open |
| 21 | The dev machine sleeps and takes PostgreSQL down with it, so a command that spans a sleep dies with *"server closed the connection unexpectedly"*. Harmless — retry. Worth knowing before someone debugs it as a code fault (§18 #10). | — | ℹ️ Environment, not a defect |
| 22 | ~~`--c-line-strong` is 1.8:1 against the page ground, and §9 asks for 3:1 on UI boundaries~~ | Phase 9 | ✅ **Decided 2026-09-15**, on Kamronbek's instruction to make the call: form controls get `--c-line-control: #756853` (3.54:1 on the page); `--c-line-strong` stays as it is for panel edges and dividers (§17 #188). **Built 2026-09-17** — every field, checkbox, stepper, size button, filter chip and language switch draws itself with it, and the ratio is asserted in `core.test_phase9.ControlBorderTests` |
| 23 | ~~`data/regions.csv` — who verifies it?~~ | — | ✅ **Closed 2026-09-13 — built and verified** (§17 #98). Original answer: Build it from the SOATO / MHOBT classifier, cross-check against published directories and the public compilations without copying them (§17 #90), confirm every postal prefix, and write the sources and the method into `data/README.md` so it can be re-checked rather than re-trusted |
| 24 | **Call Uzpost about the partner programme, before launch.** They run *UzPost multibrend topshirish punktlari*, built for marketplaces and online stores delivering to their branches, and *Bir Qadam*, next-day to designated branches nationwide. Better rates and possibly tracking numbers (§11 puts tracking out of scope; this could change that). The cash-at-handover part matters only if the owner switches cash on (§17 #99). **+998 71 233-57-47 · info@pochta.uz.** A business conversation, not development work, but it bears directly on risk #6. | Phase 11 at the latest | ⏳ Open |
| 25 | ~~Should Uzbek take a `/uz/` prefix like the other two languages?~~ | — | ✅ **Answered and done, 2026-09-14 — yes.** Built the same day, before any of it could go stale: §3's locked row is amended, `prefix_default_language=True`, old unprefixed URLs redirect into the prefixed tree, and `core/test_i18n.py` holds the new shape (§17 #121). The reasoning as it was put to him: §3 locks Uzbek at `/` with Russian at `/ru/` and English at `/en/`, so this is a locked decision and not something to change quietly. **For:** it removes a whole class of bug at the source — with every language prefixed, `LocaleMiddleware` stops forcing the default language on unprefixed paths and `set_language` works unaided (§17 #115 was one symptom); and `/` could then send a visitor to their own language instead of always serving Uzbek. **Against:** every Uzbek URL changes, so the site needs a 301 for each one, and the sitemap, the canonicals, the OG URLs and `core/tests.py` all move with them — work that is cheap now and expensive after launch. **The switcher was fixed either way**, so nothing was waiting on this; it was a URL-shape decision, not a bug fix |
| 26 | ~~Should the status label follow the "Yetkazilmoqda" tile?~~ | — | ✅ **Done 2026-09-16** — yes. Label only; the stored value is unchanged; English is "In transit" (§17 #189) |
| 27 | ~~**What is the seller's legal form?**~~ | — | ✅ **Answered 2026-09-16** — a sole proprietor (YaTT). Stated as the form and nothing more: the terms say who sells, the seller block and the contact card carry it, no certificate number (§17 #208) |
| 28 | ~~**The registration record gives postal index 700000 for a Qoʻqon address.**~~ | — | ✅ **Answered 2026-09-16** — 150700, Qoʻqon's main post office, from the published index list. No public source maps Sharq dahasi to one of the city's branches; if the owner's papers name one, it is one line in `core/legal.py` (§17 #209) |
| 29 | ~~**Which Uzpost service will parcels go by — Bir Qadam or an ordinary parcel?**~~ | — | ✅ **Answered 2026-09-16** — ordinary parcels. A branch holds one a month, and the pages say one month (§17 #210). Q24's conversation with Uzpost may still change the service; if it does, the constant and the wording change with it |
| 30 | **Register the shop with the state register of personal-data operators** before the site takes a real customer's data. The owner's to do, not code — but the privacy policy is written on the assumption that it is done | Phase 11 | ⏳ Open — Kamronbek is passing it to the owner (2026-09-16) |
| 31 | ~~**Where is the VPS?**~~ | — | ✅ **Answered 2026-09-16** — Warsaw, Poland. The privacy policy says the site's data is kept there (§17 #211); what remains is Q32 |
| 32 | ~~**Which of ZRU-1125's conditions does the Warsaw host meet?**~~ | — | ✅ **Answered 2026-09-17** — the first: Poland is No. 32 on the Cabinet of Ministers' list of countries that protect personal data equally (Resolution No. 415 of 29.07.2026, in force 03.08.2026). OVHcloud's data processing agreement and certificates are consistent with it. The privacy policy is not changed, at Kamronbek's word (§17 #215) |
| 33 | **Where does the Telegram bot service run, and at what address?** The site relays to it once `TELEGRAM_BOT_WEBHOOK_URL` is set (§17 #206). The address must be HTTPS unless the bot is on the site's own server, and if the bot runs anywhere but the Warsaw server, the privacy policy has to name that country too | Phase 1b | ⏳ Open |
| 34 | ~~**Should a staff account get past the phone-verification wall?**~~ | — | ✅ **Answered 2026-09-17 — leave the code as it is (§17 #227).** Kamronbek: *“if it is possible to verify number from admin panel and enter admin panel without phone verification, it is ok to stay like that.”* It is: `/admin/` is exempt from the wall and `phone_verified` is editable there, so the owner verifies his own account and opens the panel. It is a deploy step, written into the README, and a test holds both halves of it in place. The trap is named with it: an unverified account that sits on the code page until the window lapses is deleted, superuser or not |
| 36 | **Is 57.128.240.51 the VPS bought on 2026-09-12, or an older machine?** The plan records a Warsaw VPS bought that day (§19 Q15, Q31) and an abandoned valleymade.uz (§17 #35) — but this address is serving valleymade.uz over HTTPS right now and **refuses Kamronbek's current SSH key for every user tried** (`root`, `ubuntu`, `debian`, `admin`, `deploy`, `valleymade`), which is what a machine set up long ago looks like, not one provisioned last week from this laptop. If there is a second, unused Warsaw instance, GRAPHIX belongs on that one. Answered from the OVH panel. **Nothing is installed until it is.** | Phase 1b | ⏳ Open — raised 2026-09-18 |
| 35 | ~~**Should the product form require at least one tag?**~~ | — | ✅ **Answered 2026-09-17 — yes (§17 #228).** Kamronbek: *“make it require at least one.”* The panel refuses the save and says which field is missing, the form says so before it is submitted, and `blank=False` makes the Django admin ask as well. §12 risk #22 closes with it |

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
| Delivery carrier and pricing? | ✅ Uzpost nationwide · 15 000 to a branch · 40 000 to the home · no free threshold (§17 #85) |
| Telegram bot? | ✅ Yes — **three** notifications since 2026-09-18: a paid order, a contact message, a review awaiting moderation. An unpaid order is not announced at all (§17 #237). They can go through the shop's own bot service (§17 #206) |
| Size guide format? | ✅ Image-first, optional measurement rows |
| Map provider? | ✅ **Google Maps Platform**, behind a swappable wrapper (§17 #83). Yandex was the answer until 2026-09-12 |
| Like vs favourite? | ✅ Merged into one heart |
| Guest checkout? | ✅ Anonymous cart; login required at checkout |
| Is there data in the current production database to preserve? | ✅ No — it holds no items. A new VPS is being provisioned; nothing needs migrating (§17 #34) |
| Which visual direction? | ✅ Round one (three directions) rejected; the round-two dark premium direction signed off 2026-09-09 (§17 #44–47) |
| Which branch is the integration branch? | ✅ `main`. `Kamron's` merged into it before Phase 0; phase branches cut from `main` (§17 #32) |
| What happens to valleymade.uz? | ✅ Abandoned outright — no 301s, no old server, no Change of Address (§17 #35) |
| New VPS specs? | ✅ Ubuntu 24.04 (upgradeable to 26.04), 2 vCPU, 4 GB RAM, 40 GB SSD — anything can be installed on it |
| Who runs the server commands? | ✅ Kamronbek has shell access and I can drive it from his machine when the time comes |
| Wordmark lockups in Phase 1? | ✅ No — moved to Phase 2, after the display typeface is chosen (§17 #38) |
| "100+ designs" before the catalogue exists? | ✅ Hardcoded now; Phase 11 item 2 is the launch gate (§17 #39) |
| Is there a staff account for `/boshqaruv/style/`? | ✅ Yes — the existing `admin` account. No README change needed |

---

*End of plan. Amend it rather than working around it.*
