"""Deactivate junk Firecrawl India rows that point at directories/listicles."""

from django.core.management.base import BaseCommand

from api.discovery.india_sources import looks_like_listicle
from api.models import Tool


class Command(BaseCommand):
    help = (
        "Deactivate auto-discovered India tools whose website/title is a "
        "directory, news, or listicle page. Dry-run unless --apply."
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
            if looks_like_listicle(tool.name or "", tool.website or ""):
                bad.append(tool)

        self.stdout.write(f"Scanned: {scanned}")
        self.stdout.write(f"Bad:     {len(bad)}")
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
