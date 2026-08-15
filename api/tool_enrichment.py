"""Shared helpers for tool content enrichment import / revert."""

import csv
import json
import logging
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from .models import Category, Tool

logger = logging.getLogger(__name__)

UNMAPPED_TOOL_FIELDS = frozenset({"pros", "cons"})

_PRICING_TYPE_KEYS = {key for key, _label in Tool.PRICING_TYPE_CHOICES}
_PRICING_TYPE_LABELS = {label.lower(): key for key, label in Tool.PRICING_TYPE_CHOICES}
_PRICING_MODEL_KEYS = {key for key, _label in Tool.PRICING_CHOICES}
_PRICING_MODEL_LABELS = {label.lower(): key for key, label in Tool.PRICING_CHOICES}


def enrichment_log_dir() -> Path:
    return Path(
        getattr(settings, "ENRICHMENT_LOG_DIR", settings.BASE_DIR / "enrichment-logs")
    )


def batch_slug_from_csv(source_csv: Path) -> str:
    """approved_batch1.csv -> batch1; other names keep their stem."""
    stem = source_csv.stem
    prefix = "approved_"
    start = len(prefix)
    if stem.lower().startswith(prefix):
        return stem[start:] or source_csv.stem
    return stem


def write_enrichment_log(payload: dict, source_csv: Path | None = None) -> Path:
    """Write enrichment-logs/YYYY-MM-DD-<batch>.json (time suffix if taken)."""
    log_dir = enrichment_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    date = timezone.now().strftime("%Y-%m-%d")
    batch = batch_slug_from_csv(source_csv) if source_csv else "batch"
    path = log_dir / f"{date}-{batch}.json"
    if path.exists():
        path = log_dir / f"{date}-{batch}-{timezone.now().strftime('%H%M%S')}.json"
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def read_csv_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for raw in reader:
            rows.append(
                {
                    (key or "").strip().lower(): (value or "").strip()
                    for key, value in raw.items()
                }
            )
        return rows


def parse_tool_id(row: dict) -> int | None:
    raw = row.get("tool_id") or row.get("id") or ""
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def is_approved(row: dict) -> bool:
    return (row.get("approved") or "").strip().lower() == "yes"


def _normalize_token(token: str) -> str:
    return token.strip().lower().replace(" ", "_").replace("-", "_")


def _resolve_pricing_token(token: str) -> tuple[str, str] | None:
    key = _normalize_token(token)
    label = token.strip().lower()
    if key in _PRICING_TYPE_KEYS:
        return ("type", key)
    if label in _PRICING_TYPE_LABELS:
        return ("type", _PRICING_TYPE_LABELS[label])
    if key in _PRICING_MODEL_KEYS:
        return ("model", key)
    if label in _PRICING_MODEL_LABELS:
        return ("model", _PRICING_MODEL_LABELS[label])
    return None


def parse_pricing(raw: str) -> tuple[str, object] | None:
    """Map a CSV pricing cell onto pricing_type or pricing_models."""
    text = (raw or "").strip()
    if not text:
        return None

    tokens: list[str]
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list) and parsed:
            tokens = [str(item).strip() for item in parsed if str(item).strip()]
        else:
            return None
    elif "," in text:
        tokens = [part.strip() for part in text.split(",") if part.strip()]
    else:
        tokens = [text]

    resolved = [_resolve_pricing_token(token) for token in tokens]
    if not resolved or any(item is None for item in resolved):
        return None
    if len(resolved) == 1 and resolved[0][0] == "type":
        return ("pricing_type", resolved[0][1])
    return ("pricing_models", [item[1] for item in resolved])


def category_names(tool: Tool) -> list[str]:
    return sorted(tool.categories.values_list("name", flat=True))


def load_category_index() -> dict[str, Category]:
    index: dict[str, Category] = {}
    for category in Category.objects.all():
        index[category.name.lower()] = category
        index[category.slug.lower()] = category
        index[slugify(category.name)] = category
    return index


