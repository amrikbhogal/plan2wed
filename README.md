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
restarting the application after an update. Images are limited to 50 megapixels and resized before OCR.

## Account approval emails and password resets

Each completed signup creates an inactive account and emails
`SIGNUP_NOTIFICATION_EMAILS` (default: `info@plan2wed.co.uk`) after the database
transaction commits. The message links to the member's Django admin screen.
An administrator must sign in and set membership status to Active. Email links
do not approve accounts by themselves. Delivery failures are logged; the pending
account remains available under Members/admin for manual approval.

The sign-in page includes **Forgot your password?** Approved, active accounts
receive a single-use reset link valid for one hour. Unknown and inactive addresses
receive the same confirmation page without an email. Resetting a password does
not approve an account. No database migrations are required.

Local development prints emails to the console by default. Production uses SMTP.
Configure the variables in `.env.example` inside `/etc/plan2wed.env`, using your
provider's actual SMTP host, username and password. Keep the existing Django
secret and database settings. Do not commit SMTP credentials. For STARTTLS use
port 587 with `EMAIL_USE_TLS=true` and `EMAIL_USE_SSL=false`; for implicit TLS use
your provider's port (commonly 465), TLS false and SSL true. Never enable both.
The provider must authorise `DEFAULT_FROM_EMAIL` and the domain's required
SPF/DKIM DNS records. Set `PLAN2WED_SITE_URL=https://plan2wed.co.uk` so approval
and reset messages use the public site address.

After configuration, restart the service and test a signup notification to the
administrator, approve the test account, then request a reset from the sign-in
page. Check delivery and spam folders. Email configuration must be completed
before releasing these features; local automated tests use an in-memory backend
and do not verify delivery to real inboxes.

## Predefined shopping lists and CSV import

Each event's shopping items can be assigned to Decorations, Flowers, Food & catering,
Drinks, Clothing & accessories, Gifts & favours, Ceremony supplies, Stationery or
Other. The list filter changes visible rows; event spending totals cover all lists.
Existing items migrate to Other and retain their prices. New items may leave cost
blank; these display Not priced and contribute zero to totals until priced.
Receipt review includes a list dropdown and preserves matched items' lists.

Import CSV from within the destination event. A downloadable template is provided.
Headers: `Item,Quantity,List,Unit cost,Supplier,Notes`. Only Item is required.
Quantity defaults to 1 and missing List uses the selected default. Optional Event
values must match the open event; import other events from their own pages.
Preview makes no changes. Confirm adds items as To buy, skipping case-insensitive
duplicate names within the same event/list (including duplicates in the CSV).
Invalid rows reject the whole preview. Limits: UTF-8 CSV, 1 MB, 200 rows.

This feature **requires migration 0016** before restarting the production service.
Back up the database, pull the release, run `python manage.py migrate` and
`python manage.py collectstatic --noinput` in the service environment with
`--settings=config.production`, then restart. Prices previously stored as zero
remain zero; they are not silently changed to unknown prices.
