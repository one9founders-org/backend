"""Orchestrate discover -> facts -> generate -> gate -> publish/refresh."""

import logging
from decimal import Decimal, InvalidOperation

from django.db.models import F
from django.utils import timezone
from django.utils.text import slugify

from api.hygiene.logos import resolve_logo
from api.hygiene.track import classify_track
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
    prefer_fc = (candidate.get("sourceType") or "").startswith("firecrawl")
    facts = fetch_facts(url, prefer_firecrawl=prefer_fc or True)
    # Prefer product name from Firecrawl extract over long SERP titles.
    if facts.title and len(facts.title) < len(name):
        name = facts.title.strip()
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
        "candidate": candidate,
        "facts": facts,
        "generated": generated,
        "passed": passed,
        "reasons": reasons,
    }


def _apply_categories(tool: Tool, facts: Facts) -> None:
    names: list[str] = []
    if facts.category:
        names.append(facts.category)
    names.extend(facts.categories or [])
    seen: set[str] = set()
    for name in names:
        key = name.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        category = Category.objects.filter(name__iexact=name.strip()).first()
        if category:
            tool.categories.add(category)


def _resolve_logo_url(url: str, facts: Facts) -> str:
    if facts.logo_url:
        return facts.logo_url[:500]
    try:
        result = resolve_logo(url, verify=False)
        return (result.url or "")[:500]
    except Exception as exc:
        logger.debug("logo resolve failed for %s: %s", url, exc)
        return ""


def publish_new_tool(result: dict) -> Tool:
    name = result["name"]
    description = result["generated"]
    url = result["url"]
    facts = result["facts"]
    candidate = result.get("candidate") or {}
    raw = candidate.get("rawSignal") or {}
    now = timezone.now()

    # Prefer GitHub repo URL when extract found one — that buckets OSS.
    website = url
    if facts.github_url and "github.com" in facts.github_url.lower():
        # Keep product site as website unless the candidate itself was a repo.
        if "github.com" in (url or "").lower():
            website = facts.github_url

    track_text = " ".join(
        filter(
            None,
            [
                description or "",
                " ".join(facts.topics or []),
                " ".join(facts.categories or []),
            ],
        )
    )
    track = classify_track(
        name,
        facts.github_url or website,
        track_text,
        topics=list(facts.topics or []),
        has_license=bool(facts.github_url),
    )

    tags = ["auto-discovery"]
    source = candidate.get("sourceType") or ""
    if source:
        tags.append(source)
    if facts.india_focused or raw.get("india_focus"):
        tags.append("india")
    if facts.github_url:
        tags.append("has-github")

    tool = Tool(
        name=name[:255],
        slug=(slugify(name) or f"tool-{int(now.timestamp())}")[:255],
        website=website,
        description=description,
        short_description=(facts.meta_description or description)[:200],
        tags=tags,
        track=track,
        last_enriched_at=now,
    )
    if facts.pricing:
        tool.pricing_type = facts.pricing
    if facts.free_tier_available is not None:
        tool.free_tier_available = facts.free_tier_available
        if facts.free_tier_available:
            tool.startup_friendly = True
    if facts.pricing_from is not None:
        try:
            tool.pricing_from = Decimal(str(facts.pricing_from))
        except (InvalidOperation, TypeError, ValueError):
            pass
    if facts.india_focused or raw.get("india_focus"):
        tool.pricing_has_india_plan = bool(
            facts.has_india_pricing or facts.india_focused
        )
    if facts.has_india_pricing:
        tool.gst_applicable = True

    logo = _resolve_logo_url(website, facts)
    if logo:
        tool.logo_url = logo

    tool.save()
    _apply_categories(tool, facts)
    return tool


def run_new_tool_discovery(
    max_new: int | None = MAX_NEW_TOOLS_PER_RUN,
    *,
    candidates: list[dict] | None = None,
) -> dict:
    if candidates is None:
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


def run_india_and_new_discovery(max_new: int | None = 40) -> dict:
    """Firecrawl-only pass: Indian tools + newly launched AI tools."""
    from .india_sources import fetch_firecrawl_candidates
    from .sources import dedupe_candidates

    candidates = dedupe_candidates(fetch_firecrawl_candidates())
    result = run_new_tool_discovery(max_new=max_new, candidates=candidates)
    result["source"] = "firecrawl_india_and_new"
    return result


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

            updates = {
                "description": generated,
                "last_enriched_at": timezone.now(),
            }
            if facts.logo_url and not tool.logo_url:
                updates["logo_url"] = facts.logo_url[:500]
            if facts.pricing and tool.pricing_type == "freemium":
                updates["pricing_type"] = facts.pricing
            Tool.objects.filter(pk=tool.pk).update(**updates)
            if facts.category or facts.categories:
                _apply_categories(tool, facts)
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
