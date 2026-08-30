from django.core.management.base import BaseCommand, CommandError

from api.fintech_ingest import DEFAULT_MAX_PAGES, run
from api.firecrawl import is_configured
from api.models import FintechRating

STACKS = (
    "all",
    FintechRating.STACK_KYC,
    FintechRating.STACK_CREDIT,
    FintechRating.STACK_FRAUD,
)


class Command(BaseCommand):
    help = (
        "Crawl published fintech vendor pages with Firecrawl and score the "
        "six RBI/DPDP checks. Writes nothing without --apply. Does not call "
        "Firecrawl unless --fetch (or --rescore-only to reuse stored pages)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--stack",
            default="all",
            choices=STACKS,
            help="Which stack to ingest. Default all.",
        )
        parser.add_argument("--slug", default="", help="One catalog slug only.")
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max catalog rows this run. 0 means the matching set.",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=DEFAULT_MAX_PAGES,
            help="Max pages to scrape per vendor after map.",
        )
        parser.add_argument(
            "--fetch",
            action="store_true",
            help="Call Firecrawl (1 map + up to --max-pages scrapes per vendor).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist evidence pages and FintechRating rows.",
        )
        parser.add_argument(
            "--rescore-only",
            action="store_true",
            help="Score from stored pages. No Firecrawl.",
        )
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Re-score vendors that already have six ratings.",
        )
        parser.add_argument(
            "--overwrite-reviewed",
            action="store_true",
            help="Also process the six hand-reviewed preview vendors.",
        )

    def handle(self, *args, **options):
        if options["limit"] < 0:
            raise CommandError("--limit must be >= 0")
        if options["max_pages"] < 1:
            raise CommandError("--max-pages must be >= 1")
        if options["apply"] and not options["fetch"] and not options["rescore_only"]:
            raise CommandError(
                "Pass --fetch to crawl, or --rescore-only to score stored pages."
            )
        if options["fetch"] and options["rescore_only"]:
            raise CommandError("Use either --fetch or --rescore-only, not both.")
        if options["fetch"] and not is_configured():
            raise CommandError("FIRECRAWL_API_KEY is not set.")

        summary = run(
            stack=options["stack"],
            slug=options["slug"] or None,
            fetch=options["fetch"],
            apply=options["apply"],
            rescore_only=options["rescore_only"],
            refresh=options["refresh"],
            overwrite_reviewed=options["overwrite_reviewed"],
            limit=options["limit"],
            max_pages=options["max_pages"],
        )
        self.stdout.write("--- Fintech ingest ---")
        self.stdout.write(f"Stack: {summary['stack']}")
        self.stdout.write(f"Catalog rows: {summary['count']}")
        self.stdout.write(f"Wrote: {summary['wrote']}")
        self.stdout.write(f"Skipped: {summary['skipped']}")
        self.stdout.write(f"Errors: {summary['errors']}")
        if summary["estimated_credits"]:
            self.stdout.write(
                f"Estimated Firecrawl credits: {summary['estimated_credits']} "
                "(1 map + up to max-pages scrapes per new vendor)"
            )
        for row in summary["outcomes"]:
            if row.skipped:
                self.stdout.write(f"  skip {row.slug}: {row.skipped}")
            elif row.error:
                self.stdout.write(self.style.ERROR(f"  error {row.slug}: {row.error}"))
            elif row.wrote:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  wrote {row.slug}: {row.pages} pages {row.results}"
                    )
                )
            else:
                self.stdout.write(
                    f"  dry {row.slug}: {row.pages} pages {row.results or row.notes}"
                )
