"""Orchestrate discover -> facts -> generate -> gate -> publish/refresh."""

import hashlib
import json
import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError
from django.db.models import F, Q
from django.utils import timezone
from django.utils.text import slugify

from api.hygiene.logos import resolve_logo
from api.hygiene.track import classify_track
from api.models import (
    Category,
    DiscoveryRun,
    ExternalToolCandidate,
    Tool,
    ToolSource,
)

from . import MAX_FIRECRAWL_TOOLS_PER_RUN, MAX_NEW_TOOLS_PER_RUN, REFRESH_NOOP_RATIO
from .facts import Facts, fetch_facts
from .generate import generate_description
from .india_sources import (
    is_aggregator_host,
    is_article_path,
    is_lead_host,
    looks_like_listicle,
)
from .quality_gate import passes_quality_gate, similarity_ratio
from .sources import (
    candidate_official_url,
    candidate_signal,
    candidate_source_url,
    canonicalize_http_url,
    discover_candidates,
    normalize_url,
    url_host,
)

logger = logging.getLogger(__name__)

# Django URLField defaults to max_length=200.
_URL_MAX = 200
_SHORT_DESC_MAX = 200

SIMILARITY_ONLY_PREFIX = "description too similar to source"
RETRY_INSTRUCTION = (
    "Paraphrase more aggressively, use different sentence structure, "
    "and do not reuse wording from typical marketing or README copy."
)
REVIEW_SOURCES = {"producthunt", "taaft"}


def _source_key(candidate: dict) -> str:
    return (
        (candidate.get("sourceType") or candidate.get("source") or "").strip().lower()
    )


def stage_external_candidate(
    candidate: dict,
) -> tuple[ExternalToolCandidate, bool]:
    """Persist a reviewable source observation without exposing its raw payload."""
    source = _source_key(candidate)
    source_url = candidate_source_url(candidate)
    if source not in REVIEW_SOURCES:
        raise ValueError(f"{source or 'unknown'} is not a review source")
    if not source_url:
        raise ValueError("source URL is required")
    raw_payload = candidate.get("rawSignal") or candidate.get("payload") or {}
    canonical_payload = json.dumps(raw_payload, sort_keys=True, default=str)
    defaults = {
        "external_id": (
            candidate.get("externalId") or candidate.get("external_id") or ""
        )[:255],
        "name": (candidate.get("name") or "")[:255],
        "official_url": candidate_official_url(candidate)[:500],
        "payload": raw_payload,
        "content_hash": hashlib.sha256(canonical_payload.encode()).hexdigest(),
    }
    identity = Q(source_url=source_url)
    if defaults["external_id"]:
        identity |= Q(external_id=defaults["external_id"])
    existing = (
        ExternalToolCandidate.objects.filter(source=source).filter(identity).first()
    )
    if existing:
        changed = False
        for field, value in defaults.items():
            if field == "official_url" and not value and existing.official_url:
                continue
            if getattr(existing, field) != value:
                setattr(existing, field, value)
                changed = True
        if existing.source_url != source_url:
            existing.source_url = source_url
            changed = True
        if existing.status == ExternalToolCandidate.STATUS_ERROR:
            existing.status = ExternalToolCandidate.STATUS_PENDING
            changed = True
        if changed:
            existing.save()
        return existing, False
    return (
        ExternalToolCandidate.objects.create(
            source=source,
            source_url=source_url,
            **defaults,
        ),
        True,
    )


def _attach_source(tool: Tool, candidate: dict) -> ToolSource | None:
    source = _source_key(candidate)
    source_url = candidate_source_url(candidate)
    if not source or not source_url:
        return None
    label = dict(ToolSource._meta.get_field("source").choices).get(source, source)
    reference, _ = ToolSource.objects.update_or_create(
        tool=tool,
        source=source,
        url=source_url,
        defaults={
            "label": label,
            "external_id": (
                candidate.get("externalId") or candidate.get("external_id") or ""
            )[:255],
            "observed_at": timezone.now(),
        },
    )
    return reference


