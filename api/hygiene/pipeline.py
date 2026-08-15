"""Run the hygiene pass over directory rows.

Order matters and is cheap-to-expensive on purpose, so most rows are
resolved before any paid API is touched:

    classify (free) -> link check (free) -> logo (free)
        -> Tranco/Wikidata/HN (free) -> LLM enrich (paid) -> rank
    Google search is opt-in only (--search) and is not required.

Every stage is skippable, nothing writes unless apply=True, and each run
emits a JSON log that revert_hygiene can replay backwards.
"""

import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import timedelta

from django.db.models import F, Q
from django.utils import timezone

from api.discovery.facts import fetch_facts
from api.models import Tool
from api.tool_enrichment import write_enrichment_log
from api.tool_stats import bust_tool_stats_cache

from . import RANK_FEATURE_THRESHOLD
from .classify import classify, is_publishable
from .enrich import enrich
from .linkcheck import BROKEN, MALFORMED, UNREACHABLE, check_url
from .logos import resolve_logo
from .rank import RankInputs, completeness_score, display_order_for, score
from .signals import external_score as free_external_score
from .signals import gather as gather_signals
from .signals import open_tranco
from .taxonomy import balance, migrate_legacy_tags
from .websearch import is_configured as search_configured
from .websearch import search_footprint_score, verify_tool

logger = logging.getLogger(__name__)

# Fields the pass is allowed to touch. Anything else is left alone.
WRITABLE_FIELDS = frozenset(
    {
        "short_description",
        "description",
        "tags",
        "use_cases",
        "features",
        "ideal_for",
        "startup_benefits",
        "pricing_type",
        "logo_url",
        "entry_type",
        "hygiene_flags",
        "link_status",
        "link_checked_at",
        "link_final_url",
        "popularity_score",
        "display_order",
        "last_hygiene_at",
    }
)

DEAD_STATUSES = {BROKEN, UNREACHABLE, MALFORMED}


@dataclass
class Stages:
    link: bool = True
    logo: bool = True
    signals: bool = True  # free: Tranco + Wikidata + Hacker News
    search: bool = False  # paid: Google Programmable Search, opt-in only
    llm: bool = True


@dataclass
class ToolOutcome:
    tool_id: int
    name: str
    changes: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    skipped: str = ""


def _record(outcome: ToolOutcome, tool: Tool, field_name: str, new_value) -> None:
    """Append a change only when the value actually differs."""
    old_value = getattr(tool, field_name)
    if isinstance(old_value, list) or isinstance(new_value, list):
        if list(old_value or []) == list(new_value or []):
            return
        old_value = list(old_value or [])
    else:
        if str(old_value or "") == str(new_value or ""):
            return
    outcome.changes.append(
        {"field": field_name, "old_value": old_value, "new_value": new_value}
    )


def select_tools(
    *,
    limit: int,
    offset: int = 0,
    entry_type: str = "",
    only_missing_logo: bool = False,
    only_unchecked: bool = False,
    stale_days: int = 0,
):
    queryset = Tool.objects.all().order_by(
        F("last_hygiene_at").asc(nulls_first=True),
        "id",
    )
    if entry_type:
        queryset = queryset.filter(entry_type=entry_type)
    if only_missing_logo:
        queryset = queryset.filter(Q(logo_url__isnull=True) | Q(logo_url=""))
    if only_unchecked:
        queryset = queryset.filter(last_hygiene_at__isnull=True)
    if stale_days:
        cutoff = timezone.now() - timedelta(days=stale_days)
        queryset = queryset.filter(
            Q(last_hygiene_at__isnull=True) | Q(last_hygiene_at__lt=cutoff)
        )
    start = max(offset, 0)
    if limit:
        end = start + limit
        return queryset[start:end]
    if start:
        return queryset[start:]
    return queryset


