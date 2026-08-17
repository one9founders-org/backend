from django.core.management.base import BaseCommand, CommandError

from agents.discovery import ALL_SOURCES
from agents.discovery.pipeline import run_agent_scrape


class Command(BaseCommand):
    help = (
        "Refresh the AI Agents Directory from public catalogs and ingest new "
        "unique agents (aiagentsdirectory, GitHub awesome lists, GitHub topics, "
        "Hugging Face Spaces, Enterprise DNA, Product Hunt, Hacker News)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--sources",
            type=str,
            default=",".join(ALL_SOURCES),
            help="Comma-separated sources. Default: all.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Optional cap per source (useful for smoke tests).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and match, but do not write to the database.",
        )

    def handle(self, *args, **options):
        sources = tuple(
            source.strip()
            for source in (options["sources"] or "").split(",")
            if source.strip()
        )
        if not sources:
            raise CommandError("No sources selected.")

        self.stdout.write(
            f"Scraping agents from: {', '.join(sources)}"
            + (" (dry-run)" if options["dry_run"] else "")
        )
        try:
            summary = run_agent_scrape(
                sources=sources,
                limit=options["limit"],
                dry_run=options["dry_run"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write("--- Agent scrape summary ---")
        for source, count in (summary.get("sources") or {}).items():
            self.stdout.write(f"{source}: {count} candidates")
        self.stdout.write(f"Candidates fetched: {summary['candidates']}")
        self.stdout.write(f"Created: {summary['created']}")
        self.stdout.write(f"Updated: {summary['updated']}")
        self.stdout.write(f"Skipped: {summary['skipped']}")
        self.stdout.write(f"Total agents: {summary['total_agents']}")
        self.stdout.write(f"Categories: {summary['categories']}")
        self.stdout.write(self.style.SUCCESS("Done."))
