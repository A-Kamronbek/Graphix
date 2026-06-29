"""
Django settings for vm project.

Modified to wire up project-level templates, static, and auth redirects.
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

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'payment',
    'product',
    'user',
    'cart',
    'colorfield',
    'rest_framework',
    'click_up',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
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
        # project-level templates folder (where base.html lives)
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # custom — exposes cart_count to all templates for the nav badge
                'cart.context_processors.cart_count',
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
    # {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'user.validators.CustomMinimumLengthValidator'},
    # {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    # {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
TIME_ZONE = 'Asia/Tashkent'
LANGUAGE_CODE = 'uz'
USE_I18N = True

# ---- static & media ----
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'  # for `collectstatic` in production

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---- auth redirects ----
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'shop'
LOGOUT_REDIRECT_URL = 'home'

# ---- production security ----
# Only enforced when DEBUG is False so local dev over http still works.
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
CLICK_SERVICE_ID = os.environ["CLICK_SERVICE_ID"]
CLICK_MERCHANT_ID = os.environ["CLICK_MERCHANT_ID"]
CLICK_SECRET_KEY = os.environ["CLICK_SECRET_KEY"]
CLICK_ACCOUNT_MODEL = "payment.models.Order"
CLICK_AMOUNT_FIELD = "total_price"

# --- SMS ---
# --- eskiz sms ---
ESKIZ_EMAIL = os.environ["ESKIZ_EMAIL"]
ESKIZ_PASSWORD = os.environ["ESKIZ_PASSWORD"]
ESKIZ_FROM = os.environ.get("ESKIZ_FROM", "4546")

# ---- cache ----
# Dev (default): in-process LocMemCache — same behavior as before. Production:
# set REDIS_URL so the rate limiter and the Eskiz SMS-token cache are SHARED
# across gunicorn workers (LocMemCache is per-process). Needs `pip install redis`.
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
# Console everywhere; in production also a rotating file so SMS/payment errors
# are retained. 'django.server' is left untouched so runserver request logs are
# unchanged.
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