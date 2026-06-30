# ValleyMade

E-commerce clothing store for Uzbek-speaking customers, built with Django and
PostgreSQL. Phone-based authentication (SMS OTP via Eskiz), Click payments, and
an Uzbek-language storefront with a custom dark theme.

Production: **https://valleymade.uz**

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

## Project layout

```
vm/
├── core/       site pages, contact form, Eskiz SMS client, rate limiter, sitemaps
├── user/       custom phone-based User, auth, OTP, password reset, middleware
├── product/    catalog: categories, products, variants, images
├── cart/        cart and cart items
├── payment/    checkout, orders, Click integration
├── vm/         project settings, root URLs, wsgi/asgi
├── templates/  HTML templates (incl. robots.txt)
├── static/     source static assets
└── manage.py
```

## Local setup

```bash
git clone git@github.com:A-Kamronbek/ValleyMade.git
cd ValleyMade/vm

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
| `REDIS_URL` | Optional; enables the Redis cache backend |

## Integrations

- **Click** — single webhook endpoint at `/payment/click/update/` handles both
  Prepare and Complete (routed internally by `click_up`). Register that exact
  URL (with trailing slash) in the Click merchant dashboard.
- **Eskiz** — message templates must be moderated/approved before production
  sends will succeed; `4546` is the test sender.

## Deployment (summary)

Production runs on an Ubuntu VPS:

1. Push code; clone on the server; create the venv and `pip install -r requirements.txt`.
2. Create the production `.env` (with `DEBUG=False`) and the PostgreSQL database.
3. `python manage.py migrate && python manage.py collectstatic --noinput`.
4. Run gunicorn under systemd, reverse-proxied by nginx (sockets, static/media).
5. Issue HTTPS certificates with certbot; the security settings in `settings.py`
   switch on automatically when `DEBUG=False`.
6. Register the Click webhook URL; verify a live payment end to end.
7. Schedule `pg_dump` backups via cron.

## Backups

A daily PostgreSQL dump is taken via cron (`pg_dump` + `~/.pgpass`). Copy dumps
off-server periodically — on-server backups don't survive a server loss.
