"""Publish the Windows One9 worker installer so the website can serve the EXE."""

from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Copy the Windows NSIS setup EXE into downloads/openworker/ and upload "
        "it to the public OpenWorker downloads bucket for one9founders.com/worker."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "exe",
            help="Path to the Tauri/NSIS setup .exe from packaging/build_windows.ps1",
        )
        parser.add_argument(
            "--no-upload",
            action="store_true",
            help="Only copy locally (skip S3). Useful for runserver testing.",
        )

    def handle(self, *args, **options):
        src = Path(options["exe"]).expanduser().resolve()
        if not src.is_file():
            raise CommandError(f"Installer not found: {src}")

        dest_dir = Path(settings.OPENWORKER_LOCAL_DOWNLOAD_DIR)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / settings.OPENWORKER_WINDOWS_FILENAME
        shutil.copy2(src, dest)
        self.stdout.write(self.style.SUCCESS(f"Copied {src.name} → {dest}"))

        if options["no_upload"]:
            self.stdout.write(
                "Skipped S3. Local download: /v1/openworker/download/windows"
            )
            return

        bucket = getattr(
            settings,
            "OPENWORKER_WINDOWS_S3_BUCKET",
            "one9founders-openworker-downloads",
        )
        key = settings.OPENWORKER_WINDOWS_S3_KEY
        if not settings.AWS_ACCESS_KEY_ID:
            raise CommandError("AWS_ACCESS_KEY_ID is not set")

        import boto3

        s3 = boto3.client(
            "s3",
            region_name=getattr(settings, "AWS_S3_REGION_NAME", None) or "ap-south-1",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        extra = {
            "ContentType": "application/octet-stream",
            "ContentDisposition": f'attachment; filename="{settings.OPENWORKER_WINDOWS_FILENAME}"',
            "CacheControl": "max-age=300",
        }
        try:
            s3.upload_file(
                str(dest), bucket, key, ExtraArgs={**extra, "ACL": "public-read"}
            )
        except Exception:
            s3.upload_file(str(dest), bucket, key, ExtraArgs=extra)
        public = (
            settings.OPENWORKER_WINDOWS_DOWNLOAD_URL
            or f"https://{bucket}.s3.ap-south-1.amazonaws.com/{key}"
        )
        self.stdout.write(self.style.SUCCESS(f"Uploaded s3://{bucket}/{key}"))
        self.stdout.write(f"Public file: {public}")
        self.stdout.write(
            "Website button: https://api.one9founders.com/v1/openworker/download/windows"
        )
