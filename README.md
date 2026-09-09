# GRAPHIX

Online graphic t-shirt store for Uzbekistan, built with Django and PostgreSQL.
Phone-based authentication (SMS OTP via Eskiz), Click payments, and an
Uzbek-language storefront.

Production: **https://graphix.uz** — not yet deployed; see `docs/PLAN.md`.

The Django project package is still named `vm/` and the repository is still
`ValleyMade`, both from the pre-rebrand name. Renaming them is deliberately
deferred — the plan explains why.

---

## Tech stack

- **Backend:** Django 6, Python 3.13
- **Database:** PostgreSQL 16
- **Cache / rate-limit store:** Redis (falls back to in-memory for local dev)
- **Payments:** Click (`click-up`)
- **SMS / OTP:** Eskiz.uz
- **Server:** Ubuntu, gunicorn + nginx, HTTPS via Let's Encrypt, systemd
- **Frontend:** Django templates, vanilla JS, CSS custom properties

## Features

- Phone-number signup with SMS OTP verification (no email)
- OTP-based password reset
- Product catalog with variants (size / colour / price), search, filter, sort
- Cart with price snapshotting and a single open cart per user
- Checkout with row-locked order creation and Click online payment
- Rate limiting on auth, OTP, password-reset and contact endpoints
- Uzbek-language UI throughout; admin panel with order/status management

## Rebuild in progress

This codebase is being rebuilt from ValleyMade into GRAPHIX. **`docs/PLAN.md` is
the single source of truth** — phases, locked decisions, conventions and
progress. Read it before changing anything.

## Project layout

```
vm/
├── core/       site pages, contact form, Eskiz SMS client, rate limiter, sitemaps
├── user/       custom phone-based User, auth, OTP, password reset, middleware
├── product/    catalog: categories, products, variants, images
├── cart/        cart and cart items
├── payment/    checkout, orders, Click integration
├── vm/         project settings, root URLs, wsgi/asgi
├── templates/  HTML templates (incl. robots.txt, site.webmanifest)
├── static/     source static assets
└── manage.py
```

## Local setup

```bash
git clone git@github.com:A-Kamronbek/ValleyMade.git
cd ValleyMade/vm   # repository name predates the GRAPHIX rebrand

python -m venv ../.venv
# Windows: ..\.venv\Scripts\activate   |   Linux/macOS: source ../.venv/bin/activate
pip install -r ../requirements.txt

cp .env.example .env          # then fill in real values (see below)

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Environment variables

All configuration is read from a `.env` file next to `manage.py`. See
[`.env.example`](vm/.env.example) for the full list and notes. Required keys
fail loudly at startup if missing. Never commit `.env`.

| Key | Purpose |
|-----|---------|
| `SECRET_KEY` | Django secret key (generate a fresh one) |
| `DEBUG` | `True` for local dev, `False` in production |
| `ALLOWED_HOSTS` | Comma-separated hostnames |
| `DB_*` | PostgreSQL connection (NAME/USER/PASSWORD/HOST/PORT) |
| `CLICK_*` | Click merchant credentials |
| `ESKIZ_*` | Eskiz SMS account + sender |
| `CSRF_TRUSTED_ORIGINS` | Full origins (with scheme) allowed to POST; required in production |
| `REDIS_URL` | Optional; enables the Redis cache backend |

## Integrations

- **Click** — single webhook endpoint at `/payment/click/update/` handles both
  Prepare and Complete (routed internally by `click_up`). Register that exact
  URL (with trailing slash) in the Click merchant dashboard.
- **Eskiz** — message templates must be moderated/approved before production
  sends will succeed; `4546` is the test sender.

## Deployment (summary)

Production will run on an Ubuntu 24.04 VPS (2 vCPU / 4 GB RAM / 40 GB SSD).
Provisioning is Phase 1b of the rebuild and has not happened yet:

1. Push code; clone on the server; create the venv and `pip install -r requirements.txt`.
2. Create the production `.env` (with `DEBUG=False`) and the PostgreSQL database.
3. `python manage.py migrate && python manage.py collectstatic --noinput`.
   Also `python manage.py compilemessages` — .mo files are build output and are not
   in the repository, so the site falls back to Uzbek everywhere without this step.
4. Run gunicorn under systemd, reverse-proxied by nginx (sockets, static/media).
5. Issue HTTPS certificates with certbot; the security settings in `settings.py`
   switch on automatically when `DEBUG=False`.
6. Register the Click webhook URL; verify a live payment end to end.
7. Install Redis and set `REDIS_URL` — the rate limiter needs a shared store to
   count correctly across gunicorn workers.
8. Schedule `pg_dump` and `media/` backups via cron, and verify a restore.

## Backups

A daily PostgreSQL dump is taken via cron (`pg_dump` + `~/.pgpass`). Copy dumps
off-server periodically — on-server backups don't survive a server loss.
