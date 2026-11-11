# Receipt scanning release

This release adds uploaded receipt images and review before purchase confirmation.
There are no model changes or new Python dependencies. Keep the current production
WSGI server and database configuration. Do not copy the local SQLite database to
production.

## Prepare the existing VPS

Use the existing checkout, virtual environment and systemd service paths; confirm
these from `systemctl cat plan2wed` before running deployment commands. The
commands below assume the unit is named `plan2wed`. Run application commands
from its checkout as the `plan2wed` service user, using its virtual environment
and the existing `/etc/plan2wed.env` environment. Do not generate a new production
secret or switch database engines for this release.

1. Record the current deployed Git commit and back up the live database using the
   established backup procedure. For PostgreSQL, use `pg_dump` and verify the
   backup completed. Keep backups outside the checkout.
2. Install the OCR system dependency:

   ```sh
   sudo apt-get update
   sudo apt-get install tesseract-ocr tesseract-ocr-eng
   ```

3. In the existing HTTPS Nginx server/location serving Django, configure:

   ```nginx
   client_max_body_size 10m;
   proxy_read_timeout 60s;
   ```

   Preserve the Unix socket, TLS and proxy headers. The application accepts
   individual receipt files up to 8 MB. Set Gunicorn's worker timeout to 60 seconds
   in its existing configuration (`--timeout 60`); OCR itself stops after 25
   seconds. Review any systemd restrictions on executing `/usr/bin/tesseract`
   and writing temporary files. Keep those files private.

4. Validate Nginx with `sudo nginx -t` before reloading it.

## Release checks and activation

Deploy the reviewed source commit using the existing Git release process. In the
release checkout with dependencies installed and production environment loaded:

```sh
python manage.py check --deploy --settings=config.production --fail-level ERROR
python manage.py check_receipt_scanner --settings=config.production
python manage.py migrate --check --settings=config.production
python manage.py collectstatic --noinput --settings=config.production
```

The current production policy intentionally leaves HSTS subdomains and preload
disabled. Django reports `security.W005` and `security.W021`; review any additional
warnings before activation. Do not enable these flags without checking all
subdomains and the preload commitment.

Run the test suite in development/CI before release (`python manage.py test`),
not against the production database account. If the migration check reports
pending migrations, inspect them and apply them through the normal backed-up
migration process before activation; this feature introduces none.

After all checks pass, restart the existing application service and reload Nginx:

```sh
sudo systemctl restart plan2wed
sudo systemctl is-active plan2wed
sudo systemctl reload nginx
```

Check the service logs for errors. Verify HTTPS login and shopping list access.
With a test account/event, upload a clear receipt, review the suggested items,
confirm one new purchase and one match, and verify spent/pending totals. Check
that cancelling does not change spending and that an invalid image produces a
helpful error. Remove the test data afterward. Actual OCR accuracy must be checked
with real receipt images; mocked automated tests do not establish that.

## Rollback

Restore the recorded source commit using the existing release process, collect
static files and restart the same service. No reverse migration is required for
this feature. Confirmed purchases remain normal shopping items and survive a
code rollback. Correct unwanted imports through shopping list management;
restoring an entire database backup would discard unrelated live changes.

References: [Tesseract installation](https://tesseract-ocr.github.io/tessdoc/Installation.html),
[Gunicorn timeout](https://gunicorn.org/reference/settings/#timeout).
