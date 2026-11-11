# Plan2Wed

A Django wedding planner for events, venues, guests, seating plans, shopping lists and spending statements.

## Local setup

Use Python 3.12 or later.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DJANGO_SECRET_KEY='your-long-random-secret'
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The environment variable keeps sessions consistent between restarts. If it is absent, a temporary development key is generated. `.env.example` documents the variable; `.env` files are not automatically loaded.

## Tests

```sh
python manage.py test
```

Local databases, uploaded media, credentials and Python cache files are excluded from Git. Configure production settings before deployment; the checked-in settings are for local development.

## VPS production settings

Use `DJANGO_SETTINGS_MODULE=config.production` and a fixed, randomly generated
`DJANGO_SECRET_KEY` of at least 50 characters. Store these in `/etc/plan2wed.env`,
readable only by root and the `plan2wed` service group. Never commit this file.
The production SQLite database lives at `/srv/plan2wed/data/db.sqlite3`; back it
up separately using SQLite's backup API. GitHub stores code, not live data.
Static assets are collected to `/srv/plan2wed/staticfiles` for Nginx to serve.
The application requires HTTPS and a trusted Nginx proxy that overwrites
`X-Forwarded-Proto`. Bind Gunicorn to a local Unix socket, not a public port.
