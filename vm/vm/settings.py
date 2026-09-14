"""Django settings for the GRAPHIX project.

Secrets and environment-specific values are read from a ``.env`` file (loaded
below); required keys use ``os.environ[...]`` so a missing one fails loudly at
startup rather than running with an unsafe default.
"""
import os
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
    'click_up',
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

ROOT_URLCONF = 'vm.urls'

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
                'core.context_processors.size_guide',
                'core.context_processors.delivery_tiers',
            ],
        },
    },
]

WSGI_APPLICATION = 'vm.wsgi.application'

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
# /ru/, /en/ - see vm/urls.py, where i18n_patterns is applied with
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

# ---- static & media ----
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

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

# --- click ---
# click_up validates each payment callback's amount against the account model's
# amount field below (Order.total_price, stored in whole so'm).
CLICK_SERVICE_ID = os.environ["CLICK_SERVICE_ID"]
CLICK_MERCHANT_ID = os.environ["CLICK_MERCHANT_ID"]
CLICK_SECRET_KEY = os.environ["CLICK_SECRET_KEY"]
CLICK_ACCOUNT_MODEL = "payment.models.Order"
CLICK_AMOUNT_FIELD = "total_price"

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
# Order, payment, message and review notifications to the owner's phone. Blank
# for the same reason: core/telegram.py logs a warning and sends nothing rather
# than raising, so local development and a fresh deploy are unaffected.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Used to build absolute links in notifications, which are read outside any
# request and so cannot ask one for the host.
SITE_URL = os.environ.get("SITE_URL", "https://graphix.uz")

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

if not DEBUG:
    LOG_DIR = BASE_DIR / 'logs'
    LOG_DIR.mkdir(exist_ok=True)
    LOGGING['handlers']['file'] = {
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': str(LOG_DIR / 'app.log'),
        'maxBytes': 5 * 1024 * 1024,
        'backupCount': 5,
        'formatter': 'verbose',
    }
    for _name in ('core', 'payment', 'user', 'cart', 'product', 'django'):
        LOGGING['loggers'][_name]['handlers'] = ['console', 'file']
