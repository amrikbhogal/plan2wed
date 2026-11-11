"""Settings for the Plan2Wed VPS behind its trusted Nginx proxy."""
from .settings import *  # noqa: F403
from django.core.exceptions import ImproperlyConfigured

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY to a fixed random secret of at least 50 characters.")

DEBUG = False
ALLOWED_HOSTS = ["plan2wed.co.uk", "www.plan2wed.co.uk"]
CSRF_TRUSTED_ORIGINS = ["https://plan2wed.co.uk", "https://www.plan2wed.co.uk"]
# SQLite remains available explicitly for the initial data export.
if os.environ.get("DJANGO_DATABASE", "sqlite") == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "plan2wed",
            "USER": "plan2wed",
            "HOST": "/var/run/postgresql",
            "PORT": "5432",
            "CONN_MAX_AGE": 60,
            "CONN_HEALTH_CHECKS": True,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(os.environ.get("DJANGO_DB_PATH", "/srv/plan2wed/data/db.sqlite3")),
            "OPTIONS": {"timeout": 20},
        }
    }
STATIC_ROOT = Path("/srv/plan2wed/staticfiles")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# Nginx must overwrite this header; Gunicorn must only be reachable locally.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
# Enable a short policy first; do not include subdomains owned by other services.
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
