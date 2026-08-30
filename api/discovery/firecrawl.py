"""Thin Firecrawl v2 client for tool discovery.

Uses search (geo-targeted for India + fresh launches) and scrape with a
JSON extract schema so we can fill logo, pricing, and categories in one
pass. Soft-fails when FIRECRAWL_API_KEY is unset so the rest of discovery
still runs.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

from .sources import canonicalize_http_url

FIRECRAWL_BASE = "https://api.firecrawl.dev/v2"

REQUEST_TIMEOUT = 45
MAX_RETRIES = 4
# Pause between search queries so we stay under Firecrawl rate limits.
SEARCH_GAP_SECONDS = 2.0
SCRAPE_GAP_SECONDS = 1.5

# Structured fields we ask Firecrawl to pull from a product page.
TOOL_EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "short_description": {"type": "string"},
        "description": {"type": "string"},
        "official_website": {
            "type": "string",
            "description": "Canonical product homepage URL (not a blog or directory).",
        },
        "is_single_product_page": {
            "type": "boolean",
            "description": (
                "True only when this URL is one product's homepage or docs; "
                "false for listicles, directories, news, or multi-company pages."
            ),
        },
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
    "required": ["name", "is_single_product_page"],
}

TOOL_EXTRACT_PROMPT = (
    "Extract product metadata for an AI tools directory aimed at founders. "
    "Set is_single_product_page false when the page lists many companies, "
    "is a blog/news/roundup, a marketplace search result, or a registration agency. "
    "When the page is a YC, Wellfound, GoodFirms, Crunchbase, G2, Product Hunt, "
    "TopStartups, StartupBlink, or IndiaAI.gov company *profile*, set "
    "is_single_product_page true and set official_website to "
    "the company's own product homepage (never the directory URL itself). "
    "When is_single_product_page is true, prefer the official product name, "
    "official_website (canonical homepage), a one-sentence short description, "
    "pricing type, starting USD price if shown, whether a free tier exists, "
    "up to 5 category tags, the best logo/icon URL on the page, and any "
    "public GitHub repo URL. Set india_based_or_focused true when the "
    "company is Indian, founded in India, or clearly targets Indian "
    "founders (INR pricing, GST, India office). "
    "Set has_inr_or_india_pricing true when INR/₹ or India plans appear. "
    "If the page is not a single product/company profile, leave official_website empty."
)


def firecrawl_enabled() -> bool:
    return bool(getattr(settings, "FIRECRAWL_API_KEY", "") or "")


def _headers() -> dict[str, str]:
    key = getattr(settings, "FIRECRAWL_API_KEY", "") or ""
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _post_with_backoff(path: str, body: dict[str, Any]) -> dict[str, Any] | None:
    """POST to Firecrawl; retry on 429/5xx with exponential backoff."""
    url = f"{FIRECRAWL_BASE}{path}"
    delay = 2.0
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                url,
                headers=_headers(),
                json=body,
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = response.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else delay
                except ValueError:
                    wait = delay
                wait = max(wait, delay)
                logger.warning(
                    "Firecrawl %s status %s (attempt %s/%s); sleeping %.1fs",
                    path,
                    response.status_code,
                    attempt + 1,
                    MAX_RETRIES,
                    wait,
                )
                time.sleep(wait)
                delay = min(delay * 2, 60.0)
                continue
            # 4xx (except 429) are not retryable — bad URL / payload.
            if 400 <= response.status_code < 500:
                logger.warning(
                    "Firecrawl %s client error %s: %s",
                    path,
                    response.status_code,
                    (response.text or "")[:200],
                )
                return None
            response.raise_for_status()
            return response.json() or {}
        except requests.RequestException as exc:
            if attempt + 1 >= MAX_RETRIES:
                logger.warning("Firecrawl %s failed: %s", path, exc)
                return None
            logger.warning(
                "Firecrawl %s error (attempt %s/%s): %s; sleeping %.1fs",
                path,
                attempt + 1,
                MAX_RETRIES,
                exc,
                delay,
            )
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
    return None


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

    payload = _post_with_backoff("/search", body)
    # Throttle subsequent searches even on success.
    time.sleep(SEARCH_GAP_SECONDS)
    if not payload:
        logger.warning("Firecrawl search failed for %r", query)
        return []

    data = payload.get("data") or {}
    if isinstance(data, list):
        # Some responses return a flat list of web hits.
        web = data
    else:
        web = data.get("web") or []
    results = []
    for item in web:
        url = canonicalize_http_url(item.get("url") or "")
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
    clean = canonicalize_http_url(url)
    if not clean:
        logger.warning("Firecrawl scrape skipped; invalid URL %r", url)
        return {}

    body = {
        "url": clean,
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
    payload = _post_with_backoff("/scrape", body)
    time.sleep(SCRAPE_GAP_SECONDS)
    if not payload:
        logger.warning("Firecrawl scrape failed for %s", clean)
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
