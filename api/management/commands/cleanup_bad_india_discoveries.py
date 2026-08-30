"""Deactivate Firecrawl India rows whose website is still a directory/news URL.

YC / Wellfound / GoodFirms are valuable *sources* of startups. We do not
reject those companies — we only deactivate rows where Tool.website still
points at the directory page (e.g. wellfound.com/...) instead of the
product homepage (e.g. gomotive.com). Re-run discovery after deploy to
re-ingest those startups with a real website.
"""

from django.core.management.base import BaseCommand

from api.discovery.india_sources import website_is_unusable
from api.models import Tool


class Command(BaseCommand):
    help = (
        "Deactivate auto-discovered India tools whose website still points "
        "at a directory/news page (not the product). Dry-run unless --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist is_active=False. Omit for a dry run.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max rows to scan (0 = all matching).",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        mode = "APPLY" if apply else "DRY RUN"
        self.stdout.write(f"--- Cleanup bad India discoveries ({mode}) ---")
        self.stdout.write(
            "Note: YC/Wellfound/GoodFirms startups are kept when their "
            "website is the real product URL. Only directory/news websites "
            "are deactivated so discovery can re-publish them correctly."
        )

        queryset = (
            Tool.objects.filter(is_active=True)
            .filter(tags__contains=["firecrawl_india"])
            .order_by("id")
            .only("id", "name", "website", "tags", "is_active")
        )
        if options["limit"]:
            queryset = queryset[: options["limit"]]

        scanned = 0
        bad: list[Tool] = []
        for tool in queryset.iterator(chunk_size=200):
            scanned += 1
            if website_is_unusable(tool.website or ""):
                bad.append(tool)

        self.stdout.write(f"Scanned: {scanned}")
        self.stdout.write(f"Bad website (directory/news): {len(bad)}")
        for tool in bad[:40]:
            self.stdout.write(f"  [{tool.id}] {tool.name!r} -> {tool.website}")
        if len(bad) > 40:
            self.stdout.write(f"  ... and {len(bad) - 40} more")

        if apply and bad:
            ids = [t.id for t in bad]
            updated = Tool.objects.filter(id__in=ids).update(is_active=False)
            self.stdout.write(self.style.SUCCESS(f"Deactivated: {updated}"))
        elif not apply:
            self.stdout.write(
                self.style.WARNING("Dry run: nothing written. Re-run with --apply.")
            )
