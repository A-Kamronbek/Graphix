# GRAPHIX

[![CI](https://github.com/A-Kamronbek/Graphix/actions/workflows/ci.yml/badge.svg)](https://github.com/A-Kamronbek/Graphix/actions/workflows/ci.yml)

Online store for graphic T-shirts in Uzbekistan. Django and PostgreSQL,
server-rendered, no build step. Phone-number accounts verified by SMS, Click
payments, Uzpost delivery, and a storefront written three times over in Uzbek,
Russian and English — Uzbek first.

Production: **https://graphix.uz** — being deployed; see
[`deploy/RUNBOOK.md`](deploy/RUNBOOK.md).

| | |
|---|---|
| **The plan** | [`docs/PLAN.md`](docs/PLAN.md) — phases, locked decisions, progress. The source of truth. |
| **How it works** | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| **How to change it** | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| **How it is deployed** | [`deploy/RUNBOOK.md`](deploy/RUNBOOK.md) |

---

## Running it locally

Needs Python 3.12 or newer, PostgreSQL, and GNU gettext.

```bash
git clone git@github.com:A-Kamronbek/Graphix.git
cd Graphix

python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then fill in DB_* at least

python manage.py migrate
python manage.py seed_regions              # the checkout's regions and districts
python manage.py compilemessages --ignore .venv
python manage.py createsuperuser
python manage.py runserver                 # http://127.0.0.1:8000/uz/
```

Two things that will otherwise catch you out:

**Verify your own phone before visiting any page.** `createsuperuser` leaves
the account unverified, and every page outside `/admin/` sends an unverified
account to the SMS code screen — superuser or not. Sign in at
`http://127.0.0.1:8000/admin/`, open your user, fill in the phone and tick
**phone_verified**. An unverified account left sitting on the code screen until
the window lapses is deleted.

**`compilemessages` needs `--ignore .venv`.** The apps live at the repository
root, so without it the command walks into the virtualenv and recompiles every
catalogue Django ships. `makemessages` needs its own ignore list — see
[`CONTRIBUTING.md`](CONTRIBUTING.md).

`python manage.py seed_demo_catalogue` loads the eight demo designs every
screenshot is measured against. It replaces the catalogue and refuses to run
against anything but a local database.

Tests:

```bash
python manage.py test --parallel 4
```

The project's runner starts every test in Uzbek and blanks the Telegram
settings, so a test run can never notify the real shop.

---

## What it does

- Every page in three languages, each under its own prefix: `/uz/`, `/ru/`, `/en/`
- Phone-number signup with SMS verification, and password reset by the same
  code — there is no email anywhere
- Catalogue with sizes, tags, search, filters and sorting; one heart saves a product
- Anonymous cart with snapshotted prices, merged into the account at sign-in;
  login is asked for at checkout
- Checkout to an Uzpost branch (region, district, postal index) or to the door
  (region, district, street, optional map pin); Click payment; row-locked order
  creation; orders numbered `GX-YYMMDD-NNNN`
- Reviews from verified buyers only, moderated, photographs re-encoded to strip
  their metadata
- A staff panel at `/uz/boshqaruv/` for orders, products, reviews, messages and
  reference data; the Django admin at `/admin/` behind it as a fallback
- Telegram notifications for paid orders, contact messages and reviews — an
  order is announced when its payment lands, never before
- Terms, privacy policy and delivery page, versioned
- Rate limiting on sign-in, OTP, password reset, contact, likes and reviews

## Built with

- **Django 6**, Python 3.12+, **PostgreSQL**
- **Redis** in production for the rate limiter's counters; in-memory locally
- **Click** for payment (`click-pkg`, imported as `click_up`), **Eskiz** for SMS
- **Telegram** notifications, directly or through the shop's own bot service
- **Google Maps** JavaScript API, optional, on the checkout only
- **gunicorn + nginx** on Ubuntu 24.04, HTTPS by Let's Encrypt, systemd
- Django templates, hand-written CSS (BEM, design tokens) and vanilla JS

## Layout

```
config/      settings, root URLs, wsgi/asgi
core/        site pages, legal documents, contact, Eskiz and Telegram clients,
             rate limiter, sitemaps, test runner — and the test suite
user/        phone-based User, auth, OTP, password reset, verification middleware
product/     catalogue: products, variants, tags, photos, likes, reviews, charts
cart/        carts for guests and for signed-in customers
payment/     checkout, delivery, regions, orders, Click
panel/       the staff panel (/boshqaruv/)
templates/   HTML (including robots.txt and site.webmanifest)
static/      CSS, JS, fonts, icons
locale/      uz, ru, en
data/        regions.csv, and how it was built
deploy/      nginx, systemd units, backups, the runbook
docs/        the plan, the architecture, integration contracts, brand, design
```

---

## Configuration

Everything is read from `.env` beside `manage.py`.
[`.env.example`](.env.example) lists every key with notes. The database, Click
and Eskiz keys fail loudly at startup if missing; Google Maps and Telegram are
optional, and without one the feature it switches on is simply off. Never
commit `.env`.

| Key | Purpose |
|-----|---------|
| `SECRET_KEY` | Django secret key — generate a fresh one |
| `DEBUG` | `True` locally, `False` in production |
| `ALLOWED_HOSTS` | Comma-separated hostnames |
| `CSRF_TRUSTED_ORIGINS` | Full origins allowed to POST; required in production |
| `DB_*` | PostgreSQL connection |
| `CLICK_*` | Click merchant credentials |
| `ESKIZ_*` | Eskiz account and sender name |
| `REDIS_URL` | Enables the Redis cache. **Required in production** — without it each gunicorn worker keeps its own rate-limit counters |
| `GOOGLE_MAPS_API_KEY` | Optional; the map pin on the home-delivery form |
| `TELEGRAM_BOT_WEBHOOK_URL`, `WEBSITE_WEBHOOK_SECRET` | Optional; notifications through the shop's bot service |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Optional; notifications straight to Telegram |
| `SITE_URL` | Base for the links inside those notifications |

## Integrations

- **Click** — one webhook at `/payment/click/update/`, outside the language
  prefixes, handling both Prepare and Complete. Register that exact URL, with
  the trailing slash. A redirect in front of it is a payment that fails
  silently.
- **Eskiz** — the sender name *and every message body* must be moderated before
  production sends succeed; `4546` is the test sender.
- **Telegram** — three events: a paid order, a contact message, a review
  awaiting moderation. Each is sent once, after the change it reports is saved.
  The contract is
  [`docs/integrations/telegram-bot.md`](docs/integrations/telegram-bot.md).
- **Google Maps** — the key ships in the page, so restrict it by referrer and
  set a budget alert. Geocoding needs billing enabled; without it the customer
  types the address, which is the same path a blocked script takes.

An outage in any of them turns a feature off. None of them can break a page.

## Deployment

[`deploy/RUNBOOK.md`](deploy/RUNBOOK.md) is the procedure, step by step, and
marks which steps need a password or an account only the owner has. The files
it installs are in [`deploy/`](deploy): the nginx site, the gunicorn unit, two
systemd timers, log rotation, and the backup and restore-verification scripts.

Backups are nightly: a PostgreSQL dump plus a hard-linked snapshot of
`media/`, both copied off the server. `deploy/bin/restore-check.sh` restores
the newest dump into a throwaway database and compares every table against the
counts recorded when the dump was taken. An untested backup is not a backup,
and the backup job deliberately fails rather than succeed without an
off-server destination.
