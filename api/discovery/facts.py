"""Best-effort structured facts from a tool URL. Never publish source_text."""

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings

from api.models import Category

from .sources import USER_AGENT, normalize_url

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
GITHUB_REPO_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/]+)/([^/#?]+)", re.IGNORECASE
)
PRICING_RULES = (
    (re.compile(r"\bfreemium\b", re.I), "freemium"),
    (re.compile(r"\bfree\s+trial\b", re.I), "freemium"),
    (re.compile(r"\$\s*\d+", re.I), "paid"),
    (re.compile(r"\bsubscription\b", re.I), "paid"),
    (re.compile(r"\bpricing\b", re.I), "paid"),
    (re.compile(r"\bfree\b", re.I), "free"),
)


@dataclass
class Facts:
    title: str | None = None
    meta_description: str | None = None
    pricing: str | None = None
    category: str | None = None
    stars: int | None = None
    topics: list[str] = field(default_factory=list)
    source_text: str = ""


def parse_github_repo(url: str) -> str | None:
    match = GITHUB_REPO_RE.match(url or "")
    if not match:
        return None
    owner, repo = match.group(1), match.group(2)
    if owner.lower() in {
        "topics",
        "orgs",
        "settings",
        "marketplace",
        "features",
        "explore",
        "sponsors",
        "enterprise",
        "login",
        "signup",
        "pricing",
        "about",
    }:
        return None
    return f"{owner}/{repo.removesuffix('.git')}"


def _github_headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    token = getattr(settings, "GITHUB_TOKEN", "") or ""
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _infer_pricing(text: str) -> str | None:
    if not text:
        return None
    for pattern, value in PRICING_RULES:
        if pattern.search(text):
            return value
    return None


def _infer_category(text: str, topics: list[str] | None = None) -> str | None:
    parts = [text or ""]
    parts.extend(topics or [])
    haystack = " ".join(parts).lower()
    if not haystack.strip():
        return None
    for name, slug in Category.objects.values_list("name", "slug"):
        needles = {name.lower(), slug.lower().replace("-", " "), slug.lower()}
        if any(needle and needle in haystack for needle in needles):
            return name
    return None


def _fetch_github_facts(repo: str) -> Facts:
    try:
        response = requests.get(
            f"https://api.github.com/repos/{repo}",
            headers=_github_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("GitHub repo fetch failed for %s: %s", repo, exc)
        return Facts()

    description = (data.get("description") or "").strip()
    topics = data.get("topics") or []
    combined = " ".join([description, " ".join(topics)])
    return Facts(
        title=data.get("name") or repo,
        meta_description=description or None,
        pricing=_infer_pricing(combined) or "free",
        category=_infer_category(combined, topics),
        stars=data.get("stargazers_count"),
        topics=list(topics),
        source_text=description,
    )


def _fetch_html_facts(url: str) -> Facts:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()
        html = response.text[:80_000]
    except Exception as exc:
        logger.warning("HTML fetch failed for %s: %s", url, exc)
        return Facts()

    soup = BeautifulSoup(html, "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    meta = ""
    for attrs in (
        {"name": "description"},
        {"property": "og:description"},
        {"name": "twitter:description"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            meta = tag["content"].strip()
            break

    visible = " ".join(soup.stripped_strings)[:4000]
    source_text = meta or title
    pricing_haystack = " ".join(filter(None, [meta, title, visible[:1500]]))
    return Facts(
        title=title or None,
        meta_description=meta or None,
        pricing=_infer_pricing(pricing_haystack),
        category=_infer_category(" ".join(filter(None, [title, meta]))),
        source_text=source_text,
    )


def fetch_github_repo_meta(url: str) -> dict:
    """License, last push, open issues, archived flag. Empty dict on failure."""
    repo = parse_github_repo(url)
    if not repo:
        return {}
    try:
        response = requests.get(
            f"https://api.github.com/repos/{repo}",
            headers=_github_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("GitHub repo meta failed for %s: %s", repo, exc)
        return {}

    license_info = data.get("license") or {}
    return {
        "repo": repo,
        "html_url": data.get("html_url") or f"https://github.com/{repo}",
        "license": license_info.get("spdx_id") or license_info.get("name") or "",
        "pushed_at": data.get("pushed_at") or "",
        "open_issues": data.get("open_issues_count"),
        "archived": bool(data.get("archived")),
        "stars": data.get("stargazers_count"),
        "description": (data.get("description") or "").strip(),
        "topics": list(data.get("topics") or []),
    }


def fetch_facts(url: str) -> Facts:
    if not url or not normalize_url(url):
        return Facts()
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or "").lower().removeprefix("www.")
    if host == "github.com":
        repo = parse_github_repo(url)
        if repo:
            return _fetch_github_facts(repo)
    return _fetch_html_facts(url)
