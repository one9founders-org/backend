"""Verify a tool against Google via the Programmable Search JSON API.

This is the "recheck it against Google" step: it confirms the tool exists
under the name we list, that the website we point at is the one Google
associates with it, and how large a footprint it has.

Requires GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX. Billing is $5 per
1,000 queries with a 10k/day cap, so callers should batch across days.
"""

import logging
from dataclasses import dataclass, field

import requests
from django.conf import settings

from .classify import host_of

logger = logging.getLogger(__name__)

ENDPOINT = "https://www.googleapis.com/customsearch/v1"
REQUEST_TIMEOUT = 20
RESULTS_PER_QUERY = 10

# Directories we expect a real tool to show up in. Presence is a decent
# proxy for "this is a known product" without paying for a traffic API.
KNOWN_DIRECTORIES = (
    "producthunt.com",
    "g2.com",
    "capterra.com",
    "trustpilot.com",
    "crunchbase.com",
    "github.com",
    "futurepedia.io",
    "theresanaiforthat.com",
)


@dataclass
class SearchEvidence:
    query: str = ""
    ok: bool = False
    total_results: int = 0
    official_site_matched: bool = False
    top_host: str = ""
    directory_hits: list[str] = field(default_factory=list)
    snippets: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    error: str = ""


def is_configured() -> bool:
    return bool(
        getattr(settings, "GOOGLE_SEARCH_API_KEY", "")
        and getattr(settings, "GOOGLE_SEARCH_CX", "")
    )


def _query(term: str) -> dict | None:
    try:
        response = requests.get(
            ENDPOINT,
            params={
                "key": settings.GOOGLE_SEARCH_API_KEY,
                "cx": settings.GOOGLE_SEARCH_CX,
                "q": term,
                "num": RESULTS_PER_QUERY,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.warning("Google search failed for %r: %s", term, exc)
        return None


def verify_tool(name: str, website: str) -> SearchEvidence:
    """Search for a tool and report what Google actually knows about it."""
    if not is_configured():
        return SearchEvidence(error="GOOGLE_SEARCH_API_KEY / GOOGLE_SEARCH_CX not set")

    term = f"{name} AI tool" if website else f"{name} software"
    evidence = SearchEvidence(query=term)

    payload = _query(term)
    if payload is None:
        evidence.error = "request failed"
        return evidence

    items = payload.get("items") or []
    info = payload.get("searchInformation") or {}
    try:
        evidence.total_results = int(info.get("totalResults") or 0)
    except (TypeError, ValueError):
        evidence.total_results = 0

    expected_host = host_of(website)
    directory_hits: set[str] = set()

    for index, item in enumerate(items):
        link = item.get("link") or ""
        item_host = host_of(link)
        if index == 0:
            evidence.top_host = item_host
        if expected_host and item_host == expected_host:
            evidence.official_site_matched = True
        for directory in KNOWN_DIRECTORIES:
            if item_host == directory or item_host.endswith(f".{directory}"):
                directory_hits.add(directory)
        if item.get("snippet"):
            evidence.snippets.append(item["snippet"])
        if item.get("title"):
            evidence.titles.append(item["title"])

    evidence.directory_hits = sorted(directory_hits)
    evidence.ok = bool(items)
    return evidence


def search_footprint_score(evidence: SearchEvidence) -> float:
    """0..1 signal for how established a tool looks on the open web."""
    if not evidence.ok:
        return 0.0
    score = 0.0
    if evidence.official_site_matched:
        score += 0.45
    score += min(len(evidence.directory_hits) / 4.0, 1.0) * 0.35
    # Raw result counts are noisy; compress hard.
    if evidence.total_results >= 1_000_000:
        score += 0.20
    elif evidence.total_results >= 50_000:
        score += 0.13
    elif evidence.total_results >= 1_000:
        score += 0.07
    return round(min(score, 1.0), 4)
