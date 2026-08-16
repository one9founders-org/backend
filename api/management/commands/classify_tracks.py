"""Classify every tool into a content-type track. No model calls."""

from django.core.management.base import BaseCommand, CommandError

from api.hygiene.track import classify_track
from api.models import Tool


def track_for(tool: Tool) -> str:
    text = " ".join(
        filter(
            None,
            [
                tool.short_description or "",
                (tool.description or "")[:1500],
                " ".join(tool.tags or []),
            ],
        )
    )
    return classify_track(tool.name or "", tool.website or "", text)


class Command(BaseCommand):
    help = (
        "Set Tool.track from the name, website, and description. Free: no "
        "OpenAI calls. Writes nothing without --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max rows to process. 0 means all.",
        )
        parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="Skip this many rows.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist track values. Omit for a dry run.",
        )

    def handle(self, *args, **options):
        if options["limit"] < 0:
            raise CommandError("--limit must be >= 0")
        if options["offset"] < 0:
            raise CommandError("--offset must be >= 0")

        queryset = (
            Tool.objects.all()
            .order_by("id")
            .only(
                "id",
                "name",
                "website",
                "short_description",
                "description",
                "tags",
                "track",
            )
        )
        start = options["offset"]
        if options["limit"]:
            end = start + options["limit"]
            queryset = queryset[start:end]
        elif start:
            queryset = queryset[start:]

        mode = "APPLY" if options["apply"] else "DRY RUN"
        self.stdout.write(f"--- Classify tracks ({mode}) ---")

        counts: dict[str, int] = {}
        changed = 0
        batch: list[Tool] = []
        scanned = 0
        for tool in queryset.iterator(chunk_size=500):
            scanned += 1
            new_track = track_for(tool)
            counts[new_track] = counts.get(new_track, 0) + 1
            if tool.track != new_track:
                changed += 1
                tool.track = new_track
                batch.append(tool)
            if options["apply"] and len(batch) >= 500:
                Tool.objects.bulk_update(batch, ["track"])
                batch = []
        if options["apply"] and batch:
            Tool.objects.bulk_update(batch, ["track"])

        self.stdout.write(f"Scanned:  {scanned}")
        self.stdout.write(f"Changed:  {changed}")
        for key, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            self.stdout.write(f"  {key}: {count}")
        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING("Dry run: nothing written. Re-run with --apply.")
            )
