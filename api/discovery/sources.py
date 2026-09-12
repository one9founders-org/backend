"""Pull and dedupe tool candidates from free public sources."""

import logging
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.db.models import Q

from api.models import Tool

logger = logging.getLogger(__name__)

GITHUB_TOPICS = ("artificial-intelligence", "llm-tools")
AI_KEYWORDS = (
    "ai",
    "artificial intelligence",
    "llm",
    "gpt",
    "machine learning",
    "generative",
    "chatgpt",
    "openai",
    "claude",
    "copilot",
    "agent",
    "langchain",
)
NAME_SUFFIXES = (" ai", " app", " labs", " hq", " io", " inc", " llc")
USER_AGENT = "one9-tool-discovery/1.0"
REQUEST_TIMEOUT = 20
TAAFT_BASE_URL = "https://theresanaiforthat.com"
TAAFT_NEW_URL = f"{TAAFT_BASE_URL}/newly-added/"
TAAFT_MAX_CANDIDATES = 40
PRODUCT_HUNT_API_URL = "https://api.producthunt.com/v2/api/graphql"


def normalize_url(url: str) -> str:
    if not url:
        return ""
    text = url.strip()
    if "://" not in text:
        text = "https://" + text
    parsed = urlparse(text)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parsed.path or "").rstrip("/")
    return f"{host}{path}"


_HOST_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$",
    re.IGNORECASE,
)


def is_http_url(url: str) -> bool:
    """True for a real http(s) URL with a DNS-like host.

    Rejects opaque extract garbage (e.g. Google CAES… tokens) that Firecrawl
    sometimes returns as official_website.
    """
    text = (url or "").strip()
    if not text or len(text) > 500 or any(ch.isspace() for ch in text):
        return False
    if "://" not in text:
        # Allow bare domains like sarvam.ai — not random base64 blobs.
        if "." not in text.split("/")[0]:
            return False
        text = "https://" + text
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.netloc or "").lower().split("@")[-1].split(":")[0]
    host = host.removeprefix("www.")
    if not host or not _HOST_RE.match(host):
        return False
    return True


def canonicalize_http_url(url: str) -> str | None:
    """Return a normalized http(s) URL, or None if unusable."""
    if not is_http_url(url):
        return None
    text = (url or "").strip()
    if "://" not in text:
        text = "https://" + text
    return text


def normalize_name(name: str) -> str:
    text = (name or "").lower().strip()
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    changed = True
    while changed:
        changed = False
        for suffix in NAME_SUFFIXES:
            if text.endswith(suffix) and len(text) > len(suffix) + 2:
                text = text[: -len(suffix)].strip()
                changed = True
    return text


def url_host(url: str) -> str:
    normalized = normalize_url(url)
    return normalized.split("/", 1)[0] if normalized else ""


def candidate_source_url(candidate: dict) -> str:
    return (
        candidate.get("sourceUrl")
        or candidate.get("source_url")
        or candidate.get("url")
        or ""
    ).strip()


def candidate_official_url(candidate: dict) -> str:
    return (
        candidate.get("officialUrl")
        or candidate.get("official_url")
        or candidate.get("url")
        or ""
    ).strip()


