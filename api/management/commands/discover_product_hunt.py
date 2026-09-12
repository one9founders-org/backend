from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.discovery import MAX_NEW_TOOLS_PER_RUN
from api.discovery.pipeline import run_new_tool_discovery
from api.discovery.sources import (
    dedupe_candidates,
    fetch_product_hunt_candidates,
)


class Command(BaseCommand):
    help = (
        "Discover AI tools from Product Hunt's API (when authorized) or RSS "
        "fallback. Candidates are review-only unless --auto-publish is explicit."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-new",
            type=int,
            default=MAX_NEW_TOOLS_PER_RUN,
            help=f"Maximum candidates to process (default {MAX_NEW_TOOLS_PER_RUN}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and normalize candidates without writing to the database.",
        )
        parser.add_argument(
            "--auto-publish",
            action="store_true",
            help=(
                "Publish candidates whose official website resolves and passes "
                "quality gates. Unresolved candidates remain staged."
            ),
        )

    def handle(self, *args, **options):
        max_new = options["max_new"]
        if max_new < 1:
            raise CommandError("--max-new must be >= 1")

        candidates = dedupe_candidates(fetch_product_hunt_candidates())
        if options["dry_run"]:
            resolved = sum(1 for item in candidates if item.get("officialUrl"))
            self.stdout.write(f"Candidates: {len(candidates)}")
            self.stdout.write(f"Official websites resolved: {resolved}")
            self.stdout.write(f"Needs review: {len(candidates) - resolved}")
            return

        if options["auto_publish"]:
            settings.EXTERNAL_DISCOVERY_AUTO_PUBLISH_SOURCES = {
                *getattr(settings, "EXTERNAL_DISCOVERY_AUTO_PUBLISH_SOURCES", set()),
                "producthunt",
            }

        summary = run_new_tool_discovery(
            max_new=max_new,
            candidates=candidates,
        )
        self.stdout.write("--- Product Hunt discovery summary ---")
        for key in (
            "candidates_found",
            "published",
            "staged",
            "candidate_updates",
            "rejected",
            "errored",
            "deferred_over_cap",
        ):
            self.stdout.write(f"{key}: {summary.get(key, 0)}")
