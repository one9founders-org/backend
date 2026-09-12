from django.core.management.base import BaseCommand

from api.discovery.sources import (
    candidate_signal,
    discover_candidates,
    fetch_hacker_news_candidates,
    partition_against_catalog,
)


class Command(BaseCommand):
    help = (
        "Fetch GitHub / Product Hunt / HN candidates, dedupe against Tools, "
        "and print the list. Does not create records. "
        "Use --source hackernews for an HN-only scrape + on-site cross-check."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            choices=("all", "hackernews"),
            default="all",
            help="Which sources to fetch (default all).",
        )
        parser.add_argument(
            "--full-hn-sweep",
            action="store_true",
            help="When scraping HN, paginate Algolia AI/Show HN history.",
        )
        parser.add_argument(
            "--full-github-sweep",
            action="store_true",
            help="When scraping all sources, enable the full GitHub sweep.",
        )

    def handle(self, *args, **options):
        source = options["source"]
        if source == "hackernews":
            scraped = fetch_hacker_news_candidates(
                full_sweep=bool(options.get("full_hn_sweep")),
            )
            already, fresh = partition_against_catalog(scraped)
            self.stdout.write(
                f"HN scraped={len(scraped)} already_on_site={len(already)} "
                f"new={len(fresh)}\n"
            )
            self.stdout.write("Already on website:")
            for item in already:
                self.stdout.write(
                    f"- [on-site] {item['name']}  {item.get('url')}  "
                    f"points={candidate_signal(item)}"
                )
            self.stdout.write("\nNot yet on website:")
            for item in fresh:
                self.stdout.write(
                    f"- [new] {item['name']}  {item.get('url')}  "
                    f"points={candidate_signal(item)}"
                )
            return

        candidates = discover_candidates(
            full_github_sweep=bool(options.get("full_github_sweep")),
            full_hn_sweep=bool(options.get("full_hn_sweep")),
        )
        if not candidates:
            self.stdout.write("No new candidates.")
            return

        self.stdout.write(f"Found {len(candidates)} new candidates:\n")
        for item in candidates:
            signal = candidate_signal(item)
            self.stdout.write(
                f"- {item['name']}  {item['url']}  "
                f"[{item.get('sourceType')}] signal={signal}"
            )
