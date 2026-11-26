from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.core.files.storage import default_storage


class Command(BaseCommand):
    help = "Copy files from MEDIA_ROOT to the configured default media storage."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List how many files would be copied without uploading them.",
        )

    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT)
        if not media_root.exists():
            self.stdout.write(self.style.WARNING(f"No local media directory exists at {media_root}."))
            return

        files = sorted(path for path in media_root.rglob("*") if path.is_file())
        copied = 0
        skipped = 0
        dry_run = options["dry_run"]

        for source_path in files:
            storage_name = source_path.relative_to(media_root).as_posix()
            try:
                if default_storage.exists(storage_name):
                    skipped += 1
                    continue
                if dry_run:
                    copied += 1
                    continue
                with source_path.open("rb") as source_file:
                    default_storage.save(storage_name, File(source_file, name=source_path.name))
                copied += 1
            except Exception as exc:
                raise CommandError(f"Could not copy media file {storage_name}: {exc}") from exc

        if dry_run:
            self.stdout.write(
                f"Dry run complete: {copied} file(s) would be copied; {skipped} already exist in the configured storage."
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Media copy complete: {copied} copied; {skipped} already existed and were left unchanged."
                )
            )
