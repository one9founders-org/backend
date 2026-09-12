"""Best-effort structured facts from a tool URL. Never publish source_text."""

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings

from api.models import Category

from .sources import USER_AGENT, canonicalize_http_url

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
MAX_FIRST_PARTY_PAGES = 6
BLOCKED_CRAWL_PATH_PARTS = (
    "/account",
    "/auth",
    "/checkout",
    "/login",
    "/sign-in",
    "/signin",
    "/signup",
)
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
    # Optional enrichments (Firecrawl JSON extract / logos).
    logo_url: str | None = None
    pricing_from: float | None = None
    free_tier_available: bool | None = None
    categories: list[str] = field(default_factory=list)
    github_url: str | None = None
    india_focused: bool = False
    has_india_pricing: bool = False
    official_website: str | None = None
    is_single_product_page: bool | None = None
    evidence_urls: dict[str, str] = field(default_factory=dict)
    field_sources: dict[str, str] = field(default_factory=dict)


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


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _safe_first_party_url(url: str, official_host: str) -> str | None:
    clean = canonicalize_http_url(url)
    if not clean:
        return None
    parsed = urlparse(clean)
    if _host(clean) != official_host or parsed.username or parsed.password:
        return None
    path = parsed.path.lower()
    if any(part in path for part in BLOCKED_CRAWL_PATH_PARTS):
        return None
    if re.search(r"\.(?:pdf|zip|exe|dmg|pkg|csv|json|xml)$", path):
        return None
    return parsed._replace(fragment="").geturl()