def _existing_tool_for_candidate(candidate: dict) -> Tool | None:
    official = candidate_official_url(candidate)
    if official:
        normalized = normalize_url(official)
        host = url_host(official)
        for tool in Tool.objects.filter(website__icontains=host).only(
            "id", "name", "website"
        ):
            if normalize_url(tool.website or "") == normalized:
                return tool
    name = (candidate.get("name") or "").strip()
    if name:
        return Tool.objects.filter(name__iexact=name).first()
    return None


def approve_external_candidate(candidate: ExternalToolCandidate) -> Tool:
    """Run a reviewed candidate through dedupe and the existing quality gate."""
    payload = {
        "name": candidate.name,
        "url": candidate.official_url,
        "officialUrl": candidate.official_url,
        "sourceUrl": candidate.source_url,
        "externalId": candidate.external_id,
        "sourceType": candidate.source,
        "rawSignal": candidate.payload,
    }
    candidate.status = ExternalToolCandidate.STATUS_APPROVED
    candidate.review_notes = ""
    candidate.save(update_fields=["status", "review_notes", "updated_at"])

    try:
        tool = _existing_tool_for_candidate(payload)
        if tool is None:
            if not candidate.official_url:
                raise ValueError("Resolve an official website before approval")
            result = process_candidate(payload)
            if not result["passed"]:
                raise ValueError("; ".join(result["reasons"]))
            tool = publish_new_tool(result)
        _attach_source(tool, payload)
        candidate.linked_tool = tool
        candidate.status = ExternalToolCandidate.STATUS_PUBLISHED
        candidate.save(update_fields=["linked_tool", "status", "updated_at"])
        return tool
    except Exception as exc:
        candidate.status = ExternalToolCandidate.STATUS_ERROR
        candidate.review_notes = str(exc)
        candidate.save(update_fields=["status", "review_notes", "updated_at"])
        raise


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


