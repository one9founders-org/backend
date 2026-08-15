"""Orchestrate discover -> facts -> generate -> gate -> publish/refresh."""

import logging

from django.db.models import F
from django.utils import timezone
from django.utils.text import slugify

from api.models import Category, DiscoveryRun, Tool

from . import MAX_NEW_TOOLS_PER_RUN, REFRESH_NOOP_RATIO
from .facts import Facts, fetch_facts
from .generate import generate_description
from .quality_gate import passes_quality_gate, similarity_ratio
from .sources import candidate_signal, discover_candidates

logger = logging.getLogger(__name__)

SIMILARITY_ONLY_PREFIX = "description too similar to source"
RETRY_INSTRUCTION = (
    "Paraphrase more aggressively, use different sentence structure, "
    "and do not reuse wording from typical marketing or README copy."
)


def log_run(
    *,
    run_type: str,
    tool_name: str,
    url: str,
    status: str,
    reasons: str = "",
) -> DiscoveryRun:
    return DiscoveryRun.objects.create(
        run_type=run_type,
        tool_name=tool_name[:255],
        url=(url or "")[:500],
        status=status,
        reasons=reasons,
    )


def process_candidate(candidate: dict) -> dict:
    name = (candidate.get("name") or "").strip()
    url = (candidate.get("url") or "").strip()
    facts = fetch_facts(url)
    generated = generate_description(name, facts)
    passed, reasons = passes_quality_gate(name, generated, facts, facts.source_text)

    if (
        not passed
        and reasons
        and all(reason.startswith(SIMILARITY_ONLY_PREFIX) for reason in reasons)
    ):
        generated = generate_description(
            name, facts, extra_instruction=RETRY_INSTRUCTION
        )
        passed, reasons = passes_quality_gate(name, generated, facts, facts.source_text)

    return {
        "name": name,
        "url": url,
        "facts": facts,
        "generated": generated,
        "passed": passed,
        "reasons": reasons,
    }


def _apply_facts_to_create(tool: Tool, facts: Facts) -> None:
    if not facts.category:
        return
    category = Category.objects.filter(name__iexact=facts.category).first()
    if category:
        tool.categories.add(category)


def publish_new_tool(result: dict) -> Tool:
    name = result["name"]
    description = result["generated"]
    now = timezone.now()
    tool = Tool(
        name=name[:255],
        slug=(slugify(name) or f"tool-{int(now.timestamp())}")[:255],
        website=result["url"],
        description=description,
        short_description=description[:200],
        tags=["auto-discovery"],
        last_enriched_at=now,
    )
    facts = result["facts"]
    if facts.pricing:
        tool.pricing_type = facts.pricing
    tool.save()
    _apply_facts_to_create(tool, facts)
    return tool


def run_new_tool_discovery(max_new: int | None = MAX_NEW_TOOLS_PER_RUN) -> dict:
    candidates = discover_candidates()
    ranked = sorted(candidates, key=candidate_signal, reverse=True)
    if max_new is None:
        to_process = ranked
        deferred = []
    else:
        to_process = ranked[:max_new]
        deferred = ranked[max_new:]

    published = rejected = errored = 0
    for candidate in deferred:
        log_run(
            run_type="new",
            tool_name=candidate.get("name") or "",
            url=candidate.get("url") or "",
            status="deferred",
            reasons="deferred, over cap",
        )

    for candidate in to_process:
        name = candidate.get("name") or ""
        url = candidate.get("url") or ""
        try:
            result = process_candidate(candidate)
            if result["passed"]:
                publish_new_tool(result)
                log_run(
                    run_type="new",
                    tool_name=name,
                    url=url,
                    status="published",
                )
                published += 1
            else:
                log_run(
                    run_type="new",
                    tool_name=name,
                    url=url,
                    status="rejected",
                    reasons="; ".join(result["reasons"]),
                )
                rejected += 1
        except Exception as exc:
            logger.exception("Discovery failed for %s", name)
            log_run(
                run_type="new",
                tool_name=name,
                url=url,
                status="error",
                reasons=str(exc),
            )
            errored += 1

    return {
        "candidates_found": len(candidates),
        "published": published,
        "rejected": rejected,
        "errored": errored,
        "deferred_over_cap": len(deferred),
    }


def run_refresh_descriptions(limit: int = 50) -> dict:
    tools = list(
        Tool.objects.exclude(website__isnull=True)
        .exclude(website="")
        .order_by(F("last_enriched_at").asc(nulls_first=True), "id")[:limit]
    )
    updated = rejected = skipped = errored = 0

    for tool in tools:
        try:
            facts = fetch_facts(tool.website)
            generated = generate_description(tool.name, facts)
            passed, reasons = passes_quality_gate(
                tool.name, generated, facts, facts.source_text
            )
            if (
                not passed
                and reasons
                and all(reason.startswith(SIMILARITY_ONLY_PREFIX) for reason in reasons)
            ):
                generated = generate_description(
                    tool.name, facts, extra_instruction=RETRY_INSTRUCTION
                )
                passed, reasons = passes_quality_gate(
                    tool.name, generated, facts, facts.source_text
                )

            if not passed:
                log_run(
                    run_type="refresh",
                    tool_name=tool.name,
                    url=tool.website or "",
                    status="refresh_rejected",
                    reasons="; ".join(reasons),
                )
                rejected += 1
                continue

            if (
                similarity_ratio(generated, tool.description or "")
                >= REFRESH_NOOP_RATIO
            ):
                Tool.objects.filter(pk=tool.pk).update(last_enriched_at=timezone.now())
                skipped += 1
                continue

            Tool.objects.filter(pk=tool.pk).update(
                description=generated,
                last_enriched_at=timezone.now(),
            )
            log_run(
                run_type="refresh",
                tool_name=tool.name,
                url=tool.website or "",
                status="updated",
            )
            updated += 1
        except Exception as exc:
            logger.exception("Refresh failed for %s", tool.name)
            log_run(
                run_type="refresh",
                tool_name=tool.name,
                url=tool.website or "",
                status="error",
                reasons=str(exc),
            )
            errored += 1

    return {
        "selected": len(tools),
        "updated": updated,
        "refresh_rejected": rejected,
        "noop_skipped": skipped,
        "errored": errored,
    }