def _response_url(response, requested_url: str) -> str:
    final = getattr(response, "url", "")
    return final if isinstance(final, str) and final else requested_url


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
    from .sources import _robots_allows

    if not _robots_allows(url):
        logger.warning("HTML fetch skipped because robots.txt disallows %s", url)
        return Facts()
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

    final_url = _response_url(response, url)
    requested_host = _host(url)
    if not requested_host or _host(final_url) != requested_host:
        logger.warning("HTML fetch left official host: %s -> %s", url, final_url)
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
    pricing = _infer_pricing(pricing_haystack)
    pricing_from = None
    free_tier_available = True if pricing == "free" else None
    evidence_urls = {"homepage": final_url}
    field_sources = {
        "meta_description": final_url,
        "pricing_type": final_url,
        "category": final_url,
    }

    relevant_paths = {
        "pricing": ("pricing", "plans"),
        "features": ("features", "product"),
        "integrations": ("integrations", "apps"),
        "docs": ("docs", "documentation"),
        "security": ("security", "trust"),
        "privacy": ("privacy",),
        "terms": ("terms",),
        "changelog": ("changelog", "releases", "updates"),
    }
    base_host = _host(final_url)
    discovered: dict[str, str] = {}
    for link in soup.select("a[href]"):
        target = _safe_first_party_url(
            urljoin(final_url, (link.get("href") or "").strip()),
            base_host,
        )
        if not target:
            continue
        path = urlparse(target).path.lower().rstrip("/")
        for page_type, markers in relevant_paths.items():
            if page_type not in discovered and any(
                marker in path for marker in markers
            ):
                discovered[page_type] = target

    page_summaries = []
    for page_type, target in list(discovered.items())[:MAX_FIRST_PARTY_PAGES]:
        if not _robots_allows(target):
            continue
        try:
            page_response = requests.get(
                target,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            page_response.raise_for_status()
        except Exception as exc:
            logger.info(
                "Official %s page fetch failed for %s: %s",
                page_type,
                target,
                exc,
            )
            continue
        page_url = _response_url(page_response, target)
        if _host(page_url) != base_host:
            logger.info(
                "Official %s page left first-party host: %s",
                page_type,
                page_url,
            )
            continue
        page_soup = BeautifulSoup(page_response.text[:80_000], "html.parser")
        page_text = " ".join(page_soup.stripped_strings)[:3000]
        evidence_urls[page_type] = page_url
        if page_text:
            page_summaries.append(page_text[:800])
        if page_type == "pricing":
            pricing = _infer_pricing(page_text) or pricing
            amount_match = re.search(
                r"(?:US)?\$\s*(\d+(?:\.\d{1,2})?)", page_text, re.IGNORECASE
            )
            if amount_match:
                try:
                    pricing_from = float(amount_match.group(1))
                except ValueError:
                    pricing_from = None
            lowered = page_text.lower()
            if re.search(r"\bfree (?:plan|tier|forever)\b", lowered):
                free_tier_available = True
            elif pricing == "paid":
                free_tier_available = False
            field_sources["pricing_type"] = page_url
            field_sources["pricing_from_usd"] = page_url
            field_sources["free_tier_available"] = page_url

    return Facts(
        title=title or None,
        meta_description=meta or None,
        pricing=pricing,
        pricing_from=pricing_from,
        free_tier_available=free_tier_available,
        category=_infer_category(" ".join(filter(None, [title, meta]))),
        source_text=" ".join([source_text, *page_summaries])[:3000],
        evidence_urls=evidence_urls,
        field_sources=field_sources,
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


def _facts_from_firecrawl(url: str) -> Facts | None:
    """Prefer Firecrawl when configured; None means fall back."""
    from . import firecrawl

    if not firecrawl.firecrawl_enabled():
        return None
    page = firecrawl.scrape_tool_page(url)
    if not page:
        return None

    extracted = page.get("extracted") or {}
    markdown = page.get("markdown") or ""
    title = (extracted.get("name") or page.get("title") or "").strip() or None
    short = (
        extracted.get("short_description")
        or extracted.get("description")
        or page.get("description")
        or ""
    ).strip()
    pricing_raw = (extracted.get("pricing_type") or "").strip().lower()
    pricing = pricing_raw if pricing_raw in {"free", "freemium", "paid"} else None
    if not pricing:
        pricing = _infer_pricing(" ".join(filter(None, [short, markdown[:2000]])))

    categories = [
        str(c).strip() for c in (extracted.get("categories") or []) if str(c).strip()
    ]
    category = None
    if categories:
        category = _infer_category(" ".join(categories)) or categories[0]
    else:
        category = _infer_category(" ".join(filter(None, [title, short])))

    logo = (
        extracted.get("logo_url") or page.get("og_image") or page.get("favicon") or ""
    ).strip()
    github_url = canonicalize_http_url(extracted.get("github_url") or "")
    official = canonicalize_http_url(extracted.get("official_website") or "")
    single = extracted.get("is_single_product_page")
    if single is not None:
        single = bool(single)
    pricing_from = extracted.get("pricing_from_usd")
    try:
        pricing_from_f = float(pricing_from) if pricing_from is not None else None
    except (TypeError, ValueError):
        pricing_from_f = None

    free_tier = extracted.get("free_tier_available")
    if free_tier is None and pricing == "free":
        free_tier = True

    return Facts(
        title=title,
        meta_description=short[:500] or None,
        pricing=pricing,
        category=category,
        topics=categories,
        source_text=(short or markdown[:1500])[:2000],
        logo_url=logo or None,
        pricing_from=pricing_from_f,
        free_tier_available=bool(free_tier) if free_tier is not None else None,
        categories=categories,
        github_url=github_url,
        india_focused=bool(extracted.get("india_based_or_focused")),
        has_india_pricing=bool(extracted.get("has_inr_or_india_pricing")),
        official_website=official,
        is_single_product_page=single,
    )


def fetch_facts(url: str, *, prefer_firecrawl: bool = False) -> Facts:
    """Best-effort page facts. Firecrawl JSON extract is opt-in only.

    Default path uses the GitHub API or a cheap HTML fetch so GitHub /
    Product Hunt / HN discovery never burns Firecrawl credits.
    """
    clean = canonicalize_http_url(url)
    if not clean:
        return Facts()
    url = clean
    if prefer_firecrawl:
        scraped = _facts_from_firecrawl(url)
        if scraped is not None:
            return scraped
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or "").lower().removeprefix("www.")
    if host == "github.com":
        repo = parse_github_repo(url)
        if repo:
            return _fetch_github_facts(repo)
    return _fetch_html_facts(url)
