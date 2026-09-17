# GRAPHIX

Online store for graphic T-shirts in Uzbekistan, built with Django and
PostgreSQL. Phone-based accounts (SMS OTP via Eskiz), Click payments, Uzpost
delivery, and a storefront in Uzbek, Russian and English — Uzbek first.

Production: **https://graphix.uz** — not deployed yet; see `docs/PLAN.md`.

The repository is `Graphix`; the Django project package inside it is still
named `vm/`, from the pre-rebrand name, and the local working folder may still
be called `ValleyMade`. Renaming the package is deliberately deferred until
after launch — the plan explains why.

---

## Rebuild in progress

This codebase is being rebuilt from ValleyMade into GRAPHIX. **`docs/PLAN.md` is
the single source of truth** — phases, locked decisions, conventions and
progress. Read it before changing anything.

## Tech stack

- **Backend:** Django 6, Python 3.13
- **Database:** PostgreSQL
- **Cache / rate-limit store:** Redis in production; in-memory locally when `REDIS_URL` is unset
- **Payments:** Click (the `click-pkg` package, imported as `click_up`)
- **SMS / OTP:** Eskiz.uz
- **Notifications:** Telegram — directly, or through the shop's own bot service
- **Maps:** Google Maps JavaScript API, optional, on the checkout only
- **Server:** Ubuntu 24.04 VPS (OVHcloud, Warsaw), gunicorn + nginx, HTTPS via Let's Encrypt, systemd
- **Frontend:** Django templates, hand-written CSS (BEM, design tokens) and vanilla JS — no build step

## Features

- Every page in three languages, each under its own prefix: `/uz/`, `/ru/`, `/en/`
- Phone-number signup with SMS OTP verification, and OTP password reset (no email)
- Catalogue with sizes, tags, search, filters and sorting; one heart saves a product
- Anonymous cart with price snapshots; login is asked for at checkout
- Checkout: delivery to an Uzpost branch (region, district, postal index) or to the
  door (region, district, street, optional map pin); Click payment; row-locked order
  creation; orders numbered `GX-YYMMDD-NNNN`
- Reviews from verified buyers only, moderated, with photos re-encoded to strip
  their metadata
- Staff panel at `/uz/boshqaruv/` for orders, products, reviews, messages and
  reference data; the Django admin at `/admin/` remains as the fallback
- Telegram notifications for new orders, payments, contact messages and reviews
- Terms, privacy policy and delivery page, versioned
- Rate limiting on sign-in, OTP, password reset, contact, likes and reviews

## Project layout

```
vm/
├── core/       site pages, legal documents, contact form, Eskiz and Telegram
│               clients, rate limiter, sitemaps, test runner — and the test suite
├── user/       phone-based User, auth, OTP, password reset, verification middleware
├── product/    catalogue: products, variants, tags, photos, likes, reviews, size charts
├── cart/       carts for guests and signed-in customers
├── payment/    checkout, delivery and payment options, regions, orders, Click
├── panel/      the staff panel (/boshqaruv/)
├── vm/         settings, root URLs, wsgi/asgi
├── templates/  HTML templates (incl. robots.txt, site.webmanifest)
├── static/     CSS, JS, fonts, icons, the share image
├── locale/     uz, ru and en translation catalogues
├── data/       regions.csv, and how it was built
└── manage.py
deploy/
└── nginx/      the production web-server config (compression, caching, HTTP/2)
docs/
├── PLAN.md        the plan — read it first
├── integrations/  what the site sends to the Telegram bot service
├── brand/         brand sources, including the share card
├── content/       how product descriptions are written
└── design/        design references and the demo catalogue's photographs
```

## Local setup

```bash
git clone git@github.com:A-Kamronbek/Graphix.git
cd Graphix/vm   # the package is still `vm`, from the pre-rebrand name

python -m venv ../.venv
# Windows: ..\.venv\Scripts\activate   |   Linux/macOS: source ../.venv/bin/activate
pip install -r ../requirements.txt

cp .env.example .env          # then fill in real values (see below)

python manage.py migrate
python manage.py seed_regions         # regions and districts for the checkout
python manage.py compilemessages      # needs GNU gettext; .mo files are not tracked
python manage.py createsuperuser
python manage.py runserver            # then open http://127.0.0.1:8000/uz/
```

`createsuperuser` leaves the new account's phone unverified, and every page
outside `/admin/` sends an unverified account to the SMS code screen. Sign in
at `http://127.0.0.1:8000/admin/` first, open your own user, fill in the phone
and tick **phone_verified**, and the storefront and the panel both open (§19
Q34). Do that before visiting any other page: an unverified account that sits
on the code screen until the window lapses is deleted, superuser or not.

