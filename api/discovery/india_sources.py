"""Firecrawl-backed discovery of Indian and newly launched AI tools.

YC / Wellfound / GoodFirms / Crunchbase are *lead sources*: we scrape them
to find startups, then publish only when we can resolve an official product
homepage. News blogs and SEO listicles are junk and never become Tool rows.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from . import firecrawl
from .sources import normalize_name, normalize_url

logger = logging.getLogger(__name__)

# Geo-targeted searches for Indian AI products founders can actually buy.
INDIA_QUERIES = (
    "Indian AI startups tools for founders site:.in OR INR",
    "YC India AI companies Wellfound Bangalore",
    "Sarvam Krutrim Neysa Indian AI product official site",
    "AI SaaS founded in India pricing",
    "Bangalore AI product launch official website",
)

# Fresh launches worldwide so the directory stays current.
NEW_TOOL_QUERIES = (
    "new AI tools launched this week official site",
    "Product Hunt AI tools launched today",
    "new open source AI tools GitHub",
    "new LLM developer tools 2026",
)

# Startup directories we *want* as discovery leads. Never store these as
# Tool.website, but do scrape them for the company's official site.
_LEAD_HOST_RE = re.compile(
    r"(?:^|\.)(?:"
    r"wellfound\.com|angel\.co|ycombinator\.com|"
    r"goodfirms\.|clutch\.co|crunchbase\.com|"
    r"producthunt\.com|g2\.com|capterra\.|getapp\.|"
    r"topstartups\.io|startupblink\.com|indiaai\.gov\.in"
    r")",
    re.IGNORECASE,
)

# Multi-company list pages on lead hosts (not a single company profile).
_LEAD_LIST_PATH_RE = re.compile(
    r"/(?:companies/industry|startups/l/|artificial-intelligence/"
    r"|companies\?|search|startup/?$|top-startups|"
    r"top-startups/|hq_location)",
    re.IGNORECASE,
)

# News / SEO / job-board junk — never useful as a product or a lead profile.
_JUNK_HOST_RE = re.compile(
    r"(?:^|\.)(?:"
    r"google\.|bing\.|yahoo\.|duckduckgo\.|facebook\.|twitter\.|"
    r"x\.com|linkedin\.|youtube\.|instagram\.|reddit\.|wikipedia\.|"
    r"amazon\.|play\.google|apps\.apple|medium\.com|substack\.com|"
    r"theresanaiforthat\.com|futurepedia\.|"
    r"toolify\.|aitools\.|topai\.tools|techstori|yuverse|"
    r"analyticsindiamag\.|inc42\.|yourstory\.|techcrunch\.|"
    r"forbes\.|ndtv\.|timesofindia\.|economictimes\.|"
    r"geeksforgeeks\.|sutrahr\.|aistartupimpact\.|"
    r"bookface\.ycombinator|grow\.google|bharatsamachar\.|finifi\.io|"
    r"s2sbizsolutions\.|listany\.|"
    r"tracxn\.|pitchbook\.|cbinsights\.|"
    r"indeed\.|naukri\.|glassdoor\.|monster\.|shine\.com|"
    r"wikipedia\.org|wikidata\.|"
    r"blogspot\."
    r")",
    re.IGNORECASE,
)

# Paths that almost always mean "article about tools", not a product.
_ARTICLE_PATH_RE = re.compile(
    r"(?:/(?:blog|blogs|post|posts|article|articles|news|knowledge-base|"
    r"knowledge_base|resources/blog|builders)/)"
    r"|"
    r"(?:/top[-_](?:generative[-_])?ai[-_]companies)"
    r"|"
    r"(?:/top[-_]ai[-_]startup)",
    re.IGNORECASE,
)

# SERP titles that are roundups, not a single product.
_LISTICLE_TITLE_RE = re.compile(
    r"\b(?:top\s+\d+|best\s+\d*|best ai tools|ai tools for|"
    r"tools for (?:indian|small|digital)|latest ai products|"
    r"companies in india|github repositories|"
    r"ai startup(?:s)?(?:\s+in)?(?:\s+india)?|"
    r"startup school|sovereign ai initiative|"
    r"promise of|revolutionizing|"
    r"reviewed|roundup|list of|how to start)\b",
    re.IGNORECASE,
)


def host_of(url: str) -> str:
    host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    return host.removeprefix("www.")


def is_lead_host(url: str) -> bool:
    """YC / Wellfound / GoodFirms / etc. — scrape for official product URL."""
    host = host_of(url or "")
    if not host:
        return False
    return bool(_LEAD_HOST_RE.search(host))


def is_junk_host(url: str) -> bool:
    """News / SEO hosts that should never become Tool.website or leads."""
    host = host_of(url or "")
    if not host:
        return True
    return bool(_JUNK_HOST_RE.search(host))


def is_aggregator_host(url: str) -> bool:
    """True when the URL must not be stored as Tool.website.

    Lead directories (YC, Wellfound) and junk news hosts both fail this —
    only a real product homepage should be saved.
    """
    return is_lead_host(url) or is_junk_host(url)


def is_article_path(url: str) -> bool:
    path = urlparse(url if "://" in (url or "") else f"https://{url or ''}").path or ""
    return bool(_ARTICLE_PATH_RE.search(path))


def is_lead_list_page(url: str) -> bool:
    """Industry/filter list on a lead host (many companies, not one profile)."""
    if not is_lead_host(url or ""):
        return False
    parsed = urlparse(url if "://" in (url or "") else f"https://{url or ''}")
    path = parsed.path or ""
    query = parsed.query or ""
    if _LEAD_LIST_PATH_RE.search(path) or _LEAD_LIST_PATH_RE.search(query):
        return True
    # Bare directory roots / filter hubs are never a single company profile.
    if path in ("", "/"):
        return True
    return False


def looks_like_listicle(title: str, url: str = "") -> bool:
    """True for junk pages that should never become a Tool row.

    Lead-directory *profiles* (e.g. a Wellfound company page) return False
    so we can scrape them for an official website. Lead *list* pages and
    news/SEO junk return True.
    """
    if is_junk_host(url or ""):
        return True
    if is_lead_list_page(url or ""):
        return True
    if is_lead_host(url or ""):
        # Single company profile on YC/Wellfound/GoodFirms — keep as a lead.
        return False
    if is_article_path(url or ""):
        return True
    text = (title or "").strip()
    if not text:
        return True
    if _LISTICLE_TITLE_RE.search(text):
        return True
    # Long SEO titles with year markers are almost always articles.
    if len(text) > 80 and re.search(r"\b20\d{2}\b", text):
        return True
    return False


def website_is_unusable(url: str) -> bool:
    """True when Tool.website still points at a directory/news page."""
    if not (url or "").strip():
        return True
    if is_aggregator_host(url) or is_article_path(url) or is_lead_list_page(url):
        return True
    return False


def _candidate_from_hit(
    hit: dict,
    *,
    source_type: str,
    india_focus: bool,
) -> dict | None:
    url = (hit.get("url") or "").strip()
    title = (hit.get("title") or "").strip()
    if not url or not title or looks_like_listicle(title, url):
        return None
    return {
        "name": title[:255],
        "url": url,
        "sourceType": source_type,
        "rawSignal": {
            "votes": 5 if india_focus else 3,
            "description": hit.get("description") or "",
            "india_focus": india_focus,
            "via": "firecrawl",
            "from_lead_directory": is_lead_host(url),
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