def process_tool(
    tool: Tool,
    stages: Stages,
    connection: "sqlite3.Connection | None" = None,
) -> ToolOutcome:
    """Gather every revision for one row. Never writes."""
    outcome = ToolOutcome(tool_id=tool.id, name=tool.name)
    website = tool.website or ""

    entry_type, flags = classify(tool.name, website)
    _record(outcome, tool, "entry_type", entry_type)
    _record(outcome, tool, "hygiene_flags", flags)
    publishable = is_publishable(entry_type, flags)
    if not publishable:
        outcome.notes.append(f"not publishable as a product ({entry_type})")
        outcome.skipped = "not publishable"
        rank_inputs = RankInputs(
            completeness=completeness_score(_tool_snapshot(tool)),
            penalties=["not_publishable"],
        )
        final = score(rank_inputs)
        _record(outcome, tool, "popularity_score", final)
        _record(outcome, tool, "display_order", display_order_for(final))
        _record(outcome, tool, "last_hygiene_at", timezone.now())
        return outcome

    link_result = None
    if stages.link and website:
        link_result = check_url(website)
        _record(outcome, tool, "link_status", link_result.status)
        _record(outcome, tool, "link_checked_at", timezone.now())
        if link_result.final_url:
            _record(outcome, tool, "link_final_url", link_result.final_url[:500])
        if link_result.status in DEAD_STATUSES:
            outcome.notes.append(f"link {link_result.status}: {link_result.detail}")

    link_is_dead = link_result is not None and link_result.status in DEAD_STATUSES

    # Everything below costs time or money, so stop on rows that cannot
    # benefit from it.
    if link_is_dead:
        outcome.skipped = "dead link"
        rank_inputs = RankInputs(
            completeness=completeness_score(_tool_snapshot(tool)),
            penalties=["broken_link"],
        )
        final = score(rank_inputs)
        _record(outcome, tool, "popularity_score", final)
        _record(outcome, tool, "display_order", display_order_for(final))
        _record(outcome, tool, "last_hygiene_at", timezone.now())
        return outcome

    resolved_url = (link_result.final_url if link_result else "") or website

    if stages.logo and not (tool.logo_url or "").strip():
        logo = resolve_logo(resolved_url)
        if logo.found:
            _record(outcome, tool, "logo_url", logo.url)
            outcome.notes.append(f"logo from {logo.source}")

    facts = fetch_facts(resolved_url)

    # Free signals first. These cover the popularity and notability
    # questions without any paid quota, so the search stage below is only
    # worth running when it is explicitly enabled and configured.
    signals = None
    external = 0.0
    if stages.signals:
        signals = gather_signals(tool.name, resolved_url, connection=connection)
        external = free_external_score(signals)
        outcome.notes.extend(signals.notes)
        if signals.tranco_rank:
            outcome.notes.append(f"tranco rank {signals.tranco_rank}")

    evidence = None
    if stages.search and search_configured():
        evidence = verify_tool(tool.name, resolved_url)
        # Paid search only ever raises the score; it never overrides a
        # free signal that already found the tool.
        external = max(external, search_footprint_score(evidence))
        if evidence.ok and not evidence.official_site_matched:
            outcome.notes.append("google did not surface the listed website")

    if stages.llm:
        enriched = enrich(tool.name, resolved_url, facts, evidence, signals)
        if enriched.get("insufficient_evidence"):
            outcome.notes.append("insufficient evidence; content left unchanged")
        else:
            for field_name in (
                "short_description",
                "description",
                "startup_benefits",
                "pricing_type",
            ):
                value = enriched.get(field_name)
                if value:
                    _record(outcome, tool, field_name, value)
            for field_name in ("use_cases", "features", "ideal_for"):
                value = enriched.get(field_name)
                if value:
                    _record(outcome, tool, field_name, value)
            tags = enriched.get("tags") or []
            if tags:
                _record(outcome, tool, "tags", tags)
    else:
        # Even without the LLM, legacy tags can be mapped onto the new vocabulary.
        migrated = balance(migrate_legacy_tags(list(tool.tags or [])))
        if migrated:
            _record(outcome, tool, "tags", migrated)

    snapshot = _tool_snapshot(tool)
    for change in outcome.changes:
        snapshot[change["field"]] = change["new_value"]
    final = score(
        RankInputs(
            external_score=external,
            clicks=getattr(tool, "click_count", 0) or 0,
            views=tool.views_count or 0,
            completeness=completeness_score(snapshot),
        )
    )
    _record(outcome, tool, "popularity_score", final)
    _record(outcome, tool, "display_order", display_order_for(final))
    _record(outcome, tool, "last_hygiene_at", timezone.now())
    if final >= RANK_FEATURE_THRESHOLD:
        outcome.notes.append(f"feature-eligible (score {final})")
    return outcome


