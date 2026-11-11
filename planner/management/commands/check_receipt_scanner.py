"""Verify the OCR executable and language data under the service account."""
import subprocess

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Check that receipt OCR is available with English language data.'

    def handle(self, *args, **options):
        try:
            result = subprocess.run(
                ['tesseract', '--list-langs'], capture_output=True,
                text=True, timeout=10, check=True,
            )
        except FileNotFoundError as error:
            raise CommandError('Install tesseract-ocr and tesseract-ocr-eng and ensure tesseract is on the service PATH.') from error
        except (OSError, subprocess.SubprocessError) as error:
            raise CommandError('Tesseract could not start. Check the installation and service permissions.') from error
        if not {'eng', 'osd'}.issubset(result.stdout.splitlines()):
            raise CommandError('Tesseract needs English and orientation data. Install tesseract-ocr-eng and tesseract-ocr-osd.')
        self.stdout.write(self.style.SUCCESS('Receipt scanner ready: Tesseract and English language data are available.'))
