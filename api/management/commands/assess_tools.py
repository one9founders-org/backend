"""Score tools from published evidence. Dry-run unless --apply is given."""

from django.core.management.base import BaseCommand, CommandError

from api.hygiene import ASSESS_BUDGET_CEILING_USD, ASSESS_DEFAULT_BUDGET_USD
from api.hygiene.assess_run import TRACK_VALUES, run
from api.hygiene.track import TRACK_CHOICES


class Command(BaseCommand):
    help = (
        "Score tools against the published methodology criteria using "
        "pages fetched from each tool's own site. Writes nothing without "
        "--apply. Aborts if running OpenAI spend crosses --budget-usd."
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
            help="Skip this many matching rows (for batched runs).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist scores. Omit for a dry run (still calls the model).",
        )
        parser.add_argument(
            "--track",
            default="",
            choices=[""] + [key for key, _label in TRACK_CHOICES],
            help="Only process rows already classified as this track.",
        )
        parser.add_argument(
            "--budget-usd",
            type=float,
            default=ASSESS_DEFAULT_BUDGET_USD,
            help=(
                f"Abort the run when OpenAI spend reaches this many USD "
                f"(ceiling {ASSESS_BUDGET_CEILING_USD:.0f})."
            ),
        )
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Re-score rows that already have criteria_completed > 0.",
        )
        parser.add_argument(
            "--stale-days",
            type=int,
            default=0,
            help="Only rows never assessed, or last assessed more than N days ago.",
        )

    def handle(self, *args, **options):
        if options["limit"] < 0:
            raise CommandError("--limit must be >= 0")
        if options["offset"] < 0:
            raise CommandError("--offset must be >= 0")
        if options["stale_days"] < 0:
            raise CommandError("--stale-days must be >= 0")
        if options["budget_usd"] <= 0:
            raise CommandError("--budget-usd must be > 0")
        if options["budget_usd"] > ASSESS_BUDGET_CEILING_USD:
            self.stdout.write(
                self.style.WARNING(
                    f"Clamping --budget-usd from {options['budget_usd']} "
                    f"to {ASSESS_BUDGET_CEILING_USD}."
                )
            )

        track = options["track"]
        if track and track not in TRACK_VALUES:
            raise CommandError(f"Unknown --track {track}")

        mode = "APPLY" if options["apply"] else "DRY RUN"
        self.stdout.write(f"--- Assess tools ({mode}) ---")

        summary = run(
            limit=options["limit"],
            offset=options["offset"],
            apply=options["apply"],
            track=track,
            budget_usd=options["budget_usd"],
            only_unassessed=not options["refresh"],
            stale_days=options["stale_days"],
        )

        self.stdout.write(f"Selected:     {summary['selected']}")
        self.stdout.write(f"Processed:    {summary['processed']}")
        self.stdout.write(f"With scores:  {summary['with_scores']}")
        self.stdout.write(f"Provisional:  {summary['provisional']}")
        self.stdout.write(f"Updated:      {summary['updated']}")
        self.stdout.write(f"Skipped:      {summary['skipped']}")
        self.stdout.write(
            f"Spend:        ${summary['spent_usd']:.4f} "
            f"({summary['prompt_tokens']}+{summary['completion_tokens']} tokens)"
        )
        self.stdout.write(f"Log:          {summary['log_path']}")
        if summary["aborted"]:
            self.stdout.write(self.style.ERROR(f"Aborted: {summary['abort_reason']}"))
        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING("Dry run: nothing written. Re-run with --apply.")
            )
