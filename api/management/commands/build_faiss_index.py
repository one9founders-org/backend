"""
build_faiss_index management command — fixed version.

Changes vs original:
  - Passes upload_to_s3=True by default so the index is persisted across deploys.
  - Adds --no-upload flag for local dev use.
  - Reports dimension so you can verify it matches the model (should be 384 for MiniLM).
"""

import time

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Build FAISS index from all active tools and upload to S3 for persistence."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-upload",
            action="store_true",
            help="Skip S3 upload (useful for local dev)",
        )

    def handle(self, *args, **options):
        from api.faiss_search import FAISSSearchService

        upload = not options["no_upload"]

        if upload:
            self.stdout.write("Building FAISS index and uploading to S3 …")
        else:
            self.stdout.write("Building FAISS index locally (no S3 upload) …")

        start = time.time()
        service = FAISSSearchService.get_instance()
        count = service.build_index(upload_to_s3=upload)
        elapsed = time.time() - start

        if count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"FAISS index built: {count} tools, dimension={service.index.d}, "
                    f"time={elapsed:.2f}s"
                )
            )
            if upload:
                self.stdout.write(
                    self.style.SUCCESS(
                        "Index uploaded to S3 — will load on next cold start."
                    )
                )
        else:
            self.stdout.write(self.style.WARNING("No tools found — index not built."))