`python manage.py seed_demo_catalogue` replaces the local catalogue with the
eight demo designs every screenshot is measured against. It deletes catalogue
data and orders, and refuses to run against anything but a local database.

Tests: `python manage.py test --parallel 4`. The project's runner starts every
test in Uzbek and blanks the Telegram settings, so a test run never notifies
the shop.

## Environment variables

All configuration is read from a `.env` file next to `manage.py`. See
[`.env.example`](vm/.env.example) for the full list and notes. Required keys
(the database, Click and Eskiz) fail loudly at startup if missing. The Google
Maps and Telegram keys are optional: without one, the feature it switches on is
simply off. Never commit `.env`.

| Key | Purpose |
|-----|---------|
| `SECRET_KEY` | Django secret key (generate a fresh one) |
| `DEBUG` | `True` for local dev, `False` in production |
| `ALLOWED_HOSTS` | Comma-separated hostnames |
| `CSRF_TRUSTED_ORIGINS` | Full origins (with scheme) allowed to POST; required in production |
| `DB_*` | PostgreSQL connection (NAME/USER/PASSWORD/HOST/PORT) |
| `CLICK_*` | Click merchant credentials |
| `ESKIZ_*` | Eskiz SMS account and sender |
| `GOOGLE_MAPS_API_KEY` | Optional; the map pin on the home-delivery form |
| `TELEGRAM_BOT_WEBHOOK_URL`, `WEBSITE_WEBHOOK_SECRET` | Optional; send notifications through the shop's bot service |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Optional; send notifications to Telegram directly |
| `SITE_URL` | Base for the links inside notifications |
| `REDIS_URL` | Optional; enables the Redis cache backend |

## Integrations

- **Click** — one webhook endpoint at `/payment/click/update/`, outside the
  language prefixes, handles both Prepare and Complete (routed internally by
  `click_up`). Register that exact URL (with the trailing slash) in the Click
  merchant dashboard.
- **Eskiz** — the sender name and every message body must be moderated before
  production sends succeed; `4546` is the test sender.
- **Telegram** — with `TELEGRAM_BOT_WEBHOOK_URL` set, each event is POSTed to the
  bot service, signed with `WEBSITE_WEBHOOK_SECRET`; otherwise the site calls the
  Bot API with the token and chat ID. The contract is
  [`docs/integrations/telegram-bot.md`](docs/integrations/telegram-bot.md).
- **Google Maps** — the key ships in the page, so restrict it to the site's
  referrers and set a budget alert. Geocoding needs billing enabled on the
  Google Cloud project; without it the customer types the address.

An outage in any of them turns a feature off; it never breaks a page.

## Deployment (summary)

The server is bought — an Ubuntu 24.04 VPS at OVHcloud in Warsaw (2 vCore /
4 GB RAM / 40 GB SSD) — and not provisioned yet. Provisioning is Phase 1b of the
rebuild and runs after Phase 10:

1. Clone the code on the server; create the venv and `pip install -r requirements.txt`.
2. Create the production `.env` (with `DEBUG=False`) and the PostgreSQL database.
3. `python manage.py migrate && python manage.py seed_regions && python manage.py collectstatic --noinput`.
   Also `python manage.py compilemessages` — .mo files are build output and are not
   in the repository, so the site falls back to Uzbek everywhere without this step.
   With `DEBUG=False` the static files are served under hashed names, so
   `collectstatic` is not optional: without it every page raises on the first
   `{% static %}`.
4. Run gunicorn under systemd, reverse-proxied by nginx — `deploy/nginx/graphix.conf`
   is the config, with gzip, a year's cache on the hashed assets, HTTP/2 and the
   upload ceiling a phone photograph needs.
5. Issue HTTPS certificates with certbot; the security settings in `settings.py`
   switch on automatically when `DEBUG=False`.
6. Register the Click webhook URL; verify a live payment end to end.
7. Install Redis and set `REDIS_URL` — the rate limiter needs a shared store to
   count correctly across gunicorn workers.
8. Schedule `python manage.py prune_guest_carts` daily — the privacy policy says a
   guest cart is deleted after thirty days, and nothing else deletes one — and give
   nginx's access log the same thirty-day rotation the Django log already has.
9. Schedule nightly `pg_dump` and `media/` backups, copied off-server, and verify a
   restore before the site takes a real order.
10. `python manage.py build_renditions` once, after the first deploy and after
    restoring a media folder: photographs uploaded before Phase 9 have no WebP
    renditions, and until they do they are served at full size. New uploads
    build their own.

## Backups

Not running yet — they are set up with the server (step 9 above): a nightly
PostgreSQL dump (`pg_dump` + `~/.pgpass`) and a copy of `media/`, both copied
off-server. On-server backups don't survive a server loss, and an untested
backup is not a backup.
