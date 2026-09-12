"""Resolve Product Hunt candidates through conservative Firecrawl web search."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from . import firecrawl
from .india_sources import is_aggregator_host, is_article_path
from .sources import _mentions_ai, canonicalize_http_url, normalize_name, url_host

MIN_CONFIDENCE = 0.94
AMBIGUITY_MARGIN = 0.05
SEARCH_RESULTS_PER_CANDIDATE = 5
GENERIC_NAME_WORDS = {
    "ai",
    "android",
    "app",
    "assistant",
    "for",
    "ios",
    "mcp",
    "platform",
    "software",
    "tool",
}


@dataclass(frozen=True)
class ProductHuntURLResolution:
    url: str
    confidence: float
    query: str
    title: str
    reason: str


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _brand_word(name: str) -> str:
    words = re.findall(r"[a-z0-9]+", normalize_name(name))
    return next(
        (word for word in words if len(word) >= 3 and word not in GENERIC_NAME_WORDS),
        "",
    )


def _url_identity(url: str) -> tuple[set[str], str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower().split("@")[-1].split(":")[0].removeprefix("www.")
    labels = {
        _compact(label)
        for label in host.split(".")[:-1]
        if label not in {"app", "get", "go", "use", "www"}
    }
    identity = _compact(f"{host} {parsed.path}")
    return labels, identity


def _homepage(url: str) -> str:
    parsed = urlparse(url)
    if url_host(url) == "github.com":
        parts = [part for part in parsed.path.split("/") if part][:2]
        path = f"/{'/'.join(parts)}" if len(parts) == 2 else ""
        return parsed._replace(path=path, params="", query="", fragment="").geturl()
    return parsed._replace(path="", params="", query="", fragment="").geturl()


def _score_hit(name: str, hit: dict) -> tuple[float, str]:
    url = canonicalize_http_url(hit.get("url") or "")
    if (
        not url
        or is_aggregator_host(url)
        or is_article_path(url)
        or url_host(url).endswith("producthunt.com")
    ):
        return 0.0, "directory, article, or invalid URL"

    title = hit.get("title") or ""
    description = hit.get("description") or ""
    if not _mentions_ai(f"{name} {title} {description}"):
        return 0.0, "result has no AI-product signal"

    normalized_name = normalize_name(name)
    name_compact = _compact(normalized_name)
    title_compact = _compact(normalize_name(title))
    brand = _brand_word(name)
    labels, url_identity = _url_identity(url)

    if len(name_compact) >= 4 and name_compact in labels:
        return 0.99, "normalized product name matches the domain"
    if (
        len(brand) >= 4
        and brand in labels
        and (title_compact.startswith(brand) or name_compact in title_compact)
    ):
        return 0.97, "brand matches the domain and search title"
    if (
        url_host(url) == "github.com"
        and len(name_compact) >= 5
        and name_compact in url_identity
        and name_compact in title_compact
    ):
        return 0.95, "product name matches the URL and search title"
    return 0.0, "insufficient official-domain evidence"


def resolve_product_hunt_url(
    name: str,
    *,
    summary: str = "",
    search_limit: int = SEARCH_RESULTS_PER_CANDIDATE,
) -> ProductHuntURLResolution | None:
    """Return a unique high-confidence official URL, otherwise None."""
    query = f'"{name.strip()}" AI tool official website'
    if summary:
        context = " ".join(summary.strip().split()[:8])
        if context:
            query = f"{query} {context}"
    hits = firecrawl.search(query, limit=max(1, min(search_limit, 10)))

    ranked: list[tuple[float, str, dict, str]] = []
    seen_hosts: set[str] = set()
    for hit in hits:
        clean = canonicalize_http_url(hit.get("url") or "")
        host = url_host(clean or "")
        if not clean or not host or host in seen_hosts:
            continue
        seen_hosts.add(host)
        confidence, reason = _score_hit(name, hit)
        if confidence:
            ranked.append((confidence, clean, hit, reason))

    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] < MIN_CONFIDENCE:
        return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < AMBIGUITY_MARGIN:
        return None

    confidence, url, hit, reason = ranked[0]
    return ProductHuntURLResolution(
        url=_homepage(url),
        confidence=confidence,
        query=query,
        title=(hit.get("title") or "").strip(),
        reason=reason,
    )
