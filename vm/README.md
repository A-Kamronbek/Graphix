# VM Graphics — frontend pack

Server-rendered Django frontend for the VM Graphics e-shop. Black-primary,
brutal-bold typography, minimal lines. No APIs, no JS framework — plain
Django templates + a small `main.js`.

---

## What's included

```
vm/
├── vm/
│   ├── settings.py        # ← REPLACED (templates dir, static, media, login redirects, cart context processor)
│   └── urls.py            # ← REPLACED (wires every app + serves media in dev + 404/500 handlers)
│
├── core/
│   ├── urls.py            # ← NEW
│   └── views.py           # ← REPLACED (home, about, contact + 404/500 handlers)
│
├── user/
│   ├── urls.py            # ← NEW
│   ├── views.py           # ← REPLACED (login, signup, account, account_orders, logout)
│   └── forms.py           # ← NEW (LoginForm, SignupForm with phone field)
│
├── product/
│   ├── urls.py            # ← NEW
│   └── views.py           # ← REPLACED (shop with filters/search/sort, item with variants)
│
├── cart/
│   ├── urls.py            # ← NEW
│   ├── views.py           # ← REPLACED (cart, add, update, remove)
│   └── context_processors.py  # ← NEW (cart_count badge in nav)
│
├── payment/
│   ├── urls.py            # ← NEW
│   └── views.py           # ← REPLACED (checkout, payment-stub, status, order_detail, cancel)
│
├── templates/             # ← NEW (project-wide)
│   ├── base.html
│   ├── 404.html / 500.html
│   ├── partials/   _nav.html · _footer.html · _marquee.html
│   ├── core/       home.html · about.html · contact.html
│   ├── user/       login.html · signup.html · account.html · account_orders.html
│   ├── product/    shop.html · item.html
│   ├── cart/       cart.html
│   └── payment/    checkout.html · payment.html · status.html · order_detail.html
│
└── static/                # ← NEW
    ├── css/main.css
    └── js/main.js
```

Files I **did not** touch: every `models.py`, `admin.py`, `apps.py`, `migrations/`, `manage.py`, your `media/` folder. Drop-in safe.

---

## Setup

```bash
# 1. install deps (you already have these but for reference)
pip install "django>=6.0" psycopg[binary] django-colorfield Pillow

# 2. make sure Postgres is running with the creds in settings.py
#    (mydb / myuser / mypassword on localhost:5432)

# 3. migrate
python manage.py migrate
python manage.py createsuperuser

# 4. (optional) seed some products through /admin/ — Categories,
#    Sizes, Colours, then a Product with at least one Variant per
#    size/colour combo so the item page has something to show.

# 5. run
python manage.py runserver
```

Then visit:

| URL                    | Page                    |
|------------------------|-------------------------|
| `/`                    | Home                    |
| `/about/`              | About                   |
| `/contact/`            | Contact                 |
| `/login/`              | Log in                  |
| `/signup/`             | Sign up                 |
| `/account/`            | Account overview        |
| `/account/orders/`     | All orders              |
| `/shop/`               | Shop                    |
| `/item/<id>/`          | Product detail          |
| `/cart/`               | Cart                    |
| `/checkout/`           | Checkout (places order) |
| `/payment/<order_id>/` | Pay with Click (stub)   |
| `/order/<id>/`         | Order detail            |
| `/order/<id>/status/`  | Live status timeline    |
| `/admin/`              | Django admin            |

---

## How the order flow works

```
Cart (status=True, open)
   │  POST /checkout/
   ▼
Order (status='paying')   ← cart is closed (status=False), new cart will open on next add
   │  GET /payment/<id>/
   ▼
[Click] ← TODO: real payment gateway, see payment/views.py::payment_start
   │
   ▼
Order.status flow on the timeline:
   active → paying → paid → processing → on_the_way → done
                                                    ↘ cancelled
```

The `templates/payment/status.html` page renders this whole timeline visually,
highlighting wherever the order currently sits.

---

## Click integration — the one TODO

Look in `payment/views.py` at the `payment_start` view. The docstring inside
that view tells you exactly which steps to fill in. Click in Uzbekistan uses
**SHOP-API** with two server-to-server callbacks (`Prepare` and `Complete`),
plus a redirect to `https://my.click.uz/services/pay`. When you wire it up:

1. Add a small `Transaction` model linking Click's `click_trans_id` to your
   `Order`.
2. In `payment_start`, build the redirect URL with your `merchant_id`,
   `service_id`, `amount=order.total_price`, `transaction_param=order.id`,
   and return an `HttpResponseRedirect` to it.
3. Add two more URLs (`/click/prepare/`, `/click/complete/`) that accept
   POSTs from Click and update `Order.status` to `paid` on success.
4. Set the **Return URL** in your Click merchant dashboard to
   `/order/<order_id>/status/` so users land on the timeline page after paying.

The payment template already shows the order summary and a disabled
"Continue to Click →" button — just remove the `disabled` attribute and
swap the form action once `payment_start` does the real redirect.

---

## Suggestions for what to build next

These weren't in your original list but they'll matter once real users hit the site:

- **Forgot / reset password** — Django's built-in `django.contrib.auth.views.PasswordResetView` covers it; just add four templates.
- **Saved addresses** — your `Order.address` is a single CharField. Add a `UserAddress(user, label, line, city, default)` model so customers don't retype on every order.
- **Wishlist** — simple `Wishlist(user, variant)` join table. Heart icon on the item / shop tiles.
- **Size guide** — clothing shops live and die by this. Static page or a modal triggered from the item page.
- **Drops / lookbook** — given the "limited drops" branding, a curated page per drop would suit the aesthetic better than a flat shop grid forever.
- **Stock counters** — your `Variant` only has a `available: bool`. A `stock` integer would let you say "Only 3 left" on the item page (a strong nudge in clothing).
- **Order email confirmation** — fires from `payment/views.py::checkout` after order creation.
- **Privacy / Terms / Shipping / Returns** — the footer links to them but they're stubs.
- **Phone field on the user** — my `SignupForm` accepts `phone` but the default Django `User` model has no place to store it. Add a `UserProfile(user, phone)` model and persist it in `SignupForm.save()` (there's a comment marking the spot).

---

## Style notes — so future edits stay on-brand

- Black `#000` background everywhere. White is the only accent.
- Bold uppercase `Helvetica/Arial Black`-style display type for headings.
- `JetBrains Mono` (monospace) for labels, prices, breadcrumbs, status pills.
- No drop shadows, no gradients (except a subtle bottom-of-tile fade for legibility).
- 1px hairline borders (`var(--line)` = `#2a2a2a`) for separators and form fields.
- Buttons invert on hover: outline → solid, or solid → outline.
- Marquee strips at the top of every page and accent breaks between sections — that's the brand asset come to life.
- Stars (`★`) are sprinkled but never overdone.
- Use the existing CSS vars in `:root` rather than hardcoding hex codes when you extend.

That's it. If you want me to wire up Click for real, drop me your merchant docs and I'll write the `Transaction` model + the two callback views.
