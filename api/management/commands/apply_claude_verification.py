"""Write web-checked Claude drafts onto directory rows.

Matches by slug. Updates a row when one exists. Inserts a row when the
slug is new. Skips hand-verified listings and drafts below the confidence
bar. Dry-run unless --apply is given. Writes a diff log that
revert_tool_enrichment can replay.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from api.hygiene.enrich import MIN_WRITE_CONFIDENCE
from api.hygiene.taxonomy import infer_tags
from api.models import Tool
from api.tool_enrichment import apply_tool_changes, write_enrichment_log
from api.verified_listings import protected_from_ai

DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "claude_verification_2026_10_16.jsonl"
)
PRICING_TYPES = {"free", "freemium", "paid"}


def _clip(text, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


def _strings(value, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        text = _clip(item, 200)
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _host(url: str) -> str:
    return (urlparse(url or "").netloc or "").lower().removeprefix("www.")


def load_drafts(path: Path) -> list[dict]:
    drafts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        record = item.get("record") or {}
        if item.get("error"):
            continue
        try:
            confidence = float(record.get("confidence") or 0)
        except (TypeError, ValueError):
            continue
        if confidence < MIN_WRITE_CONFIDENCE or not record.get("exists"):
            continue
        description = _clip(record.get("description"), 8000)
        short = _clip(record.get("short_description"), 200)
        if not description or not short:
            continue
        drafts.append(
            {
                "slug": _clip(item.get("slug"), 255),
                "name": _clip(item.get("name") or item.get("slug"), 255),
                "listed_website": _clip(item.get("listed_website"), 200),
                "official_url": _clip(record.get("official_url"), 200),
                "description": description,
                "short_description": short,
                "pricing_type": (record.get("pricing_type") or "").strip().lower(),
                "pricing_source_url": _clip(record.get("pricing_source_url"), 500),
                "free_tier": bool(record.get("free_tier")),
                "features": _strings(record.get("features"), 12),
                "use_cases": _strings(record.get("use_cases"), 8),
                "integrations": _strings(record.get("integrations"), 12),
                "status": (record.get("status") or "").strip().lower(),
                "confidence": confidence,
            }
        )
    return drafts


def _changes_for(tool: Tool, draft: dict) -> list[dict]:
    changes = []

    def consider(field: str, new_value) -> None:
        old_value = getattr(tool, field)
        if isinstance(old_value, list):
            old_value = list(old_value or [])
        if old_value != new_value and str(old_value or "") != str(new_value or ""):
            changes.append(
                {"field": field, "old_value": old_value, "new_value": new_value}
            )

    consider("short_description", draft["short_description"])
    consider("description", draft["description"])
    if draft["features"]:
        consider("features", draft["features"])
    if draft["use_cases"]:
        consider("use_cases", draft["use_cases"])
    if draft["integrations"]:
        consider("integrations", draft["integrations"])

    official = draft["official_url"]
    if (
        official.startswith("http")
        and _host(official)
        and _host(official) != _host(tool.website or "")
    ):
        consider("website", official)

    sourced = (
        draft["pricing_source_url"].startswith("http")
        and draft["pricing_type"] in PRICING_TYPES
    )
    if sourced:
        consider("pricing_type", draft["pricing_type"])
        consider("free_tier_available", draft["free_tier"])
        consider("startup_friendly", draft["free_tier"])

    if draft["status"] == "shutdown" and tool.is_active:
        consider("is_active", False)
    return changes


def _insert(draft: dict) -> Tool:
    pricing = (
        draft["pricing_type"] if draft["pricing_type"] in PRICING_TYPES else "freemium"
    )
    sourced = (
        draft["pricing_source_url"].startswith("http")
        and draft["pricing_type"] in PRICING_TYPES
    )
    website = draft["official_url"] if draft["official_url"].startswith("http") else ""
    if not website:
        website = draft["listed_website"]
    tool = Tool(
        name=draft["name"],
        slug=draft["slug"],
        short_description=draft["short_description"],
        description=draft["description"],
        website=website or None,
        pricing_type=pricing if sourced else "freemium",
        free_tier_available=draft["free_tier"] if sourced else False,
        startup_friendly=draft["free_tier"] if sourced else False,
        features=draft["features"],
        use_cases=draft["use_cases"],
        integrations=draft["integrations"],
        tags=infer_tags(f"{draft['name']} {draft['description']}") or ["productivity"],
        is_active=draft["status"] != "shutdown",
        verified=False,
    )
    Tool.objects.bulk_create([tool])
    return Tool.objects.get(slug=draft["slug"])


class Command(BaseCommand):
    help = (
        "Apply web-checked Claude drafts to directory rows. "
        "Writes nothing without --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_FIXTURE))
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist changes. Omit for a dry run.",
        )

    def handle(self, *args, **options):
        path = Path(options["file"]).expanduser()
        if not path.is_file():
            raise CommandError(f"Draft file not found: {path}")
        drafts = load_drafts(path)
        apply = options["apply"]
        updated = 0
        inserted = 0
        skipped_protected = 0
        unchanged = 0
        entries = []

        with transaction.atomic():
            for draft in drafts:
                if not draft["slug"]:
                    continue
                tool = Tool.objects.filter(slug=draft["slug"]).first()
                if tool is None and Tool.objects.filter(name=draft["name"]).exists():
                    skipped_protected += 1
                    continue
                if tool is not None and protected_from_ai(tool):
                    skipped_protected += 1
                    continue
                if tool is None:
                    if apply:
                        tool = _insert(draft)
                        inserted += 1
                        entries.append(
                            {
                                "tool_id": tool.id,
                                "slug": tool.slug,
                                "inserted": True,
                                "changes": [],
                            }
                        )
                    else:
                        inserted += 1
                    continue
                changes = _changes_for(tool, draft)
                if not changes:
                    unchanged += 1
                    continue
                if apply:
                    apply_tool_changes(tool, changes, use_old=False)
                updated += 1
                entries.append(
                    {
                        "tool_id": tool.id,
                        "slug": tool.slug,
                        "changes": changes,
                    }
                )
            if not apply:
                transaction.set_rollback(True)

        log_path = ""
        if apply and entries:
            payload = {
                "kind": "claude_verification",
                "tools": entries,
                "ran_at": timezone.now().isoformat(),
            }
            log_path = str(write_enrichment_log(payload))
            # The data volume survives the next image rebuild, so a revert
            # file is still on the server after this deploy.
            from django.conf import settings

            durable = Path(settings.BASE_DIR) / "data"
            durable.mkdir(parents=True, exist_ok=True)
            durable_path = durable / "claude-verification-apply.json"
            durable_path.write_text(
                json.dumps(payload, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            log_path = str(durable_path)

        mode = "APPLY" if apply else "DRY RUN"
        self.stdout.write(f"--- Claude verification ({mode}) ---")
        self.stdout.write(f"Drafts:    {len(drafts)}")
        self.stdout.write(f"Updated:   {updated}")
        self.stdout.write(f"Inserted:  {inserted}")
        self.stdout.write(f"Unchanged: {unchanged}")
        self.stdout.write(f"Protected: {skipped_protected}")
        if log_path:
            self.stdout.write(f"Log:       {log_path}")
        if not apply:
            self.stdout.write("Dry run: nothing written. Re-run with --apply.")
