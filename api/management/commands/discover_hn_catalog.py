"""Catalogue AI tools from Hacker News and cross-check the site directory.

Uses the official Firebase HN API (show/top/best/new) plus Algolia Show HN /
AI story search. Drops stories already present as Tool rows (URL or name).
"""

from django.core.management.base import BaseCommand

from api.discovery.pipeline import run_new_tool_discovery
from api.discovery.sources import (
    candidate_signal,
    fetch_hacker_news_candidates,
    partition_against_catalog,
)


class Command(BaseCommand):
    help = (
        "Scrape Hacker News (Firebase + Algolia) for AI tools, cross-check "
        "against tools already on the website, and optionally publish new ones."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-new",
            type=int,
            default=100,
            help="Cap on new Tool rows this run (default 100).",
        )
        parser.add_argument(
            "--full-sweep",
            action="store_true",
            default=True,
            help="Paginate Algolia AI/Show HN queries across history (default on).",
        )
        parser.add_argument(
            "--incremental",
            action="store_true",
            help="Recent window only (skip full Algolia pagination).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Fetch and cross-check only: print already-on-site vs new, "
                "do not write Tool rows."
            ),
        )
        parser.add_argument(
            "--limit-print",
            type=int,
            default=40,
            help="Max candidates to print per bucket in dry-run (default 40).",
        )

    def handle(self, *args, **options):
        max_new = options["max_new"]
        if max_new < 1:
            self.stderr.write("--max-new must be >= 1")
            return

        full_sweep = not options["incremental"]
        self.stdout.write(
            f"Scraping Hacker News "
            f"(full_sweep={full_sweep}, dry_run={options['dry_run']})…"
        )
        scraped = fetch_hacker_news_candidates(full_sweep=full_sweep)
        already, fresh = partition_against_catalog(scraped)

        self.stdout.write("--- HN cross-check ---")
        self.stdout.write(f"scraped: {len(scraped)}")
        self.stdout.write(f"already_on_site: {len(already)}")
        self.stdout.write(f"new_candidates: {len(fresh)}")

        limit = max(0, int(options["limit_print"]))
        if limit:
            self.stdout.write("\nAlready on website:")
            for item in already[:limit]:
                signal = candidate_signal(item)
                self.stdout.write(
                    f"  [on-site] {item['name']}  {item.get('url')}  "
                    f"points={signal}"
                )
            if len(already) > limit:
                self.stdout.write(f"  … {len(already) - limit} more")

            self.stdout.write("\nNot yet on website:")
            for item in fresh[:limit]:
                signal = candidate_signal(item)
                self.stdout.write(
                    f"  [new] {item['name']}  {item.get('url')}  " f"points={signal}"
                )
            if len(fresh) > limit:
                self.stdout.write(f"  … {len(fresh) - limit} more")

        if options["dry_run"]:
            self.stdout.write("\nDry run complete (no writes).")
            return

        summary = run_new_tool_discovery(
            max_new=max_new,
            candidates=fresh,
        )
        self.stdout.write("\n--- HN catalogue publish summary ---")
        for key in (
            "candidates_found",
            "published",
            "rejected",
            "errored",
            "deferred_over_cap",
            "staged",
            "candidate_updates",
        ):
            if key in summary:
                self.stdout.write(f"{key}: {summary[key]}")
        for source, counts in sorted(summary.get("by_source", {}).items()):
            self.stdout.write(f"  {source}: {counts}")
