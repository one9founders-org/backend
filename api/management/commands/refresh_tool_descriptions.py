from django.core.management.base import BaseCommand

from api.discovery.pipeline import run_refresh_descriptions


class Command(BaseCommand):
    help = (
        "Re-fetch facts for existing tools and overwrite descriptions "
        "only when the quality gate passes and the text changed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="How many existing tools to refresh (default 50).",
        )

    def handle(self, *args, **options):
        summary = run_refresh_descriptions(limit=options["limit"])
        self.stdout.write("--- Refresh summary ---")
        self.stdout.write(f"Selected: {summary['selected']}")
        self.stdout.write(f"Updated: {summary['updated']}")
        self.stdout.write(f"Refresh rejected: {summary['refresh_rejected']}")
        self.stdout.write(f"No-op skipped: {summary['noop_skipped']}")
        self.stdout.write(f"Errored: {summary['errored']}")
