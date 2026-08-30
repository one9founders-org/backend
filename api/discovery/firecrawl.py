"""Thin Firecrawl v2 client for tool discovery.

Uses search (geo-targeted for India + fresh launches) and scrape with a
JSON extract schema so we can fill logo, pricing, and categories in one
pass. Soft-fails when FIRECRAWL_API_KEY is unset so the rest of discovery
still runs.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

FIRECRAWL_BASE = "https://api.firecrawl.dev/v2"
REQUEST_TIMEOUT = 45

# Structured fields we ask Firecrawl to pull from a product page.
TOOL_EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "short_description": {"type": "string"},
        "description": {"type": "string"},
        "pricing_type": {
            "type": "string",
            "enum": ["free", "freemium", "paid", "unknown"],
        },
        "pricing_from_usd": {"type": ["number", "null"]},
        "free_tier_available": {"type": "boolean"},
        "categories": {"type": "array", "items": {"type": "string"}},
        "logo_url": {"type": "string"},
        "github_url": {"type": "string"},
        "india_based_or_focused": {"type": "boolean"},
        "has_inr_or_india_pricing": {"type": "boolean"},
    },
    "required": ["name"],
}

TOOL_EXTRACT_PROMPT = (
    "Extract product metadata for an AI tools directory aimed at founders. "
    "Prefer the official product name, a one-sentence short description, "
    "pricing type, starting USD price if shown, whether a free tier exists, "
    "up to 5 category tags, the best logo/icon URL on the page, and any "
    "public GitHub repo URL. Set india_based_or_focused true when the "
    "company is Indian, founded in India, or clearly targets Indian "
    "founders (INR pricing, GST, India office). "
    "Set has_inr_or_india_pricing true when INR/₹ or India plans appear."
)


def firecrawl_enabled() -> bool:
    return bool(getattr(settings, "FIRECRAWL_API_KEY", "") or "")


def _headers() -> dict[str, str]:
    key = getattr(settings, "FIRECRAWL_API_KEY", "") or ""
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def search(
    query: str,
    *,
    limit: int = 10,
    country: str | None = None,
    location: str | None = None,
) -> list[dict]:
    """Return web search hits: {url, title, description}."""
    if not firecrawl_enabled():
        logger.info("FIRECRAWL_API_KEY unset; skipping search for %r", query)
        return []

    body: dict[str, Any] = {"query": query, "limit": limit}
    if country:
        body["country"] = country
    if location:
        body["location"] = location

    try:
        response = requests.post(
            f"{FIRECRAWL_BASE}/search",
            headers=_headers(),
            json=body,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json() or {}
    except Exception as exc:
        logger.warning("Firecrawl search failed for %r: %s", query, exc)
        return []

    data = payload.get("data") or {}
    if isinstance(data, list):
        # Some responses return a flat list of web hits.
        web = data
    else:
        web = data.get("web") or []
    results = []
    for item in web:
        url = (item.get("url") or "").strip()
        title = (item.get("title") or "").strip()
        if not url or not title:
            continue
        results.append(
            {
                "url": url,
                "title": title,
                "description": (item.get("description") or "").strip(),
            }
        )
    return results


def scrape_tool_page(url: str) -> dict[str, Any]:
    """Scrape one URL; return markdown + json extract (+ metadata)."""
    if not firecrawl_enabled():
        return {}
    if not url:
        return {}

    body = {
        "url": url,
        "onlyMainContent": True,
        "formats": [
            "markdown",
            {
                "type": "json",
                "prompt": TOOL_EXTRACT_PROMPT,
                "schema": TOOL_EXTRACT_SCHEMA,
            },
        ],
    }
    try:
        response = requests.post(
            f"{FIRECRAWL_BASE}/scrape",
            headers=_headers(),
            json=body,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json() or {}
    except Exception as exc:
        logger.warning("Firecrawl scrape failed for %s: %s", url, exc)
        return {}

    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return {}
    extracted = data.get("json") or {}
    if not isinstance(extracted, dict):
        extracted = {}
    metadata = data.get("metadata") or {}
    return {
        "markdown": (data.get("markdown") or "")[:8000],
        "extracted": extracted,
        "metadata": metadata if isinstance(metadata, dict) else {},
        "og_image": (metadata.get("ogImage") or metadata.get("og:image") or ""),
        "favicon": (metadata.get("favicon") or ""),
        "title": (metadata.get("title") or extracted.get("name") or ""),
        "description": (
            metadata.get("description")
            or extracted.get("short_description")
            or extracted.get("description")
            or ""
        ),
    }
