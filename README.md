# GRAPHIX

[![CI](https://github.com/A-Kamronbek/Graphix/actions/workflows/ci.yml/badge.svg)](https://github.com/A-Kamronbek/Graphix/actions/workflows/ci.yml)

Online store for graphic T-shirts in Uzbekistan. Django and PostgreSQL,
server-rendered, no build step. Phone-number accounts verified by SMS, four
payment methods, Uzpost delivery, and a storefront written in Uzbek, Russian
and English.

Production: **https://graphix.uz**

| | |
|---|---|
| How it works | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| How to change it | [`CONTRIBUTING.md`](CONTRIBUTING.md) |

---

## Running it locally

Needs Python 3.12 or newer, PostgreSQL, and GNU gettext.

```bash
git clone git@github.com:A-Kamronbek/Graphix.git
cd Graphix

python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # fill in DB_* at least

python manage.py migrate
python manage.py seed_regions              # the checkout's regions and districts
python manage.py compilemessages --ignore .venv
python manage.py createsuperuser
python manage.py runserver                 # http://127.0.0.1:8000/uz/
```

Two things that catch people out:

**Verify your own phone before visiting any page.** `createsuperuser` leaves
the account unverified, and every page outside `/admin/` sends an unverified
account to the SMS code screen, superuser or not. Sign in at
`http://127.0.0.1:8000/admin/`, open your user, fill in the phone and tick
**phone_verified**. An unverified account left on the code screen until the
window lapses is deleted.

**`compilemessages` needs `--ignore .venv`.** The apps live at the repository
root, so without it the command walks into the virtualenv and recompiles every
catalogue Django ships. `makemessages` needs its own ignore list; see
[`CONTRIBUTING.md`](CONTRIBUTING.md).

`python manage.py seed_demo_catalogue` loads eight demo designs. It replaces
the catalogue and refuses to run against anything but a local database.

Tests:

```bash
python manage.py test --parallel 4
```

The test runner starts every test in Uzbek and blanks the Telegram settings,
so a test run cannot notify the real shop.

---

## What it does

- Every page in three languages, each under its own prefix: `/uz/`, `/ru/`, `/en/`
- Phone-number signup with SMS verification, and password reset by the same
  code. There is no email anywhere.
- Catalogue with sizes, tags, search, filters and sorting; one heart saves a
  product
- Anonymous cart with snapshotted prices, merged into the account at sign-in.
  Login is asked for at checkout.
- Checkout to an Uzpost branch (region, district, postal index) or to the door
  (region, district, street, optional map pin). Row-locked order creation,
  orders numbered `GX-YYMMDD-NNNN`.
- Four payment methods, each switched on or off from the staff panel: Click,
  Payme, Octo and cash
- Reviews from verified buyers only, moderated, photographs re-encoded to strip
  their metadata
- A staff panel at `/uz/boshqaruv/` for orders, products, reviews, messages and
  reference data, with the Django admin behind it as a fallback
- Telegram notifications for paid orders, contact messages and reviews. An
  order is announced when its payment lands, never before.
- Terms, privacy policy and delivery page, versioned
- Rate limiting on sign-in, OTP, password reset, contact, likes and reviews
- A Content-Security-Policy with a per-request nonce

## Built with

- **Django 6**, Python 3.12+, **PostgreSQL**
- **Redis** in production for the rate limiter's counters; in-memory locally
- **tolov** for Click, Payme and Octo payments, **Eskiz** for SMS
- **Telegram** notifications, directly or through the shop's own bot service
- **Google Maps** JavaScript API, optional, on the checkout only
- **gunicorn + nginx** on Ubuntu 24.04, HTTPS by Let's Encrypt, systemd
- Django templates, hand-written CSS (BEM, design tokens) and vanilla JS

## Layout

```
config/      settings, root URLs, wsgi/asgi
core/        site pages, legal documents, contact, Eskiz and Telegram clients,
             rate limiter, CSP middleware, sitemaps, test runner, test suite
user/        phone-based User, auth, OTP, password reset, verification middleware
product/     catalogue: products, variants, tags, photos, likes, reviews, charts
cart/        carts for guests and for signed-in customers
payment/     checkout, delivery, regions, orders, the payment gateways
panel/       the staff panel (/boshqaruv/)
templates/   HTML (including robots.txt and site.webmanifest)
static/      CSS, JS, fonts, icons
locale/      uz, ru, en
data/        regions.csv, the demo catalogue, product-copy guidance
deploy/      nginx, systemd units, log rotation, backup and restore scripts
docs/        architecture and integration contracts
```

---

## Configuration

Everything is read from `.env` beside `manage.py`.
[`.env.example`](.env.example) lists every key with notes. The database, Click
and Eskiz keys fail at startup if missing. Google Maps, Payme, Octo and
Telegram are optional, and without one the feature it switches on stays off.
Never commit `.env`.

| Key | Purpose |
|-----|---------|
| `SECRET_KEY` | Django secret key; generate a fresh one |
| `DEBUG` | `True` locally, `False` in production |
| `ALLOWED_HOSTS` | Comma-separated hostnames |
| `CSRF_TRUSTED_ORIGINS` | Full origins allowed to POST; required in production |
| `DB_*` | PostgreSQL connection |
| `CLICK_*` | Click merchant credentials |
| `PAYME_*`, `OCTO_*` | Payme and Octo credentials; blank until the merchant accounts exist |
| `ESKIZ_*` | Eskiz account and sender name |
| `REDIS_URL` | Enables the Redis cache. Required in production: without it each gunicorn worker keeps its own rate-limit counters. |
| `GOOGLE_MAPS_API_KEY` | Optional; the map pin on the home-delivery form |
| `TELEGRAM_BOT_WEBHOOK_URL`, `WEBSITE_WEBHOOK_SECRET` | Optional; notifications through the shop's bot service |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Optional; notifications straight to Telegram |
| `SITE_URL` | Base for the links inside those notifications |

## Integrations

Each payment gateway has one webhook, mounted outside the language prefixes:

| Gateway | Webhook |
|---|---|
| Click | `/payment/click/update/` |
| Payme | `/payment/payme/update/` |
| Octo | `/payment/octo/update/` |

Register those exact paths, with the trailing slash. A redirect in front of
one is a payment that fails with no error on either side. Octo additionally
needs `OCTO_UNIQUE_KEY` in production: it signs the callback, and the site
treats Octo as unconfigured without it rather than accept a payment it could
not confirm.

**Eskiz** moderates the sender name and every message body before production
sends succeed; `4546` is the test sender.

**Telegram** reports three events: a paid order, a contact message, and a
review awaiting moderation. Each is sent once, after the change it reports is
saved. The message contract is
[`docs/integrations/telegram-bot.md`](docs/integrations/telegram-bot.md).

**Google Maps** ships its key in the page, so restrict it by referrer and set
a budget alert. Geocoding needs billing enabled; without it the customer types
the address, which is also what happens when the script is blocked.

An outage in any of these turns a feature off. None of them can break a page.

## Deployment

`deploy/` holds what the server runs: the nginx site, the gunicorn unit, two
systemd timers, log rotation, and the backup and restore-verification scripts.

Backups are nightly: a PostgreSQL dump plus a hard-linked snapshot of
`media/`, both copied off the server. `deploy/bin/restore-check.sh` restores
the newest dump into a throwaway database and compares every table against the
counts recorded when the dump was taken. The backup job fails rather than
report success without an off-server destination.
