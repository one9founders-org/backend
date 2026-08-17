"""Run the published-evidence assessment pass over directory rows.

Dry-run unless apply=True. Each OpenAI call is priced; the run aborts
when the running total crosses budget_usd (capped at $50). Writes a
JSON log that records every score and the URL it was cited from.
"""

from __future__ import annotations

import gc
import logging
from dataclasses import asdict, dataclass, field
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from api.models import Tool
from api.tool_enrichment import write_enrichment_log
from api.tool_stats import bust_tool_stats_cache

from . import ASSESS_BUDGET_CEILING_USD, ASSESS_DEFAULT_BUDGET_USD
from .assess import (
    AUTOMATABLE,
    DEFAULT_MODEL,
    MANUAL_ONLY,
    assess,
    assessment_detail,
    empty_usage,
    token_cost_usd,
)
from .evidence import clear_evidence_cache, collect_evidence
from .linkcheck import BROKEN, MALFORMED, PARKED, UNREACHABLE
from .track import TRACK_CHOICES

logger = logging.getLogger(__name__)

TRACK_VALUES = {key for key, _label in TRACK_CHOICES}


@dataclass
class SpendGuard:
    budget_usd: float
    model: str = DEFAULT_MODEL
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def add(self, prompt: int, completion: int) -> None:
        self.prompt_tokens += int(prompt or 0)
        self.completion_tokens += int(completion or 0)

    @property
    def usd(self) -> float:
        return token_cost_usd(self.prompt_tokens, self.completion_tokens, self.model)

    def remaining(self) -> float:
        return self.budget_usd - self.usd

    def exceeded(self) -> bool:
        return self.usd >= self.budget_usd


@dataclass
class ToolOutcome:
    tool_id: int
    name: str
    website: str = ""
    criteria_completed: int = 0
    overall_score: float | None = None
    security_criterion_score: int | None = None
    scored: dict = field(default_factory=dict)
    unassessed: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    skipped: str = ""
    error: str = ""


def clamp_budget(budget_usd: float) -> float:
    if budget_usd <= 0:
        raise ValueError("--budget-usd must be > 0")
    return min(float(budget_usd), ASSESS_BUDGET_CEILING_USD)


def select_tools(
    *,
    limit: int,
    offset: int = 0,
    track: str = "",
    only_unassessed: bool = True,
    stale_days: int = 0,
):
    queryset = Tool.objects.all().order_by("id")
    if track:
        queryset = queryset.filter(track=track)
    if only_unassessed:
        queryset = queryset.filter(last_assessed_at__isnull=True)
    if stale_days:
        cutoff = timezone.now() - timedelta(days=stale_days)
        queryset = queryset.filter(
            Q(last_assessed_at__isnull=True) | Q(last_assessed_at__lt=cutoff)
        )
    queryset = queryset.exclude(Q(website__isnull=True) | Q(website=""))
    queryset = queryset.exclude(
        link_status__in=(BROKEN, MALFORMED, PARKED, UNREACHABLE)
    )
    start = max(offset, 0)
    if limit:
        end = start + limit
        return queryset[start:end]
    if start:
        return queryset[start:]
    return queryset


def _blank_result() -> dict:
    return {
        "scored": {},
        "unassessed": list(AUTOMATABLE),
        "manual_only": list(MANUAL_ONLY),
        "criteria_completed": 0,
        "overall_score": None,
        "security_criterion_score": None,
        "usage": empty_usage(),
    }


def process_tool(tool: Tool) -> tuple[ToolOutcome, dict]:
    outcome = ToolOutcome(tool_id=tool.id, name=tool.name, website=tool.website or "")
    website = (tool.website or "").strip()
    if not website:
        outcome.skipped = "no website"
        return outcome, _blank_result()

    try:
        evidence = collect_evidence(website, track=getattr(tool, "track", "") or "")
        if not evidence:
            outcome.skipped = "no evidence"
            return outcome, _blank_result()

        result = assess(tool.name, website, evidence)
        usage = result.get("usage") or {}
        outcome.usage = usage
        outcome.scored = result.get("scored") or {}
        outcome.unassessed = result.get("unassessed") or []
        outcome.criteria_completed = int(result.get("criteria_completed") or 0)
        outcome.overall_score = result.get("overall_score")
        outcome.security_criterion_score = result.get("security_criterion_score")
        if result.get("error"):
            outcome.error = str(result["error"])
            outcome.skipped = "assess error"
        outcome.notes.append(f"evidence_keys={sorted(evidence.keys())}")
        return outcome, result
    finally:
        clear_evidence_cache()


