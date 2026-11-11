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
Set `DJANGO_DATABASE=postgresql` to use the local `plan2wed` PostgreSQL database
and role through Unix-socket peer authentication as the `plan2wed` OS user.
Without this flag, SQLite at `/srv/plan2wed/data/db.sqlite3` is used for the
initial export. Back up PostgreSQL separately using `pg_dump`; GitHub stores
code, not live data.
Static assets are collected to `/srv/plan2wed/staticfiles` for Nginx to serve.
The application requires HTTPS and a trusted Nginx proxy that overwrites
`X-Forwarded-Proto`. Bind Gunicorn to a local Unix socket, not a public port.

## Receipt scanning

Shopping lists accept uploaded receipt photos (JPEG, PNG or TIFF, up to 8 MB). Install Tesseract with English language data on the application
server: `brew install tesseract` on macOS or
`sudo apt-get install tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd` on Debian/Ubuntu.
The service must have `tesseract` on its PATH. See the
[Tesseract documentation](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html).
No external OCR account or API key is used. Images are deleted after processing.
Allow uploads of at least 8 MB in the reverse proxy (`client_max_body_size 10m;`
for Nginx) and allow the OCR request up to 25 seconds plus request overhead.

Suggestions assume each item line ends with its total, optionally with a leading
quantity such as `2 x Candles 12.00`. Quantities otherwise default to one.
Users must review unit prices, tax, discounts and matches before confirming.
Confirming replaces matched unpurchased items or creates new purchased items;
the existing spending calculation then updates automatically. PDF and HEIC
receipts should be converted to JPEG/PNG first. No database migration is needed.

## Deploying this release

Follow the [receipt scanning deployment runbook](docs/deployment.md) for server
prerequisites, production checks, activation, smoke testing and rollback.
Check OCR availability under the application service account with
`python manage.py check_receipt_scanner --settings=config.production`.

Receipt OCR applies phone EXIF orientation, white-background greyscale contrast
cleanup and automatic page orientation detection. Install requirements.txt before
restarting the application after an update. Images are limited to 24 megapixels.
