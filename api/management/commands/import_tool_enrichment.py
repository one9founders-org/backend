from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from api.tool_enrichment import (
    apply_diff_entries,
    build_tool_diff,
    is_approved,
    load_category_index,
    load_tools,
    parse_tool_id,
    read_csv_rows,
    write_enrichment_log,
)


def _preview(value, limit=220) -> str:
    text = value if isinstance(value, str) else repr(value)
    text = text.replace("\n", " ")
    if len(text) > limit:
        return text[:limit] + "..."
    return text


class Command(BaseCommand):
    help = (
        "Import approved tool content enrichment from a CSV. "
        "Dry-run by default; pass --apply to write. "
        "Updates description, pricing_type/pricing_models, and categories only. "
        "Does not touch assessment or security fields. "
        "pros/cons have no Tool fields and are skipped."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            required=True,
            help="Path to the enrichment CSV.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist changes inside a single transaction. Default is dry-run.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print diffs without writing (default when --apply is omitted).",
        )

    def handle(self, *args, **options):
        path = Path(options["file"]).expanduser()
        if not path.is_file():
            raise CommandError(f"CSV file not found: {path}")

        apply_mode = bool(options["apply"]) and not options["dry_run"]
        rows = read_csv_rows(path)

        skipped_not_approved = 0
        skipped_not_found = 0
        approved_ids: list[int] = []
        approved_rows: list[tuple[int, dict]] = []

        for row in rows:
            if not is_approved(row):
                skipped_not_approved += 1
                continue
            tool_id = parse_tool_id(row)
            if tool_id is None:
                skipped_not_found += 1
                raw_id = row.get("tool_id") or row.get("id")
                self.stderr.write(
                    self.style.WARNING(
                        f"Skipping approved row with invalid tool_id={raw_id!r}"
                    )
                )
                continue
            approved_ids.append(tool_id)
            approved_rows.append((tool_id, row))

        tools = load_tools(approved_ids)
        category_index = load_category_index()
        entries: list[dict] = []
        unmapped_fields: set[str] = set()

        for tool_id, row in approved_rows:
            tool = tools.get(tool_id)
            if tool is None:
                skipped_not_found += 1
                self.stderr.write(
                    self.style.WARNING(f"Tool id={tool_id} not found; skipped")
                )
                continue

            changes, unmapped, warnings = build_tool_diff(
                tool, row, category_index=category_index
            )
            unmapped_fields.update(unmapped)
            for warning in warnings:
                self.stderr.write(
                    self.style.WARNING(f"Tool id={tool_id} ({tool.name}): {warning}")
                )
            if not changes:
                continue
            entries.append(
                {
                    "tool_id": tool.id,
                    "tool_name": tool.name,
                    "changes": changes,
                }
            )

        if entries:
            self.stdout.write("")
            for entry in entries:
                self.stdout.write("=" * 72)
                self.stdout.write(f"Tool #{entry['tool_id']}  {entry['tool_name']}")
                self.stdout.write("-" * 72)
                for change in entry["changes"]:
                    self.stdout.write(f"  {change['field']}")
                    self.stdout.write(f"    old: {_preview(change['old_value'])}")
                    self.stdout.write(f"    new: {_preview(change['new_value'])}")
            self.stdout.write("=" * 72)
        else:
            self.stdout.write("No field changes to apply.")

        if unmapped_fields:
            self.stderr.write(
                self.style.WARNING(
                    "Skipped unmapped CSV columns (no matching Tool field): "
                    + ", ".join(sorted(unmapped_fields))
                    + ". Add JSONField(s) on Tool if these should be stored."
                )
            )

        log_path = None
        if apply_mode:
            payload = {
                "created_at": timezone.now().isoformat(),
                "source_file": str(path.resolve()),
                "mode": "apply",
                "tools": entries,
            }
            log_path = write_enrichment_log(payload, source_csv=path)
            apply_diff_entries(entries, use_old=False)

        self.stdout.write("")
        self.stdout.write("--- Summary ---")
        self.stdout.write(f"Mode: {'APPLY' if apply_mode else 'DRY RUN'}")
        self.stdout.write(f"Rows processed: {len(rows)}")
        self.stdout.write(f"Skipped (not approved): {skipped_not_approved}")
        self.stdout.write(f"Skipped (tool not found): {skipped_not_found}")
        self.stdout.write(f"Tools updated: {len(entries)}")
        if apply_mode and log_path is not None:
            self.stdout.write(f"Diff log: {log_path}")
            self.stdout.write(
                "Revert with: python manage.py revert_tool_enrichment "
                f"--file {log_path}"
            )
