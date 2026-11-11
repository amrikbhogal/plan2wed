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