def _github_headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    token = getattr(settings, "GITHUB_TOKEN", "") or ""
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_github_candidates(days: int = 14) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    headers = _github_headers()
    if not getattr(settings, "GITHUB_TOKEN", ""):
        logger.warning("GITHUB_TOKEN is unset; GitHub search will be rate-limited")

    candidates = []
    seen_urls = set()
    for topic in GITHUB_TOPICS:
        query = f"topic:{topic} created:>{since}"
        try:
            response = requests.get(
                "https://api.github.com/search/repositories",
                params={"q": query, "sort": "stars", "order": "desc", "per_page": 50},
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            items = response.json().get("items") or []
        except Exception as exc:
            logger.warning("GitHub search failed for topic=%s: %s", topic, exc)
            continue

        for item in items:
            html_url = item.get("html_url") or ""
            key = normalize_url(html_url)
            if not key or key in seen_urls:
                continue
            seen_urls.add(key)
            full_name = (item.get("full_name") or "").strip()
            # Prefer github/owner/repo so open-source bucketing can key off
            # the same prefix as website paths and agent external ids.
            display_name = (
                f"github/{full_name}"
                if full_name and "/" in full_name
                else (item.get("name") or full_name or "")
            )
            candidates.append(
                {
                    "name": display_name,
                    "url": html_url,
                    "sourceType": "github",
                    "rawSignal": {
                        "stars": item.get("stargazers_count") or 0,
                        "description": item.get("description") or "",
                        "full_name": full_name,
                    },
                }
            )
    return candidates


def _mentions_ai(text: str) -> bool:
    haystack = (text or "").lower()
    return bool(re.search(r"\bai\b", haystack)) or any(
        keyword in haystack for keyword in AI_KEYWORDS if keyword != "ai"
    )


def _resolve_product_hunt_redirect(url: str) -> str:
    """Resolve an RSS/API-provided outbound redirect without scraping a PH page."""
    clean = canonicalize_http_url(url)
    if not clean:
        return ""
    parsed = urlparse(clean)
    if parsed.netloc.lower().removeprefix("www.") != "producthunt.com":
        return clean
    if not parsed.path.startswith("/r/p/"):
        return ""
    try:
        response = requests.get(
            clean,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html",
                "Referer": "https://www.producthunt.com/feed",
            },
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except Exception as exc:
        logger.info("Product Hunt outbound redirect could not be resolved: %s", exc)
        return ""
    if response.status_code not in {301, 302, 303, 307, 308}:
        return ""
    target = canonicalize_http_url(response.headers.get("Location") or "")
    if not target or url_host(target).endswith("producthunt.com"):
        return ""
    return target


def _product_hunt_candidate(
    *,
    name: str,
    source_url: str,
    external_id: str,
    summary: str,
    website: str = "",
    published_at: str = "",
    updated_at: str = "",
    author: str = "",
    upvotes: int = 0,
    logo_url: str = "",
) -> dict:
    official = _resolve_product_hunt_redirect(website)
    return {
        "name": name.strip(),
        "url": official,
        "sourceUrl": source_url,
        "officialUrl": official,
        "externalId": external_id,
        "sourceType": "producthunt",
        "rawSignal": {
            "upvotes": upvotes,
            "summary": summary.strip(),
            "published_at": published_at,
            "updated_at": updated_at,
            "author": author,
            "logo_url": logo_url,
            "outbound_url": website,
        },
    }


def fetch_product_hunt_api_candidates(token: str, first: int = 50) -> list[dict]:
    """Use Product Hunt's authorized API when a commercially approved token exists."""
    query = """
    query ProductHuntPosts($first: Int!) {
      posts(first: $first, order: NEWEST) {
        edges {
          node {
            id
            name
            tagline
            description
            url
            website
            votesCount
            createdAt
            thumbnail { url }
          }
        }
      }
    }
    """
    try:
        response = requests.post(
            PRODUCT_HUNT_API_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            json={"query": query, "variables": {"first": max(1, min(first, 100))}},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise ValueError(payload["errors"][0].get("message") or "GraphQL error")
    except Exception as exc:
        logger.warning("Product Hunt API failed: %s", exc)
        return []

    candidates = []
    for edge in ((payload.get("data") or {}).get("posts") or {}).get("edges") or []:
        node = edge.get("node") or {}
        name = node.get("name") or ""
        summary = node.get("description") or node.get("tagline") or ""
        if not name or not _mentions_ai(f"{name} {summary}"):
            continue
        thumbnail = node.get("thumbnail") or {}
        candidates.append(
            _product_hunt_candidate(
                name=name,
                source_url=node.get("url") or "",
                external_id=str(node.get("id") or ""),
                summary=summary,
                website=node.get("website") or "",
                published_at=node.get("createdAt") or "",
                upvotes=int(node.get("votesCount") or 0),
                logo_url=thumbnail.get("url") or "",
            )
        )
    return [candidate for candidate in candidates if candidate_source_url(candidate)]


def fetch_product_hunt_rss_candidates() -> list[dict]:
    try:
        feed = feedparser.parse(
            "https://www.producthunt.com/feed",
            request_headers={"User-Agent": USER_AGENT},
        )
    except Exception as exc:
        logger.warning("Product Hunt RSS failed: %s", exc)
        return []

    candidates = []
    for entry in feed.entries:
        title = entry.get("title") or ""
        content = entry.get("content") or []
        content_html = content[0].get("value", "") if content else ""
        content_soup = BeautifulSoup(content_html, "html.parser")
        paragraphs = content_soup.find_all("p")
        summary = (
            paragraphs[0].get_text(" ", strip=True)
            if paragraphs
            else entry.get("summary") or entry.get("description") or ""
        )
        if not _mentions_ai(f"{title} {summary}"):
            continue
        url = entry.get("link") or ""
        if not url:
            continue
        outbound = ""
        for link in content_soup.select('a[href*="/r/p/"]'):
            outbound = (link.get("href") or "").strip()
            if outbound:
                break
        votes = 0
        for key in ("pheedloop_votes", "votes"):
            if entry.get(key) is not None:
                try:
                    votes = int(entry.get(key))
                except (TypeError, ValueError):
                    votes = 0
        entry_id = entry.get("id") or ""
        external_id = (
            entry_id.rsplit("/", 1)[-1]
            if entry_id
            else urlparse(url).path.rstrip("/").split("/")[-1]
        )
        candidates.append(
            _product_hunt_candidate(
                name=title,
                source_url=url,
                external_id=external_id,
                summary=summary,
                website=outbound,
                published_at=entry.get("published") or "",
                updated_at=entry.get("updated") or "",
                author=(entry.get("author") or "").strip(),
                upvotes=votes,
            )
        )
    return candidates


def fetch_product_hunt_candidates() -> list[dict]:
    token = (getattr(settings, "PRODUCT_HUNT_API_TOKEN", "") or "").strip()
    if token:
        api_candidates = fetch_product_hunt_api_candidates(token)
        if api_candidates:
            return api_candidates
    return fetch_product_hunt_rss_candidates()


@lru_cache(maxsize=8)
def _robots_parser(origin: str) -> RobotFileParser | None:
    robots_url = f"{origin}/robots.txt"
    try:
        response = requests.get(
            robots_url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/plain"},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 404:
            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse([])
            return parser
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Could not verify robots.txt for %s: %s", origin, exc)
        return None
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    return parser


def _robots_allows(url: str) -> bool:
    parsed = urlparse(url)
    parser = _robots_parser(f"{parsed.scheme}://{parsed.netloc}")
    if parser is None:
        return False
    return parser.can_fetch(USER_AGENT, url)


def _taaft_official_url(soup: BeautifulSoup) -> str:
    for link in soup.select('a[href^="http"]'):
        href = (link.get("href") or "").strip()
        host = url_host(href)
        if not host or host.endswith("theresanaiforthat.com"):
            continue
        if host in {
            "facebook.com",
            "instagram.com",
            "linkedin.com",
            "twitter.com",
            "x.com",
            "youtube.com",
        }:
            continue
        rel = {str(value).lower() for value in (link.get("rel") or [])}
        classes = " ".join(link.get("class") or []).lower()
        text = link.get_text(" ", strip=True).lower()
        if "nofollow" in rel or any(
            marker in f"{classes} {text}" for marker in ("visit", "website", "open")
        ):
            return href
    return ""


def fetch_taaft_candidates(limit: int = TAAFT_MAX_CANDIDATES) -> list[dict]:
    """Read public TAAFT pages without login, browser evasion, or blocked APIs."""
    if not _robots_allows(TAAFT_NEW_URL):
        logger.warning(
            "TAAFT discovery skipped because robots.txt disallows %s", TAAFT_NEW_URL
        )
        return []
    try:
        response = requests.get(
            TAAFT_NEW_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("TAAFT listing failed: %s", exc)
        return []

    soup = BeautifulSoup(response.text[:500_000], "html.parser")
    candidates: list[dict] = []
    seen: set[str] = set()
    for link in soup.select('a[href*="/ai/"]'):
        source_url = urljoin(TAAFT_BASE_URL, (link.get("href") or "").strip())
        if not source_url or source_url in seen or not _robots_allows(source_url):
            continue
        seen.add(source_url)
        container = link.find_parent(["li", "article"]) or link.parent or link
        name = (
            container.get("data-name")
            or link.get("data-name")
            or link.get_text(" ", strip=True)
        )
        name = re.sub(r"\s+", " ", name or "").strip()
        if not name:
            name = (
                urlparse(source_url).path.rstrip("/").split("/")[-1].replace("-", " ")
            )
        try:
            detail = requests.get(
                source_url,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
                timeout=REQUEST_TIMEOUT,
            )
            detail.raise_for_status()
        except Exception as exc:
            logger.warning("TAAFT detail failed for %s: %s", source_url, exc)
            continue
        detail_soup = BeautifulSoup(detail.text[:300_000], "html.parser")
        official_url = _taaft_official_url(detail_soup)
        description_tag = detail_soup.select_one(
            'meta[name="description"], meta[property="og:description"]'
        )
        summary = (
            (description_tag.get("content") or "").strip() if description_tag else ""
        )
        candidates.append(
            {
                "name": name[:255],
                "url": official_url,
                "officialUrl": official_url,
                "sourceUrl": source_url,
                "externalId": urlparse(source_url).path.rstrip("/").split("/")[-1],
                "sourceType": "taaft",
                "rawSignal": {"summary": summary[:1000]},
            }
        )
        if len(candidates) >= max(1, limit):
            break
    return candidates


def fetch_hacker_news_candidates(days: int = 14) -> list[dict]:
    since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    try:
        response = requests.get(
            "http://hn.algolia.com/api/v1/search_by_date",
            params={
                "query": "AI tool",
                "tags": "story",
                "numericFilters": f"created_at_i>{since}",
                "hitsPerPage": 50,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        hits = response.json().get("hits") or []
    except Exception as exc:
        logger.warning("Hacker News search failed: %s", exc)
        return []

    candidates = []
    for hit in hits:
        url = hit.get("url") or ""
        title = hit.get("title") or ""
        if not url or not title:
            continue
        candidates.append(
            {
                "name": title,
                "url": url,
                "sourceType": "hackernews",
                "rawSignal": {
                    "points": hit.get("points") or 0,
                    "title": title,
                },
            }
        )
    return candidates


def fetch_all_candidates() -> list[dict]:
    """Cheap public sources by default. Firecrawl only when explicitly enabled."""
    from .firecrawl import firecrawl_discovery_enabled
    from .india_sources import fetch_firecrawl_candidates

    fetchers = [
        fetch_github_candidates,
        fetch_product_hunt_candidates,
        fetch_hacker_news_candidates,
    ]
    if getattr(settings, "TAAFT_DISCOVERY_ENABLED", False):
        fetchers.append(fetch_taaft_candidates)
    if firecrawl_discovery_enabled():
        fetchers.insert(0, fetch_firecrawl_candidates)

    combined = []
    for fetcher in fetchers:
        try:
            combined.extend(fetcher())
        except Exception as exc:
            logger.warning("Discovery source %s failed: %s", fetcher.__name__, exc)
    return combined


def _existing_tools_for_candidates(candidates: list[dict]) -> list[Tool]:
    """Load only tools that could match, never the full 25k table."""
    query = Q()
    hosts = {url_host(candidate_official_url(item)) for item in candidates}
    hosts.discard("")
    for host in hosts:
        query |= Q(website__icontains=host)

    for item in candidates:
        key = normalize_name(item.get("name") or "")
        if len(key) >= 3:
            query |= Q(name__icontains=key)

    if not query:
        return []
    return list(Tool.objects.filter(query).only("id", "name", "website"))


def _matches_existing(candidate: dict, existing: list[Tool]) -> bool:
    cand_url = normalize_url(candidate_official_url(candidate))
    cand_name = normalize_name(candidate.get("name") or "")
    for tool in existing:
        if cand_url and normalize_url(tool.website or "") == cand_url:
            return True
        tool_name = normalize_name(tool.name or "")
        if cand_name and tool_name and cand_name == tool_name:
            return True
    return False


def candidate_signal(candidate: dict) -> int:
    raw = candidate.get("rawSignal") or {}
    for key in ("stars", "points", "upvotes", "votes"):
        value = raw.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def dedupe_candidates(candidates: list[dict]) -> list[dict]:
    existing = _existing_tools_for_candidates(candidates)
    unique: list[dict] = []
    seen_urls: set[str] = set()
    seen_names: set[str] = set()

    ranked = sorted(candidates, key=candidate_signal, reverse=True)
    for candidate in ranked:
        name = (candidate.get("name") or "").strip()
        source_url = candidate_source_url(candidate)
        official_url = candidate_official_url(candidate)
        identity_url = source_url or official_url
        if not name or not identity_url:
            continue
        url_key = normalize_url(identity_url)
        name_key = normalize_name(name)
        if url_key in seen_urls or (name_key and name_key in seen_names):
            continue
        if (candidate.get("sourceType") or "").lower() not in {
            "producthunt",
            "taaft",
        } and _matches_existing(candidate, existing):
            continue
        seen_urls.add(url_key)
        if name_key:
            seen_names.add(name_key)
        unique.append(candidate)
    return unique


def discover_candidates() -> list[dict]:
    return dedupe_candidates(fetch_all_candidates())