def resolve_categories(
    raw: str, index: dict[str, Category] | None = None
) -> tuple[list[Category], list[str]]:
    if index is None:
        index = load_category_index()
    names = [part.strip() for part in (raw or "").split(",") if part.strip()]
    found: list[Category] = []
    missing: list[str] = []
    seen_ids: set[int] = set()
    for name in names:
        category = index.get(name.lower()) or index.get(slugify(name))
        if category is None:
            missing.append(name)
            continue
        if category.id not in seen_ids:
            seen_ids.add(category.id)
            found.append(category)
    return found, missing


def values_equal(old, new) -> bool:
    if isinstance(old, list) and isinstance(new, list):
        return old == new
    return str(old if old is not None else "") == str(new if new is not None else "")


def build_tool_diff(
    tool: Tool,
    row: dict,
    category_index: dict[str, Category] | None = None,
) -> tuple[list[dict], list[str], list[str]]:
    """Return (changes, unmapped_nonempty_fields, field_warnings)."""
    changes: list[dict] = []
    unmapped: list[str] = []
    warnings: list[str] = []

    description = row.get("description") or ""
    if description:
        old = tool.description or ""
        if not values_equal(old, description):
            changes.append(
                {
                    "field": "description",
                    "old_value": old,
                    "new_value": description,
                }
            )

    pricing_raw = row.get("pricing") or ""
    if pricing_raw:
        mapped = parse_pricing(pricing_raw)
        if mapped is None:
            warnings.append(
                f"pricing value {pricing_raw!r} does not match Tool.pricing_type "
                f"or Tool.pricing_models choices; skipped"
            )
        else:
            field, new_value = mapped
            old_value = getattr(tool, field)
            if field == "pricing_models":
                old_value = list(old_value or [])
            if not values_equal(old_value, new_value):
                changes.append(
                    {
                        "field": field,
                        "old_value": old_value,
                        "new_value": new_value,
                    }
                )

    for field in UNMAPPED_TOOL_FIELDS:
        if row.get(field):
            unmapped.append(field)

    category_raw = row.get("category") or ""
    if category_raw:
        categories, missing = resolve_categories(category_raw, category_index)
        if missing:
            warnings.append(
                f"category name(s) not found and skipped: {', '.join(missing)}"
            )
        if categories:
            new_names = sorted(category.name for category in categories)
            old_names = category_names(tool)
            if not values_equal(old_names, new_names):
                changes.append(
                    {
                        "field": "categories",
                        "old_value": old_names,
                        "new_value": new_names,
                    }
                )

    return changes, unmapped, warnings


def load_tools(tool_ids: list[int]) -> dict[int, Tool]:
    return {
        tool.id: tool
        for tool in Tool.objects.filter(id__in=tool_ids).prefetch_related("categories")
    }


def apply_tool_changes(
    tool: Tool,
    changes: list[dict],
    *,
    use_old: bool,
    category_index: dict[str, Category] | None = None,
) -> None:
    scalar_update = {}
    for change in changes:
        field = change["field"]
        value = change["old_value"] if use_old else change["new_value"]
        if field == "categories":
            categories, missing = resolve_categories(
                ", ".join(value or []), category_index
            )
            if missing:
                logger.warning(
                    "Tool %s: category name(s) missing during apply: %s",
                    tool.id,
                    ", ".join(missing),
                )
            tool.categories.set(categories)
        elif field in {"description", "pricing_type", "pricing_models"}:
            scalar_update[field] = value
        else:
            logger.warning(
                "Tool %s: unknown enrichment field %s; skipped", tool.id, field
            )
    if scalar_update:
        scalar_update["updated_at"] = timezone.now()
        Tool.objects.filter(pk=tool.pk).update(**scalar_update)


def apply_diff_entries(entries: list[dict], *, use_old: bool) -> tuple[int, list[int]]:
    """Apply diffs. Returns (updated_count, missing_tool_ids)."""
    tool_ids = [entry["tool_id"] for entry in entries]
    tools = load_tools(tool_ids)
    category_index = load_category_index()
    updated = 0
    missing: list[int] = []
    with transaction.atomic():
        for entry in entries:
            tool = tools.get(entry["tool_id"])
            if tool is None:
                missing.append(entry["tool_id"])
                logger.warning(
                    "Tool id=%s not found; skipped during apply", entry["tool_id"]
                )
                continue
            apply_tool_changes(
                tool,
                entry.get("changes") or [],
                use_old=use_old,
                category_index=category_index,
            )
            updated += 1
    return updated, missing
