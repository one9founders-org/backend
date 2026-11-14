"""Re-run AI enrichment for tool submissions that failed after gpt-3.5-turbo died."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from api.models import ToolSubmission
from api.submission_enrichment import enrich_submission


class Command(BaseCommand):
    help = (
        "Re-enrich ToolSubmission rows with enrichment_status=failed. "
        "Use after switching TOOL_ENRICH_MODEL off the deprecated gpt-3.5-turbo."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum submissions to retry (default 50).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List targets without calling OpenAI.",
        )
        parser.add_argument(
            "--id",
            type=int,
            action="append",
            dest="ids",
            help="Only retry these submission ids (repeatable).",
        )

    def handle(self, *args, **options):
        limit = max(1, int(options["limit"]))
        qs = ToolSubmission.objects.filter(enrichment_status="failed").order_by("id")
        ids = options.get("ids") or []
        if ids:
            qs = qs.filter(pk__in=ids)
        targets = list(qs[:limit])
        self.stdout.write(f"Targets: {len(targets)} (limit={limit})")
        if options["dry_run"]:
            for row in targets:
                self.stdout.write(
                    f"  dry-run id={row.pk} name={row.name!r} "
                    f"error={(row.enrichment_error or '')[:80]!r}"
                )
            return

        succeeded = 0
        failed = 0
        for row in targets:
            enrich_submission(row.pk)
            row.refresh_from_db()
            if row.enrichment_status == "succeeded":
                succeeded += 1
                self.stdout.write(self.style.SUCCESS(f"ok id={row.pk} {row.name}"))
            else:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"fail id={row.pk} {row.name}: "
                        f"{(row.enrichment_error or '')[:200]}"
                    )
                )
        self.stdout.write(
            f"Done. succeeded={succeeded} failed={failed} attempted={len(targets)}"
        )
