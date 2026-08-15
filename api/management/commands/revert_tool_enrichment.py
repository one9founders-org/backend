import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from api.tool_enrichment import apply_diff_entries


class Command(BaseCommand):
    help = (
        "Restore Tool content fields from an enrichment diff log. "
        "Writes old values inside a single transaction."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            required=True,
            help="Path to a timestamped enrichment-logs JSON diff.",
        )

    def handle(self, *args, **options):
        path = Path(options["file"]).expanduser()
        if not path.is_file():
            raise CommandError(f"Diff log not found: {path}")

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON diff log: {exc}") from exc

        entries = payload.get("tools")
        if not isinstance(entries, list):
            raise CommandError("Diff log is missing a 'tools' list.")

        updated, missing = apply_diff_entries(entries, use_old=True)

        for tool_id in missing:
            self.stderr.write(
                self.style.WARNING(f"Tool id={tool_id} not found; skipped")
            )

        self.stdout.write("")
        self.stdout.write("--- Summary ---")
        self.stdout.write("Mode: REVERT")
        self.stdout.write(f"Tools reverted: {updated}")
        self.stdout.write(f"Skipped (tool not found): {len(missing)}")
        self.stdout.write(f"Diff log: {path}")
