"""Download the Tranco top-1M list into a local sqlite lookup.

Tranco is a free research ranking of the most-visited domains, published
daily. It is the popularity signal that replaces the paid Google search
stage. Refresh it monthly -- ranks move slowly.
"""

import csv
import io
import sqlite3
import zipfile

import requests
from django.core.management.base import BaseCommand, CommandError

from api.hygiene.linkcheck import USER_AGENT
from api.hygiene.signals import tranco_db_path

TRANCO_URL = "https://tranco-list.eu/top-1m.csv.zip"
DOWNLOAD_TIMEOUT = 300


class Command(BaseCommand):
    help = "Download the Tranco top-1M domain list into a local sqlite database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            default=TRANCO_URL,
            help="Override the Tranco download URL.",
        )

    def handle(self, *args, **options):
        path = tranco_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        self.stdout.write(f"Downloading {options['url']} ...")
        try:
            response = requests.get(
                options["url"],
                timeout=DOWNLOAD_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError(f"Tranco download failed: {exc}") from exc

        try:
            archive = zipfile.ZipFile(io.BytesIO(response.content))
            name = archive.namelist()[0]
            raw = archive.read(name).decode("utf-8")
        except (zipfile.BadZipFile, IndexError, UnicodeDecodeError) as exc:
            raise CommandError(f"Could not read the Tranco archive: {exc}") from exc

        # Build into a temporary file, then swap, so a failed refresh never
        # leaves the pipeline with a half-written lookup.
        temp_path = path.with_suffix(".building")
        temp_path.unlink(missing_ok=True)

        connection = sqlite3.connect(temp_path)
        try:
            connection.execute(
                "CREATE TABLE ranks (domain TEXT PRIMARY KEY, rank INTEGER NOT NULL)"
            )
            rows = (
                (domain, int(rank))
                for rank, domain in csv.reader(io.StringIO(raw))
                if domain and rank.isdigit()
            )
            connection.executemany("INSERT OR REPLACE INTO ranks VALUES (?, ?)", rows)
            connection.commit()
            count = connection.execute("SELECT COUNT(*) FROM ranks").fetchone()[0]
        finally:
            connection.close()

        temp_path.replace(path)
        self.stdout.write(
            self.style.SUCCESS(f"Stored {count:,} ranked domains at {path}")
        )