def _tool_snapshot(tool: Tool) -> dict:
    return {
        "short_description": tool.short_description,
        "description": tool.description,
        "logo_url": tool.logo_url,
        "website": tool.website,
        "tags": list(tool.tags or []),
        "use_cases": list(tool.use_cases or []),
        "pricing_type": tool.pricing_type,
        "features": list(tool.features or []),
    }


def apply_outcome(outcome: ToolOutcome) -> bool:
    updates = {
        change["field"]: change["new_value"]
        for change in outcome.changes
        if change["field"] in WRITABLE_FIELDS
    }
    if not updates:
        return False
    Tool.objects.filter(pk=outcome.tool_id).update(**updates)
    return True


def run(
    *,
    limit: int = 50,
    offset: int = 0,
    apply: bool = False,
    stages: Stages | None = None,
    entry_type: str = "",
    only_missing_logo: bool = False,
    only_unchecked: bool = False,
    stale_days: int = 0,
    search_budget: int = 8000,
) -> dict:
    stages = stages or Stages()
    if stages.search and not search_configured():
        logger.warning("GOOGLE_SEARCH_API_KEY/CX are not set; search stage will no-op.")
        stages.search = False

    # One read-only handle for the whole run; the lookup is per-tool but
    # opening the file per tool would dominate the runtime.
    connection = open_tranco() if stages.signals else None
    if stages.signals and connection is None:
        logger.warning(
            "Tranco lookup unavailable; popularity will fall back to "
            "Wikidata and Hacker News only."
        )

    tools = list(
        select_tools(
            limit=limit,
            offset=offset,
            entry_type=entry_type,
            only_missing_logo=only_missing_logo,
            only_unchecked=only_unchecked,
            stale_days=stale_days,
        )
    )

    outcomes: list[ToolOutcome] = []
    searches_used = 0
    applied = 0
    for index, tool in enumerate(tools, start=1):
        if stages.search and searches_used >= search_budget:
            stages.search = False
            logger.warning(
                "Hygiene search budget of %s reached; remaining rows skip Google.",
                search_budget,
            )
        try:
            before_search = stages.search
            outcome = process_tool(tool, stages, connection)
            outcomes.append(outcome)
            if before_search and not outcome.skipped:
                searches_used += 1
            # Apply as we go so a killed run still keeps finished rows.
            # --only-unchecked then resumes from the rest.
            if apply and outcome.changes and apply_outcome(outcome):
                applied += 1
        except Exception:
            logger.exception("Hygiene pass failed for tool id=%s", tool.id)
        if index % 50 == 0:
            logger.info(
                "Hygiene progress %s/%s applied=%s",
                index,
                len(tools),
                applied,
            )

    if connection is not None:
        connection.close()

    if apply and applied:
        bust_tool_stats_cache()

    changed = [o for o in outcomes if o.changes]
    payload = {
        "kind": "hygiene",
        "ran_at": timezone.now().isoformat(),
        "applied": apply,
        "selected": len(tools),
        "with_changes": len(changed),
        "updated": applied,
        "stages": asdict(stages),
        "entries": [asdict(o) for o in outcomes],
    }
    log_path = write_enrichment_log(payload)

    return {
        "selected": len(tools),
        "with_changes": len(changed),
        "updated": applied,
        "skipped": sum(1 for o in outcomes if o.skipped),
        "log_path": str(log_path),
    }