def _clip(value: str | None, limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _reject(candidate: dict, name: str, url: str, reasons: list[str], facts=None):
    return {
        "name": name,
        "url": url,
        "candidate": candidate,
        "facts": facts if facts is not None else Facts(),
        "generated": "",
        "passed": False,
        "reasons": reasons,
    }


def _resolve_product_url(serp_url: str, facts: Facts) -> str | None:
    """Pick a real product homepage; None when we only have a listicle URL."""
    official = canonicalize_http_url(facts.official_website or "")
    if official and not is_aggregator_host(official) and not is_article_path(official):
        return official
    github = canonicalize_http_url(facts.github_url or "")
    if github and "github.com" in github.lower() and not is_aggregator_host(github):
        return github
    serp = canonicalize_http_url(serp_url or "")
    if serp and not is_aggregator_host(serp) and not is_article_path(serp):
        return serp
    return None


def process_candidate(candidate: dict) -> dict:
    name = (candidate.get("name") or "").strip()
    url = candidate_official_url(candidate)

    if looks_like_listicle(name, url):
        return _reject(
            candidate, name, url, ["listicle or roundup page, not a product"]
        )

    prefer_fc = (candidate.get("sourceType") or "").startswith("firecrawl")
    # Never `prefer_fc or True` — that burned Firecrawl credits on every
    # GitHub / Product Hunt / HN candidate (JSON extract ≈ 5 credits/page).
    facts = fetch_facts(url, prefer_firecrawl=prefer_fc)

    # Lead directories (YC/Wellfound/GoodFirms): keep the company, but only
    # publish after we resolve their official product homepage.
    if is_lead_host(url):
        official = canonicalize_http_url(facts.official_website or "")
        if not official or is_aggregator_host(official) or is_article_path(official):
            return _reject(
                candidate,
                name,
                url,
                ["lead directory page missing official product website"],
                facts=facts,
            )
        facts = fetch_facts(official, prefer_firecrawl=prefer_fc)
        url = official

    if facts.is_single_product_page is False:
        # Extractor said this is a directory/blog — try official URL once.
        official = canonicalize_http_url(facts.official_website or "")
        if (
            official
            and official.rstrip("/") != url.rstrip("/")
            and not is_aggregator_host(official)
            and not is_article_path(official)
        ):
            facts = fetch_facts(official, prefer_firecrawl=prefer_fc)
            url = official
            if facts.is_single_product_page is False:
                return _reject(
                    candidate,
                    name,
                    url,
                    ["page is not a single product"],
                    facts=facts,
                )
        else:
            return _reject(
                candidate,
                name,
                url,
                ["page is not a single product"],
                facts=facts,
            )

    product_url = _resolve_product_url(url, facts)
    if not product_url:
        return _reject(
            candidate,
            name,
            url,
            ["no official product website found"],
            facts=facts,
        )
    if product_url.rstrip("/") != url.rstrip("/"):
        # Re-fetch facts from the real homepage when SERP pointed elsewhere.
        if is_aggregator_host(url) or is_article_path(url):
            facts = fetch_facts(product_url, prefer_firecrawl=prefer_fc)
        url = product_url

    if is_aggregator_host(url) or is_article_path(url):
        return _reject(
            candidate,
            name,
            url,
            ["website is a directory or article, not a product"],
            facts=facts,
        )

    # Prefer a short extracted product name, but never adopt a name that
    # already exists (listicles often extract "ChatGPT" / "Gemini").
    extracted = (facts.title or "").strip()
    if (
        extracted
        and len(extracted) < len(name)
        and len(extracted) <= 80
        and not looks_like_listicle(extracted, url)
        and not Tool.objects.filter(name__iexact=extracted).exists()
    ):
        name = extracted

    if looks_like_listicle(name, url):
        return _reject(
            candidate,
            name,
            url,
            ["extracted name looks like a listicle title"],
            facts=facts,
        )

    if Tool.objects.filter(name__iexact=name).exists():
        return _reject(
            candidate,
            name,
            url,
            [f"tool named {name!r} already exists"],
            facts=facts,
        )

    if url:
        exact = Tool.objects.filter(website__iexact=url).exists()
        if not exact:
            # Common trailing-slash / http(s) variants.
            trimmed = url.rstrip("/")
            exact = (
                Tool.objects.filter(website__iexact=trimmed).exists()
                or Tool.objects.filter(website__iexact=trimmed + "/").exists()
            )
        if exact:
            return _reject(
                candidate,
                name,
                url,
                ["website already in directory"],
                facts=facts,
            )

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
    # URLField max_length=200 — drop logos that cannot fit.
    candidates = []
    if facts.logo_url:
        candidates.append(facts.logo_url.strip())
    try:
        result = resolve_logo(url, verify=False)
        if result.url:
            candidates.append(result.url.strip())
    except Exception as exc:
        logger.debug("logo resolve failed for %s: %s", url, exc)
    for logo in candidates:
        if logo and len(logo) <= _URL_MAX:
            return logo
    return ""


def publish_new_tool(result: dict) -> Tool:
    name = (result["name"] or "").strip()
    description = result["generated"]
    url = result["url"]
    facts = result["facts"]
    candidate = result.get("candidate") or {}
    raw = candidate.get("rawSignal") or {}
    now = timezone.now()

    if not name:
        raise ValueError("tool name required")
    if Tool.objects.filter(name__iexact=name).exists():
        raise IntegrityError(f"tool named {name!r} already exists")

    # Prefer GitHub repo URL when extract found one — that buckets OSS.
    website = url or ""
    if facts.github_url and "github.com" in facts.github_url.lower():
        if "github.com" in (url or "").lower():
            website = facts.github_url
    website = _clip(website, _URL_MAX)

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

    short = _clip(facts.meta_description or description, _SHORT_DESC_MAX)
    tool = Tool(
        name=name[:255],
        slug=(slugify(name) or f"tool-{int(now.timestamp())}")[:255],
        website=website or None,
        description=description,
        short_description=short,
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
    # Only mark India pricing when the page actually shows INR/India plans.
    # India-focused discovery alone must not invent a local price plan.
    if facts.has_india_pricing:
        tool.pricing_has_india_plan = True
        tool.gst_applicable = True
    elif facts.india_focused:
        tool.gst_applicable = True

    logo = _resolve_logo_url(website, facts)
    if logo:
        tool.logo_url = logo

    tool.save()
    _apply_categories(tool, facts)
    _attach_source(tool, candidate)
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

    published = rejected = errored = staged = candidate_updates = 0
    by_source: dict[str, dict[str, int]] = {}

    def increment(source: str, outcome: str) -> None:
        source_counts = by_source.setdefault(source or "unknown", {})
        source_counts[outcome] = source_counts.get(outcome, 0) + 1

    for candidate in deferred:
        log_run(
            run_type="new",
            tool_name=candidate.get("name") or "",
            url=candidate_source_url(candidate) or candidate_official_url(candidate),
            status="deferred",
            reasons="deferred, over cap",
        )

    for candidate in to_process:
        name = candidate.get("name") or ""
        url = candidate_source_url(candidate) or candidate_official_url(candidate)
        source = _source_key(candidate)
        review_record = None
        try:
            if source in REVIEW_SOURCES:
                review_record, created = stage_external_candidate(candidate)
                can_auto_publish = source in getattr(
                    settings, "EXTERNAL_DISCOVERY_AUTO_PUBLISH_SOURCES", set()
                )
                if not can_auto_publish or not candidate_official_url(candidate):
                    if created:
                        staged += 1
                        increment(source, "staged")
                    else:
                        candidate_updates += 1
                        increment(source, "updated")
                    continue
            result = process_candidate(candidate)
            if result["passed"]:
                try:
                    tool = publish_new_tool(result)
                except IntegrityError as exc:
                    log_run(
                        run_type="new",
                        tool_name=name,
                        url=url,
                        status="rejected",
                        reasons=f"duplicate: {exc}",
                    )
                    rejected += 1
                    increment(source, "rejected")
                    if review_record:
                        review_record.status = ExternalToolCandidate.STATUS_REJECTED
                        review_record.review_notes = f"duplicate: {exc}"
                        review_record.save(
                            update_fields=["status", "review_notes", "updated_at"]
                        )
                    continue
                if review_record:
                    review_record.linked_tool = tool
                    review_record.status = ExternalToolCandidate.STATUS_PUBLISHED
                    review_record.save(
                        update_fields=["linked_tool", "status", "updated_at"]
                    )
                log_run(
                    run_type="new",
                    tool_name=name,
                    url=url,
                    status="published",
                )
                published += 1
                increment(source, "published")
            else:
                log_run(
                    run_type="new",
                    tool_name=name,
                    url=url,
                    status="rejected",
                    reasons="; ".join(result["reasons"]),
                )
                rejected += 1
                increment(source, "rejected")
                if review_record:
                    review_record.status = ExternalToolCandidate.STATUS_REJECTED
                    review_record.review_notes = "; ".join(result["reasons"])
                    review_record.save(
                        update_fields=["status", "review_notes", "updated_at"]
                    )
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
            increment(source, "error")
            if review_record:
                review_record.status = ExternalToolCandidate.STATUS_ERROR
                review_record.review_notes = str(exc)
                review_record.save(
                    update_fields=["status", "review_notes", "updated_at"]
                )

    return {
        "candidates_found": len(candidates),
        "published": published,
        "rejected": rejected,
        "errored": errored,
        "deferred_over_cap": len(deferred),
        "staged": staged,
        "candidate_updates": candidate_updates,
        "by_source": by_source,
    }


def run_india_and_new_discovery(max_new: int | None = None) -> dict:
    """Firecrawl-only pass: Indian tools + newly launched AI tools.

    No-op unless FIRECRAWL_DISCOVERY_ENABLED=true (JSON extract is expensive).
    """
    from .firecrawl import firecrawl_discovery_enabled
    from .india_sources import fetch_firecrawl_candidates
    from .sources import dedupe_candidates

    if max_new is None:
        max_new = MAX_FIRECRAWL_TOOLS_PER_RUN
    if not firecrawl_discovery_enabled():
        return {
            "candidates_found": 0,
            "published": 0,
            "rejected": 0,
            "errored": 0,
            "deferred_over_cap": 0,
            "source": "firecrawl_india_and_new",
            "skipped": "FIRECRAWL_DISCOVERY_ENABLED is not set",
        }

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
            # Cheap HTML / GitHub only — never Firecrawl JSON extract.
            facts = fetch_facts(tool.website, prefer_firecrawl=False)
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
            if facts.logo_url and not tool.logo_url and len(facts.logo_url) <= _URL_MAX:
                updates["logo_url"] = facts.logo_url
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
