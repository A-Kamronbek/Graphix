# Architecture

How GRAPHIX is put together, and why it is put together that way. For the plan
— phases, decisions, progress — see [`PLAN.md`](PLAN.md). For the rules you
have to follow when changing it, see [`../CONTRIBUTING.md`](../CONTRIBUTING.md).

A plain Django project: server-rendered templates, no build step, no
JavaScript framework, no API layer. That is a choice rather than an omission.
The audience is on a mid-range Android phone on a 4G connection in Tashkent,
and the fastest page is the one that is already HTML when it arrives.

---

## The shape

```
config/      settings, the root URL conf, wsgi and asgi
core/        site pages, the legal documents, the contact form, the Eskiz and
             Telegram clients, the rate limiter, the sitemaps, the test runner
             — and the whole test suite
user/        the phone-based User, sign-in, OTP, password reset, the
             verification middleware
product/     the catalogue: products, variants, tags, photographs, likes,
             reviews, size charts, and the image pipeline
cart/        carts, for guests and for signed-in customers
payment/     checkout, delivery options, regions and districts, orders, Click
panel/       the staff panel at /boshqaruv/
templates/   every template, including robots.txt and site.webmanifest
static/      CSS, JS, fonts, icons
locale/      uz, ru, en
data/        regions.csv and a note on how it was built
deploy/      what the server runs: nginx, systemd units, backups, the runbook
docs/        this, the plan, the integration contracts, brand and design
```

The test suite lives in `core/` rather than in each app because most of what
is worth asserting crosses app boundaries: a checkout is `cart` and `payment`
and `user` at once, and a test that can only see one of them is testing the
wrong thing.

---

## What a request does

```
nginx  →  gunicorn  →  middleware  →  URL resolution  →  view  →  template
```

nginx terminates TLS, serves `/static/` and `/media/` straight from disk, and
proxies everything else to gunicorn over a unix socket. Django never serves a
file in production.

The middleware order in `config/settings.py` is load-bearing and commented
there. Two entries are ours:

- **`LocaleMiddleware`** sits after the session middleware (it reads the
  language from the session) and before `CommonMiddleware` (which appends
  slashes using the active URL conf). Getting this wrong makes the language
  switcher one-way, which it was for three phases.
- **`user.middleware.PhoneVerificationMiddleware`** sends a signed-in account
  whose phone is unverified to the code screen, from anywhere except
  `/admin/`. It applies to staff too — which is why a new superuser has to be
  verified through `/admin/` once before the panel will open (plan §19 Q34).

### URLs and language

Every customer-facing path lives under a language prefix — `/uz/`, `/ru/`,
`/en/` — through `i18n_patterns` with `prefix_default_language=True`. Uzbek is
not special-cased: it carries its prefix like the others (§17 #121).

Four kinds of path stay **outside** the prefix because a machine asks for them
and a redirect would break it:

| Path | Why |
|---|---|
| `/payment/click/update/` | **the Click webhook. A redirect here is a silent payment failure.** |
| `/admin/` | the Django admin, kept as the fallback behind the panel |
| `/sitemap.xml`, `/robots.txt`, `/favicon.ico`, `/site.webmanifest` | crawlers and browsers |
| `/i18n/`, `/static/`, `/media/` | the language switch and the files |

---

## The parts worth understanding before changing them

### Money

`payment.services.create_order_from_cart` takes a `select_for_update` row lock
and computes the total inside it, so two taps on "pay" cannot produce two
orders or one order with a stale price. Add to that function; do not
restructure it.

Delivery prices are rows, not constants. The product page, the delivery page,
the footer and the terms all render them from a context processor, because the
first version stated them as copy and two pages quietly lied for a week.

An order is `GX-YYMMDD-NNNN`. Every screen and every document calls it that;
the database id is never shown.

### Payment

Click calls one endpoint for both Prepare and Complete; `click_up` routes
internally. `apply_successful_payment` is where an order becomes `paid`, and
it is the only place that announces an order to Telegram (§17 #237) — an order
that is placed and never paid for is never mentioned to anyone.

### Accounts

There is no email anywhere: an account is a phone number, verified by an SMS
code, and a forgotten password is reset the same way. `User.save()` normalises
the number; the OTP flows and their rate limits are correct as written and are
the last thing on the site that should be refactored casually.

An account with an order cannot be deleted — `Order.user` is `PROTECT`
(§17 #219). The privacy policy promises the orders are kept, and the Tax Code
wants them.

### Photographs

Every uploaded image is re-encoded rather than stored as received, which
strips EXIF — phone photographs carry GPS coordinates, and a customer's review
photo would otherwise publish where they live.

`product/images.py` then builds WebP renditions at 400, 800 and 1600 px,
stepping quality down from 80 until the file fits a 250 KB budget. They are
built on `transaction.on_commit`, so a rolled-back upload leaves nothing
behind, and `manage.py build_renditions` backfills anything older. Templates
never reference a file directly — `{% photo_attrs %}` emits `srcset`, `sizes`
and the intrinsic `width`/`height` that keep layout shift at zero.

### Outside services

Eskiz, Telegram, Google Maps and Click all follow the pattern in
`core/sms.py`: a module-level logger, catch everything, log it, return
something falsy. **An outage degrades a feature; it never 500s a page.** Every
one of them also ships with its credential blank and the feature fully built
around the blank (§17 #93), so switching one on is a paste into `.env` rather
than a deploy.

### Rate limiting

`core/ratelimit.py` counts in the cache. In production the cache is Redis,
because gunicorn runs three workers and three separate in-memory counters mean
the real limit is three times the configured one. The window of every limit is
asserted against what the privacy policy promises.

### Translation

Uzbek is the source language, so the msgid *is* the Uzbek string and
`locale/uz` translates almost nothing. Russian and English are written by
hand, never machine-translated in bulk.

This means a one-character change to an Uzbek string in a template silently
orphans its Russian and English translations — the msgid no longer matches and
both fall back to Uzbek, with nothing failing. It has happened: a typography
pass added a no-break space to the catalogues' msgids and missed two template
blocks, and the product page served Uzbek to Russian visitors until the
mismatch was found. `makemessages` is what finds it; run it after touching
translatable copy, and read the diff.

### Static files

With `DEBUG=False` — and outside tests — static files are served under hashed
names via `ManifestStaticFilesStorage`, so nginx can cache them for a year
honestly. `collectstatic` is therefore not optional in production: without it
the first `{% static %}` on the first page raises.

---

## The staff panel

`/boshqaruv/` is a second interface, not a skin on the Django admin: orders,
the catalogue, moderation, the contact inbox and the reference tables. It has
its own guard — a signed-in customer gets a 403, not a second login form — and
it is **the one place in the project allowed to assume JavaScript** (§17 #141).

Five reference models are edited through a single endpoint behind an allowlist
(§17 #149) rather than five near-identical views.

The Django admin stays at `/admin/` as the fallback for the things the panel
deliberately does not do.

---

## Testing

`core.runner.Runner` does three things no individual test should have to:
starts every test in Uzbek (`LocaleMiddleware` leaves the last request's
language active, which made failures move around under `--parallel`), carries
a worker's failure to the parent as text (a traceback will not pickle, and
tblib is a dependency we do not take), and blanks the Telegram settings so a
test run cannot notify the real shop.

```bash
python manage.py test --parallel 4
```
