"""Pull and dedupe tool candidates from free public sources."""

import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import feedparser
import requests
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
            candidates.append(
                {
                    "name": item.get("name") or item.get("full_name") or "",
                    "url": html_url,
                    "sourceType": "github",
                    "rawSignal": {
                        "stars": item.get("stargazers_count") or 0,
                        "description": item.get("description") or "",
                        "full_name": item.get("full_name") or "",
                    },
                }
            )
    return candidates


def _mentions_ai(text: str) -> bool:
    haystack = (text or "").lower()
    return any(keyword in haystack for keyword in AI_KEYWORDS)


def fetch_product_hunt_candidates() -> list[dict]:
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
        summary = entry.get("summary") or entry.get("description") or ""
        if not _mentions_ai(f"{title} {summary}"):
            continue
        url = entry.get("link") or ""
        if not url:
            continue
        votes = 0
        for key in ("pheedloop_votes", "votes"):
            if entry.get(key) is not None:
                try:
                    votes = int(entry.get(key))
                except (TypeError, ValueError):
                    votes = 0
        candidates.append(
            {
                "name": title.split("—")[0].split("-")[0].strip() or title,
                "url": url,
                "sourceType": "producthunt",
                "rawSignal": {"upvotes": votes, "title": title, "summary": summary},
            }
        )
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
    combined = []
    for fetcher in (
        fetch_github_candidates,
        fetch_product_hunt_candidates,
        fetch_hacker_news_candidates,
    ):
        try:
            combined.extend(fetcher())
        except Exception as exc:
            logger.warning("Discovery source %s failed: %s", fetcher.__name__, exc)
    return combined


def _existing_tools_for_candidates(candidates: list[dict]) -> list[Tool]:
    """Load only tools that could match, never the full 25k table."""
    query = Q()
    hosts = {url_host(item.get("url") or "") for item in candidates}
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
    cand_url = normalize_url(candidate.get("url") or "")
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
        url = (candidate.get("url") or "").strip()
        if not name or not url:
            continue
        url_key = normalize_url(url)
        name_key = normalize_name(name)
        if url_key in seen_urls or (name_key and name_key in seen_names):
            continue
        if _matches_existing(candidate, existing):
            continue
        seen_urls.add(url_key)
        if name_key:
            seen_names.add(name_key)
        unique.append(candidate)
    return unique


def discover_candidates() -> list[dict]:
    return dedupe_candidates(fetch_all_candidates())
