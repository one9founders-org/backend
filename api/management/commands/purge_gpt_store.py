"""Remove ChatGPT-store scrapes from the directory.

Selection uses live classify() (chat.openai.com / chatgpt.com), not the
stored entry_type, so rows the hygiene pass has not reached yet are
included. Writes a JSON manifest first so the id list survives the
delete. Dry-run unless --apply.
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from api.hygiene.classify import GPT_STORE, classify
from api.models import Tool
from api.tool_stats import bust_tool_stats_cache

DEFAULT_MANIFEST = Path(settings.BASE_DIR) / "data" / "gpt_store_purge.json"
BATCH = 200


def list_gpt_store_rows():
    rows = []
    for tool in (
        Tool.objects.all()
        .only("id", "name", "website", "slug")
        .iterator(chunk_size=500)
    ):
        entry_type, _flags = classify(tool.name, tool.website or "")
        if entry_type == GPT_STORE:
            rows.append(
                {
                    "id": tool.id,
                    "name": tool.name,
                    "website": tool.website,
                    "slug": tool.slug,
                }
            )
    return rows


class Command(BaseCommand):
    help = (
        "Delete rows that classify as ChatGPT store listings. "
        "Writes nothing without --apply. Writes a manifest first."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually delete. Omit for a dry run.",
        )
        parser.add_argument(
            "--manifest",
            default=str(DEFAULT_MANIFEST),
            help="Where to write the id/name/url list before deleting.",
        )

    def handle(self, *args, **options):
        rows = list_gpt_store_rows()
        path = Path(options["manifest"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"count": len(rows), "rows": rows}))
        self.stdout.write(f"Listed {len(rows):,} GPT-store rows at {path}")

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING("Dry run: nothing deleted. Re-run with --apply.")
            )
            return

        ids = [row["id"] for row in rows]
        deleted = 0
        for start in range(0, len(ids), BATCH):
            batch = ids[start : start + BATCH]
            count, _detail = Tool.objects.filter(pk__in=batch).delete()
            deleted += count
            if start and start % 1000 == 0:
                self.stdout.write(f"  progress {start:,}/{len(ids):,}")

        bust_tool_stats_cache()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted:,} database rows (tools + cascaded relations)."
            )
        )
