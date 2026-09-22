"""Django settings for the GRAPHIX project.

Secrets and environment-specific values are read from a ``.env`` file (loaded
below); required keys use ``os.environ[...]`` so a missing one fails loudly at
startup rather than running with an unsafe default.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = os.environ.get("DEBUG", "False") == "True"

AUTH_USER_MODEL = 'user.User'

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")

# Full origins (scheme + host) allowed to send state-changing POSTs. Needed once
# nginx terminates TLS: Django compares the Origin header against this list, and
# an empty list rejects every form submission on the live HTTPS domain.
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    # tolov's payment tables, and it sits HERE, above our own apps, on
    # purpose: `payment/admin.py` unregisters tolov's transaction admin, and
    # admin autodiscovery walks this list in order — below `payment` the
    # unregister runs before the register and quietly does nothing (§17 #263).
    #
    # It registers under the app label `django`, because its AppConfig sets no
    # `label` and Django derives one from the last component of
    # `tolov.integrations.django`. That is ugly — migrations print as
    # `django.0001_initial`, which reads like a core Django migration and is
    # not one — and it has to stay: the package's own second migration names
    # `('django', '0001_initial')` as a dependency, so relabelling the app
    # makes its migration graph unresolvable (§17 #261).
    'tolov.integrations.django',
    'core',
    'payment',
    'product',
    'user',
    'cart',
    # The staff panel (Phase 7). Views over the models above, plus the one
    # table that records who moved an order's status.
    'panel',
    'colorfield',
    'rest_framework',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # Must sit after SessionMiddleware (it reads the language from the session)
    # and before CommonMiddleware (which appends slashes using the active URLconf).
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'user.middleware.PhoneVerificationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
                'cart.context_processors.cart_count',
                'cart.context_processors.liked_count',
                'product.context_processors.nav_categories',
                'core.context_processors.languages',
                'core.context_processors.seo',
                'core.context_processors.size_guide',
                'core.context_processors.delivery_tiers',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'user.validators.CustomMinimumLengthValidator'},
]

TIME_ZONE = 'Asia/Tashkent'

# ---- languages ----
# Uzbek is the source of truth. All three languages carry a URL prefix - /uz/,
# /ru/, /en/ - see config/urls.py, where i18n_patterns is applied with
# prefix_default_language=True (§17 #121). Uzbek Latin is written with U+02BB
# (oʻ, gʻ), never an ASCII apostrophe.
LANGUAGE_CODE = 'uz'
LANGUAGES = [
    ('uz', "Oʻzbekcha"),
    ('ru', 'Русский'),
    ('en', 'English'),
]
LOCALE_PATHS = [BASE_DIR / 'locale']
USE_I18N = True

# The language cookie is only a fallback - the URL prefix decides the language.
# A year keeps a returning visitor on the language they chose.
LANGUAGE_COOKIE_NAME = 'graphix_lang'
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365
LANGUAGE_COOKIE_SAMESITE = 'Lax'

# ---- tests ----
# Every test starts in Uzbek whatever the previous one requested, and a failure
# under --parallel is reported as text instead of ending the run: tblib is not
# installed, so a traceback cannot be sent back from a worker (§17 #199).
TEST_RUNNER = 'core.runner.Runner'

# ---- static & media ----
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

#: True while `manage.py test` is running. Read from the command line because
#: the settings are imported before the test runner exists - and a worker
#: started by `--parallel` is handed the parent's argv, so it agrees.
TESTING = len(sys.argv) > 1 and sys.argv[1] == 'test'

# Hashed static filenames in production (§9 Phase 9 item 6), so nginx can serve
# every asset with a year's cache and a deploy still reaches the browser: the
# name changes with the content. Not in development, where the hash would
# change on every edit, and NOT under test: the manifest is written by
# `collectstatic`, and without one every `{% static %}` raises - the test runner
# turns DEBUG off, so this is the only thing separating a test run from a
# production one here.
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': (
        'django.contrib.staticfiles.storage.StaticFilesStorage'
        if DEBUG or TESTING
        else 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage')},
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---- auth redirects ----
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'shop'
LOGOUT_REDIRECT_URL = 'home'

# ---- production security ----
# Enforced only when DEBUG is off. SECURE_PROXY_SSL_HEADER is required because
# nginx terminates TLS and proxies to gunicorn over plain HTTP; without it
# SECURE_SSL_REDIRECT would loop forever (Django would never see "https").
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# --- payments (tolov) ---
# One dict, because that is the shape tolov reads (§17 #253).
#
# There is no AMOUNT_FIELD here and that is not an omission: tolov hardcodes
# `getattr(account, "amount", 0)` when it checks a callback's amount against
# the order, where click-pkg took the field name from a setting. `Order.amount`
# is a property returning `total_price` for exactly this, and the alternative
# — ONE_TIME_PAYMENT False — is not an alternative: it drops the amount
# check to "greater than zero", which would take 1 000 so'm for a 400 000
# so'm order (§17 #262).
CLICK_SERVICE_ID = os.environ["CLICK_SERVICE_ID"]
CLICK_MERCHANT_ID = os.environ["CLICK_MERCHANT_ID"]
CLICK_SECRET_KEY = os.environ["CLICK_SECRET_KEY"]

# Payme and Octo ship BLANK, and the feature is built around that, the same way
# the Maps key is (§17 #93): with no credentials the `PaymentOption` row stays
# switched off, the method is not offered at checkout and is refused
# server-side if one is POSTed anyway. `os.environ.get`, not `os.environ`:
# a missing key must not stop the site booting (§17 #264).
PAYME_ID = os.environ.get("PAYME_ID", "")
PAYME_KEY = os.environ.get("PAYME_KEY", "")
OCTO_SHOP_ID = os.environ.get("OCTO_SHOP_ID", "")
OCTO_SECRET = os.environ.get("OCTO_SECRET", "")
OCTO_UNIQUE_KEY = os.environ.get("OCTO_UNIQUE_KEY", "")

TOLOV = {
    "CLICK": {
        "SERVICE_ID": CLICK_SERVICE_ID,
        "MERCHANT_ID": CLICK_MERCHANT_ID,
        "SECRET_KEY": CLICK_SECRET_KEY,
        "ACCOUNT_MODEL": "payment.models.Order",
        "ACCOUNT_FIELD": "id",
        "ONE_TIME_PAYMENT": True,
        "COMMISSION_PERCENT": 0.0,
    },
    # Payme and Octo both take the field name from a setting, so they are
    # told `total_price` outright. Click cannot be told (§17 #262) and reads
    # `Order.amount`, which is the same number under the name it insists on.
    # Payme quotes tiyin and tolov multiplies by 100 on our behalf; Click and
    # Octo quote soʻm and it does not.
    "PAYME": {
        "PAYME_ID": PAYME_ID,
        "PAYME_KEY": PAYME_KEY,
        "ACCOUNT_MODEL": "payment.models.Order",
        # `order_id`, not `id`, and the two ends have to agree: this name is
        # the key inside Payme's `account` object AND what the webhook looks
        # the order up by, with tolov special-casing `order_id` to mean the
        # model's `id`. It is also the default `create_payment` builds the
        # link with, so leaving both at the library's own pairing is the
        # tested path — and `order_id` is what a Payme merchant cabinet is
        # normally configured with anyway.
        "ACCOUNT_FIELD": "order_id",
        "AMOUNT_FIELD": "total_price",
        "ONE_TIME_PAYMENT": True,
    },
    "OCTO_BANK": {
        # int, not text: tolov types this one. Blank until the owner has a
        # shop id, and `int("")` raises, so the coercion tolerates empty.
        "OCTO_SHOP_ID": int(OCTO_SHOP_ID or 0),
        "OCTO_SECRET": OCTO_SECRET,
        "OCTO_UNIQUE_KEY": OCTO_UNIQUE_KEY,
        "ACCOUNT_MODEL": "payment.models.Order",
        "ACCOUNT_FIELD": "id",
        "AMOUNT_FIELD": "total_price",
        "ONE_TIME_PAYMENT": True,
        "TEST_MODE": DEBUG,
    },
}

# --- eskiz SMS ---
# ESKIZ_FROM defaults to Eskiz's test sender (4546); set the approved sender in prod.
ESKIZ_EMAIL = os.environ["ESKIZ_EMAIL"]
ESKIZ_PASSWORD = os.environ["ESKIZ_PASSWORD"]
ESKIZ_FROM = os.environ.get("ESKIZ_FROM", "4546")

# --- Google Maps ---
# The map on the home-delivery half of checkout. It ships BLANK and the feature
# is built around that (§17 #93): with no key the map block simply does not
# render and the address field carries the form on its own, which is the
# behaviour a blocked script or a denied permission has to produce anyway.
# Turning the map on is a paste into the server .env, not a deploy.
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# --- Telegram ---
# Order, payment, message and review notifications to the shop's staff. Blank
# for the same reason: core/telegram.py logs a warning and sends nothing rather
# than raising, so local development and a fresh deploy are unaffected.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# The shop's own bot service. With the URL set, every notification is POSTed
# there as signed JSON and the bot delivers it - the token and chat id above
# are then unused. The secret is the one the bot holds as well; it lives in the
# two .env files and nowhere else (§17 #206, docs/integrations/telegram-bot.md).
TELEGRAM_BOT_WEBHOOK_URL = os.environ.get("TELEGRAM_BOT_WEBHOOK_URL", "")
WEBSITE_WEBHOOK_SECRET = os.environ.get("WEBSITE_WEBHOOK_SECRET", "")

# Used to build absolute links in notifications, which are read outside any
# request and so cannot ask one for the host.
SITE_URL = os.environ.get("SITE_URL", "https://graphix.uz")

# Whether search engines may index this site at all. True everywhere by
# default, including in tests; the server sets it False until the catalogue
# is loaded, so Google's first impression of graphix.uz is not a shop with
# nothing in it and a home page promising a hundred designs (§19 Q37).
#
# The default is deliberately the permissive one. A noindex left on by
# accident after launch is invisible and costs months of traffic; an Allow
# left on before launch is a bad afternoon. Phase 11 deletes the variable.
SITE_INDEXABLE = os.environ.get("SITE_INDEXABLE", "True") == "True"

# ---- cache ----
# Use Redis when REDIS_URL is set: it's shared across gunicorn workers, which the
# rate limiter needs to count correctly. Otherwise fall back to per-process memory
# (fine for a single worker / local dev, but counters aren't shared).
REDIS_URL = os.environ.get("REDIS_URL")
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }

# ---- logging ----
# Console logging always; in production also write a rotating file in logs/.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{asctime} {levelname} {name}: {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'verbose'},
    },
    'loggers': {
        'core':    {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'payment': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'user':    {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'cart':    {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'product': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'django':  {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}

# How long the application's own log is kept, in days. The privacy policy
# states this figure - core/legal.py reads it from here - so the file rotates
# by day rather than by size: a size-rotated log keeps a phone number from a
# failed SMS for however long 25 MB takes to fill, which nobody can promise
# a customer (§17 #196). The web server's own access log is rotated to the
# same period on the VPS (plan §9 Phase 1b).
LOG_RETENTION_DAYS = 30

if not DEBUG:
    LOG_DIR = BASE_DIR / 'logs'
    LOG_DIR.mkdir(exist_ok=True)
    LOGGING['handlers']['file'] = {
        'class': 'logging.handlers.TimedRotatingFileHandler',
        'filename': str(LOG_DIR / 'app.log'),
        'when': 'midnight',
        'backupCount': LOG_RETENTION_DAYS,
        'encoding': 'utf-8',
        'formatter': 'verbose',
    }
    for _name in ('core', 'payment', 'user', 'cart', 'product', 'django'):
        LOGGING['loggers'][_name]['handlers'] = ['console', 'file']
