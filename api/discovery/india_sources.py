"""Firecrawl-backed discovery of Indian and newly launched AI tools."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from . import firecrawl
from .sources import normalize_name, normalize_url

logger = logging.getLogger(__name__)

# Geo-targeted searches for Indian AI products founders can actually buy.
INDIA_QUERIES = (
    "Indian AI startups tools for founders",
    "best AI SaaS tools India INR pricing",
    "AI tools for Indian startups GST",
    "India founded generative AI product",
    "Bangalore AI startup product launch",
)

# Fresh launches worldwide so the directory stays current.
NEW_TOOL_QUERIES = (
    "new AI tools launched this week",
    "Product Hunt AI tools launched today",
    "new open source AI tools GitHub",
    "new LLM developer tools 2026",
)

# Directory/listicle hosts — we want the product site, not the roundup.
_SKIP_HOST_RE = re.compile(
    r"(?:google\.|bing\.|yahoo\.|duckduckgo\.|facebook\.|twitter\.|"
    r"x\.com|linkedin\.|youtube\.|instagram\.|reddit\.|wikipedia\.|"
    r"amazon\.|play\.google|apps\.apple|"
    r"producthunt\.com|theresanaiforthat\.com|futurepedia\.|"
    r"toolify\.|aitools\.|topai\.tools)",
    re.IGNORECASE,
)


def _is_skippable_host(url: str) -> bool:
    host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    host = host.removeprefix("www.")
    if not host:
        return True
    return bool(_SKIP_HOST_RE.search(host))


def _candidate_from_hit(
    hit: dict,
    *,
    source_type: str,
    india_focus: bool,
) -> dict | None:
    url = (hit.get("url") or "").strip()
    title = (hit.get("title") or "").strip()
    if not url or not title or _is_skippable_host(url):
        return None
    # Drop github path-less or non-repo noise later; keep real repos.
    return {
        "name": title[:255],
        "url": url,
        "sourceType": source_type,
        "rawSignal": {
            "votes": 5 if india_focus else 3,
            "description": hit.get("description") or "",
            "india_focus": india_focus,
            "via": "firecrawl",
        },
    }


def fetch_india_tool_candidates(limit_per_query: int = 8) -> list[dict]:
    """Search Indian AI tools via Firecrawl (country=IN)."""
    if not firecrawl.firecrawl_enabled():
        return []

    candidates: list[dict] = []
    seen: set[str] = set()
    for query in INDIA_QUERIES:
        hits = firecrawl.search(
            query,
            limit=limit_per_query,
            country="IN",
            location="India",
        )
        for hit in hits:
            cand = _candidate_from_hit(
                hit, source_type="firecrawl_india", india_focus=True
            )
            if not cand:
                continue
            key = normalize_url(cand["url"])
            if key in seen:
                continue
            seen.add(key)
            candidates.append(cand)
    logger.info("Firecrawl India search yielded %s candidates", len(candidates))
    return candidates


def fetch_new_tool_candidates(limit_per_query: int = 8) -> list[dict]:
    """Search newly launched AI tools via Firecrawl."""
    if not firecrawl.firecrawl_enabled():
        return []

    candidates: list[dict] = []
    seen: set[str] = set()
    for query in NEW_TOOL_QUERIES:
        hits = firecrawl.search(query, limit=limit_per_query)
        for hit in hits:
            cand = _candidate_from_hit(
                hit, source_type="firecrawl_new", india_focus=False
            )
            if not cand:
                continue
            key = normalize_url(cand["url"])
            if key in seen:
                continue
            seen.add(key)
            candidates.append(cand)
    logger.info("Firecrawl new-tools search yielded %s candidates", len(candidates))
    return candidates


def fetch_firecrawl_candidates() -> list[dict]:
    combined = []
    for fetcher in (fetch_india_tool_candidates, fetch_new_tool_candidates):
        try:
            combined.extend(fetcher())
        except Exception as exc:
            logger.warning("Firecrawl source %s failed: %s", fetcher.__name__, exc)
    # Prefer shorter product names over long SERP titles when possible.
    for item in combined:
        name = normalize_name(item.get("name") or "")
        # Keep display name as title; pipeline may replace from extract.
        item.setdefault("rawSignal", {})["normalized"] = name
    return combined
