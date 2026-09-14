from django.core.management.base import BaseCommand

from api.discovery import MAX_NEW_TOOLS_PER_RUN
from api.discovery.pipeline import run_new_tool_discovery


class Command(BaseCommand):
    help = (
        "Discover new tools from free sources (GitHub / Product Hunt / HN), "
        "run the quality gate, and publish candidates that pass. "
        "Does not call Firecrawl unless FIRECRAWL_DISCOVERY_ENABLED=true."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-new",
            type=int,
            default=MAX_NEW_TOOLS_PER_RUN,
            help=(
                f"Cap on new Tool rows this run " f"(default {MAX_NEW_TOOLS_PER_RUN})."
            ),
        )
        parser.add_argument(
            "--full-github-sweep",
            action="store_true",
            help=(
                "Partition GitHub Search by topic×star-bin and auto-split "
                "bins over 1,000 hits so every 100+ star AI repo is considered."
            ),
        )
        parser.add_argument(
            "--full-hn-sweep",
            action="store_true",
            help=(
                "Paginate Hacker News Algolia AI/Show HN queries across history "
                "and merge official Firebase show/top/best/new feeds."
            ),
        )

    def handle(self, *args, **options):
        max_new = options["max_new"]
        if max_new is not None and max_new < 1:
            self.stderr.write("--max-new must be >= 1")
            return
        summary = run_new_tool_discovery(
            max_new=max_new,
            full_github_sweep=bool(options.get("full_github_sweep")),
            full_hn_sweep=bool(options.get("full_hn_sweep")),
        )
        self.stdout.write("--- Discovery summary ---")
        self.stdout.write(f"Candidates found: {summary['candidates_found']}")
        self.stdout.write(f"Published: {summary['published']}")
        self.stdout.write(f"Rejected: {summary['rejected']}")
        self.stdout.write(f"Errored: {summary['errored']}")
        self.stdout.write(f"Deferred over cap: {summary['deferred_over_cap']}")
        self.stdout.write(f"Staged for review: {summary.get('staged', 0)}")
        self.stdout.write(
            f"Existing candidates updated: {summary.get('candidate_updates', 0)}"
        )
        for source, counts in sorted(summary.get("by_source", {}).items()):
            formatted = ", ".join(
                f"{outcome}={count}" for outcome, count in sorted(counts.items())
            )
            self.stdout.write(f"{source}: {formatted}")
