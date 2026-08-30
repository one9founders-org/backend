"""Discover Indian + newly launched AI tools via Firecrawl and publish them."""

from django.core.management.base import BaseCommand, CommandError

from api.discovery.pipeline import run_india_and_new_discovery


class Command(BaseCommand):
    help = (
        "Search Indian and new AI tools with Firecrawl, scrape product pages "
        "for logo/pricing/categories, classify track (ai_tool vs open_source), "
        "and publish into the directory. Requires FIRECRAWL_API_KEY."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=40,
            help="Max new tools to publish this run (default 40).",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1:
            raise CommandError("--limit must be >= 1")
        self.stdout.write("--- Firecrawl India + new tools discovery ---")
        result = run_india_and_new_discovery(max_new=limit)
        for key, value in sorted(result.items()):
            self.stdout.write(f"  {key}: {value}")
