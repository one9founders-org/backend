"""Run the directory hygiene pass. Dry-run unless --apply is given."""

from django.core.management.base import BaseCommand, CommandError

from api.hygiene.classify import ENTRY_TYPE_CHOICES
from api.hygiene.pipeline import Stages, run
from api.hygiene.websearch import is_configured as search_configured


class Command(BaseCommand):
    help = (
        "Re-verify and revise tool rows: classify, check links, resolve "
        "logos, confirm against Google, re-tag, and re-rank. Writes nothing "
        "without --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Max rows to process. 0 means the whole matching set.",
        )
        parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="Skip this many matching rows (for batched dry-runs).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist changes. Omit for a dry run.",
        )
        parser.add_argument(
            "--entry-type",
            default="",
            choices=[""] + [key for key, _label in ENTRY_TYPE_CHOICES],
            help="Only process rows already classified as this type.",
        )
        parser.add_argument(
            "--only-missing-logo",
            action="store_true",
            help="Restrict to rows with no logo.",
        )
        parser.add_argument(
            "--only-unchecked",
            action="store_true",
            help="Restrict to rows the hygiene pass has never touched.",
        )
        parser.add_argument(
            "--stale-days",
            type=int,
            default=0,
            help="Only rows never checked, or last checked more than N days ago.",
        )
        parser.add_argument(
            "--search-budget",
            type=int,
            default=8000,
            help="Max Google queries this run (daily cap is 10,000).",
        )
        parser.add_argument("--no-link", action="store_true", help="Skip link checks.")
        parser.add_argument("--no-logo", action="store_true", help="Skip logo lookup.")
        parser.add_argument(
            "--no-search",
            action="store_true",
            help="Skip Google verification (saves paid quota).",
        )
        parser.add_argument(
            "--no-llm",
            action="store_true",
            help="Skip LLM enrichment; still migrates legacy tags.",
        )

    def handle(self, *args, **options):
        if options["limit"] < 0:
            raise CommandError("--limit must be >= 0")
        if options["offset"] < 0:
            raise CommandError("--offset must be >= 0")
        if options["stale_days"] < 0:
            raise CommandError("--stale-days must be >= 0")
        if options["search_budget"] < 0:
            raise CommandError("--search-budget must be >= 0")

        stages = Stages(
            link=not options["no_link"],
            logo=not options["no_logo"],
            search=not options["no_search"],
            llm=not options["no_llm"],
        )

        if stages.search and not search_configured():
            self.stdout.write(
                self.style.WARNING(
                    "GOOGLE_SEARCH_API_KEY/CX are not set; search stage will no-op."
                )
            )

        mode = "APPLY" if options["apply"] else "DRY RUN"
        self.stdout.write(f"--- Hygiene pass ({mode}) ---")

        summary = run(
            limit=options["limit"],
            offset=options["offset"],
            apply=options["apply"],
            stages=stages,
            entry_type=options["entry_type"],
            only_missing_logo=options["only_missing_logo"],
            only_unchecked=options["only_unchecked"],
            stale_days=options["stale_days"],
            search_budget=options["search_budget"],
        )

        self.stdout.write(f"Selected:     {summary['selected']}")
        self.stdout.write(f"With changes: {summary['with_changes']}")
        self.stdout.write(f"Updated:      {summary['updated']}")
        self.stdout.write(f"Skipped:      {summary['skipped']}")
        self.stdout.write(f"Log:          {summary['log_path']}")
        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING("Dry run: nothing written. Re-run with --apply.")
            )
