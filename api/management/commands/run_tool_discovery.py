from django.core.management.base import BaseCommand

from api.discovery import MAX_NEW_TOOLS_PER_RUN
from api.discovery.pipeline import run_new_tool_discovery


class Command(BaseCommand):
    help = (
        "Discover new tools, run the quality gate, and publish every "
        "candidate that passes. Pass --max-new to restore a cap."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-new",
            type=int,
            default=MAX_NEW_TOOLS_PER_RUN,
            help="Optional cap on new Tool rows this run. Default is unlimited.",
        )

    def handle(self, *args, **options):
        summary = run_new_tool_discovery(max_new=options["max_new"])
        self.stdout.write("--- Discovery summary ---")
        self.stdout.write(f"Candidates found: {summary['candidates_found']}")
        self.stdout.write(f"Published: {summary['published']}")
        self.stdout.write(f"Rejected: {summary['rejected']}")
        self.stdout.write(f"Errored: {summary['errored']}")
        self.stdout.write(f"Deferred over cap: {summary['deferred_over_cap']}")