def apply_outcome(tool: Tool, outcome: ToolOutcome, result: dict, model: str) -> bool:
    """Write scores via QuerySet.update so Tool.save() cannot fire
    auto-enrichment or embeddings — those would blow the OpenAI budget.
    """
    from api.ratings import coerce_overall_score

    completed = int(outcome.criteria_completed or 0)
    overall = coerce_overall_score(completed, outcome.overall_score)
    Tool.objects.filter(pk=tool.pk).update(
        criteria_completed=completed,
        overall_score=overall,
        security_criterion_score=outcome.security_criterion_score,
        assessment_detail=assessment_detail(result, model=model, hands_on=False),
        last_assessed_at=timezone.now(),
    )
    return True


def run(
    *,
    limit: int = 50,
    offset: int = 0,
    apply: bool = False,
    track: str = "",
    budget_usd: float = ASSESS_DEFAULT_BUDGET_USD,
    only_unassessed: bool = True,
    stale_days: int = 0,
    model: str = "",
) -> dict:
    from django.conf import settings

    budget = clamp_budget(budget_usd)
    model_name = model or getattr(settings, "HYGIENE_ASSESS_MODEL", DEFAULT_MODEL)
    guard = SpendGuard(budget_usd=budget, model=model_name)
    tools = list(
        select_tools(
            limit=limit,
            offset=offset,
            track=track,
            only_unassessed=only_unassessed,
            stale_days=stale_days,
        )
    )

    outcomes: list[ToolOutcome] = []
    applied = 0
    aborted = ""
    for index, tool in enumerate(tools, start=1):
        if guard.exceeded():
            aborted = (
                f"budget ${guard.usd:.4f} reached ceiling ${budget:.2f} "
                f"after {index - 1} tools"
            )
            logger.warning("Assessment abort: %s", aborted)
            break
        try:
            outcome, result = process_tool(tool)
        except Exception:
            logger.exception("Assessment failed for tool id=%s", tool.id)
            outcome = ToolOutcome(
                tool_id=tool.id,
                name=tool.name,
                website=tool.website or "",
                skipped="exception",
            )
            result = None
        usage = outcome.usage or {}
        guard.add(usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0)
        outcomes.append(outcome)
        if (
            apply
            and result is not None
            and outcome.skipped
            not in {
                "no website",
                "assess error",
                "exception",
            }
        ):
            apply_outcome(tool, outcome, result, model_name)
            applied += 1
        if index % 25 == 0:
            gc.collect()
        if index % 250 == 0:
            logger.info(
                "Assess progress %s/%s applied=%s spent=$%.4f tokens=%s+%s",
                index,
                len(tools),
                applied,
                guard.usd,
                guard.prompt_tokens,
                guard.completion_tokens,
            )

    if apply and applied:
        bust_tool_stats_cache()

    payload = {
        "kind": "assess",
        "ran_at": timezone.now().isoformat(),
        "applied": apply,
        "track": track,
        "budget_usd": budget,
        "spent_usd": round(guard.usd, 6),
        "prompt_tokens": guard.prompt_tokens,
        "completion_tokens": guard.completion_tokens,
        "model": model_name,
        "aborted": bool(aborted),
        "abort_reason": aborted,
        "selected": len(tools),
        "processed": len(outcomes),
        "with_scores": sum(1 for o in outcomes if o.criteria_completed),
        "provisional": sum(1 for o in outcomes if o.overall_score is not None),
        "updated": applied,
        "entries": [asdict(o) for o in outcomes],
    }
    log_path = write_enrichment_log(payload)

    return {
        "selected": len(tools),
        "processed": len(outcomes),
        "with_scores": payload["with_scores"],
        "provisional": payload["provisional"],
        "updated": applied,
        "skipped": sum(1 for o in outcomes if o.skipped),
        "spent_usd": payload["spent_usd"],
        "prompt_tokens": guard.prompt_tokens,
        "completion_tokens": guard.completion_tokens,
        "aborted": bool(aborted),
        "abort_reason": aborted,
        "log_path": str(log_path),
    }
