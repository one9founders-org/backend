"""Fetch AI agent candidates from public catalogs and APIs."""

import logging
import re
import time
from datetime import datetime, timedelta, timezone

import feedparser
import requests
from django.conf import settings
from django.utils.dateparse import parse_datetime

from agents.discovery import SOURCE_RANK
from agents.discovery.normalize import (
    canonical_category_label,
    infer_category,
    is_github_repo_url,
    is_skipped_host,
    map_access,
    map_pricing,
    normalize_string_list,
    popularity_from,
    safe_bool,
    safe_email,
    safe_int,
    safe_str,
    safe_url,
    should_skip_category,
)

logger = logging.getLogger(__name__)

USER_AGENT = "one9-agent-discovery/1.0 (+https://one9founders.com/agents)"
REQUEST_TIMEOUT = 45
DIRECTORY_AGENTS_URL = "https://aiagentsdirectory.com/api/agents"
DIRECTORY_CATEGORIES_URL = "https://aiagentsdirectory.com/api/categories"
ENTERPRISE_DNA_URL = "https://enterprisedna.co/directories/api/agents.json"
HF_SPACES_URL = "https://huggingface.co/api/spaces"
HN_SEARCH_URL = "http://hn.algolia.com/api/v1/search_by_date"
PRODUCT_HUNT_FEED = "https://www.producthunt.com/feed"
GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"

AWESOME_LISTS = (
    ("e2b-dev", "awesome-ai-agents", "README.md"),
    ("caramaschiHG", "awesome-ai-agents-2026", "README.md"),
    ("kyrolabs", "awesome-agents", "README.md"),
)

GITHUB_QUERIES = (
    "topic:ai-agent stars:>=100 fork:false",
    "topic:autonomous-agents stars:>=50 fork:false",
    "topic:agentic-ai stars:>=50 fork:false",
    "topic:llm-agent stars:>=50 fork:false",
    "topic:multi-agent-system stars:>=80 fork:false",
)

SKIP_SECTION_RE = re.compile(
    r"table of contents|contents|contribut|license|learning resource|"
    r"newsletter|podcast|community|benchmark|leaderboard|timeline|"
    r"foundation model|compar(e|ison)|research paper|\bpapers\b",
    re.I,
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
HEADING_LINK_RE = re.compile(r"^\[([^\]]+)\]\((https?://[^)\s]+)\)$")
LIST_LINK_RE = re.compile(
    r"^[-*]\s+\[([^\]]+)\]\((https?://[^)\s]+)\)(?:\s*[-–—:]\s*(.*))?$"
)
INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
STRIP_MD_RE = re.compile(r"[*`]+")
AGENT_HINT_RE = re.compile(
    r"\b(agent|agentic|autonomous|multi-agent|crewai|autogen|"
    r"langgraph|openhands|devin|operator)\b",
    re.I,
)
SOCIAL_HOSTS = {
    "twitter.com",
    "x.com",
    "linkedin.com",
    "discord.com",
    "discord.gg",
    "youtube.com",
    "youtu.be",
    "instagram.com",
}

_session: requests.Session | None = None


def _session_obj() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
            }
        )
    return _session


def _github_headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    token = getattr(settings, "GITHUB_TOKEN", "") or ""
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_json(url: str, *, params=None, headers=None, timeout=REQUEST_TIMEOUT):
    response = _session_obj().get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _get_text(url: str, *, headers=None, timeout=REQUEST_TIMEOUT) -> str:
    response = _session_obj().get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.text


def _candidate(
    *,
    name: str,
    website: str,
    source: str,
    slug: str = "",
    external_id: str | None = None,
    category_label: str = "",
    industry: str = "",
    access: str = "",
    pricing_model: str = "",
    short_description: str = "",
    long_description: str = "",
    key_features: list[str] | None = None,
    use_cases: list[str] | None = None,
    logo_url: str = "",
    image_url: str = "",
    video_url: str = "",
    popularity_score: int = 0,
    upvotes: int = 0,
    views: int = 0,
    github_url: str = "",
    twitter_url: str = "",
    linkedin_url: str = "",
    discord_url: str = "",
    email: str = "",
    is_featured: bool = False,
    created_at=None,
) -> dict | None:
    name = safe_str(name)
    website = safe_url(website)
    github_url = safe_url(github_url)
    if not name:
        return None
    if source not in {"aiagentsdirectory", "enterprisedna"} and len(name.split()) > 12:
        return None
    if not website and github_url:
        website = github_url
    if not website:
        return None
    if is_skipped_host(website):
        return None
    category_label = canonical_category_label(category_label)
    if should_skip_category(category_label):
        return None
    if not github_url and is_github_repo_url(website):
        github_url = website
    return {
        "name": name[:300],
        "slug": safe_str(slug),
        "external_id": safe_str(external_id) or None,
        "website": website,
        "source": source,
        "source_rank": SOURCE_RANK.get(source, 0),
        "category_label": category_label,
        "industry": safe_str(industry)[:200],
        "access": map_access(access, github_url),
        "pricing_model": map_pricing(pricing_model),
        "short_description": safe_str(short_description),
        "long_description": safe_str(long_description),
        "key_features": key_features or [],
        "use_cases": use_cases or [],
        "logo_url": safe_url(logo_url),
        "image_url": safe_url(image_url),
        "video_url": safe_url(video_url),
        "popularity_score": popularity_score,
        "upvotes": safe_int(upvotes),
        "views": safe_int(views),
        "github_url": github_url,
        "twitter_url": safe_url(twitter_url),
        "linkedin_url": safe_url(linkedin_url),
        "discord_url": safe_url(discord_url),
        "email": safe_email(email),
        "is_featured": bool(is_featured),
        "created_at": created_at,
    }


def fetch_directory_categories() -> list[dict]:
    try:
        payload = _get_json(DIRECTORY_CATEGORIES_URL)
    except Exception as exc:
        logger.warning("Directory categories fetch failed: %s", exc)
        return []
    if not isinstance(payload, list):
        return []
    categories = []
    for item in payload:
        name = safe_str((item or {}).get("name"))
        if not name or should_skip_category(name):
            continue
        categories.append(
            {
                "label": name,
                "agent_count": safe_int(item.get("count")),
            }
        )
    return categories


def fetch_directory_agents(limit: int | None = None) -> list[dict]:
    try:
        payload = _get_json(DIRECTORY_AGENTS_URL, timeout=90)
    except Exception as exc:
        logger.warning("Directory agents fetch failed: %s", exc)
        return []
    if not isinstance(payload, list):
        logger.warning("Directory agents payload was not a list")
        return []

    candidates = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        created = (
            parse_datetime(safe_str(item.get("createdAt")))
            if item.get("createdAt")
            else None
        )
        candidate = _candidate(
            name=item.get("name") or "",
            slug=item.get("slug") or "",
            website=item.get("website") or "",
            source="aiagentsdirectory",
            external_id=item.get("_id") or item.get("id"),
            category_label=item.get("category") or "",
            industry=item.get("industry") or "",
            access=item.get("access") or "",
            pricing_model=item.get("pricingModel") or "",
            short_description=item.get("shortDescription") or "",
            long_description=item.get("longDescription") or "",
            key_features=normalize_string_list(item.get("keyFeatures")),
            use_cases=normalize_string_list(item.get("useCases")),
            logo_url=item.get("logo") or "",
            image_url=item.get("image") or "",
            video_url=item.get("video") or "",
            popularity_score=popularity_from(item),
            upvotes=item.get("upvotes") or 0,
            views=item.get("views") or 0,
            github_url=item.get("githubUrl") or "",
            twitter_url=item.get("twitterUrl") or "",
            linkedin_url=item.get("linkedinUrl") or "",
            discord_url=item.get("discordUrl") or "",
            email=item.get("email") or "",
            is_featured=safe_bool(item.get("featured")),
            created_at=created,
        )
        if candidate:
            candidates.append(candidate)
        if limit and len(candidates) >= limit:
            break
    return candidates


def fetch_enterprisedna_agents(limit: int | None = None) -> list[dict]:
    try:
        payload = _get_json(ENTERPRISE_DNA_URL)
    except Exception as exc:
        logger.warning("Enterprise DNA fetch failed: %s", exc)
        return []
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []

    candidates = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        created = None
        added = safe_str(item.get("addedAt"))
        if added:
            created = parse_datetime(f"{added}T00:00:00Z")
        pricing = item.get("pricingTier") or ""
        access = "Open Source" if "open" in safe_str(pricing).lower() else ""
        candidate = _candidate(
            name=item.get("name") or "",
            slug=item.get("slug") or "",
            website=item.get("officialLink") or "",
            source="enterprisedna",
            external_id=f"edna:{item.get('slug') or ''}" if item.get("slug") else None,
            category_label=item.get("category") or "",
            access=access,
            pricing_model=pricing,
            short_description=item.get("tagline") or "",
            long_description=item.get("description") or "",
            use_cases=list(item.get("useCases") or []),
            logo_url=item.get("screenshotUrl") or "",
            image_url=item.get("screenshotUrl") or "",
            is_featured=safe_bool(item.get("featured")),
            created_at=created,
        )
        if candidate:
            candidates.append(candidate)
        if limit and len(candidates) >= limit:
            break
    return candidates


def _strip_md(text: str) -> str:
    return STRIP_MD_RE.sub("", text or "").strip()


def parse_awesome_markdown(markdown: str, source: str = "awesome") -> list[dict]:
    """Parse GitHub awesome-list markdown into agent candidates."""
    current_section = ""
    skip_section = False
    pending: dict | None = None
    pending_field = ""
    candidates: list[dict] = []

    def flush_pending():
        nonlocal pending, pending_field
        if not pending:
            pending_field = ""
            return
        candidate = _candidate(
            name=pending.get("name") or "",
            website=pending.get("website") or "",
            source=source,
            category_label=pending.get("category") or current_section,
            short_description=pending.get("description") or "",
            long_description=pending.get("description") or "",
            github_url=pending.get("github_url") or "",
            twitter_url=pending.get("twitter_url") or "",
            access="Open Source" if pending.get("github_url") else "",
            pricing_model="Free" if pending.get("github_url") else "",
        )
        if candidate:
            candidates.append(candidate)
        pending = None
        pending_field = ""

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        heading = HEADING_RE.match(line)
        if heading:
            title = _strip_md(heading.group(2)).strip()
            heading_link = HEADING_LINK_RE.match(title)
            if heading_link:
                flush_pending()
                pending = {
                    "name": heading_link.group(1).strip(),
                    "website": heading_link.group(2).strip(),
                    "category": current_section,
                    "description": "",
                    "github_url": "",
                    "twitter_url": "",
                }
                pending_field = ""
                continue
            lower_title = title.lower()
            if lower_title in {"category", "description", "links"}:
                pending_field = lower_title
                continue
            flush_pending()
            current_section = title
            skip_section = bool(SKIP_SECTION_RE.search(title))
            pending_field = ""
            continue

        if skip_section or not line:
            if pending_field == "description" and pending and line:
                pending["description"] = (
                    (pending["description"] + " " + line.lstrip("-* ")).strip()
                    if pending.get("description")
                    else line.lstrip("-* ")
                )
            continue

        if pending and pending_field == "category":
            pending["category"] = _strip_md(line)
            pending_field = ""
            continue
        if pending and pending_field == "description":
            pending["description"] = (
                (pending["description"] + " " + line.lstrip("-* ")).strip()
                if pending.get("description")
                else line.lstrip("-* ")
            )
            continue
        if pending and pending_field == "links":
            for match in INLINE_LINK_RE.finditer(line):
                url = match.group(2)
                if is_github_repo_url(url):
                    pending["github_url"] = url
                if "twitter.com" in url or "x.com" in url:
                    pending["twitter_url"] = url
            continue

        list_match = LIST_LINK_RE.match(line)
        if list_match:
            flush_pending()
            name = list_match.group(1)
            url = list_match.group(2)
            desc = list_match.group(3) or ""
            if any(host in url for host in SOCIAL_HOSTS) and not is_github_repo_url(
                url
            ):
                continue
            pending = {
                "name": name.strip(),
                "website": url.strip(),
                "category": current_section,
                "description": _strip_md(desc),
                "github_url": url if is_github_repo_url(url) else "",
                "twitter_url": "",
            }
            pending_field = ""

    flush_pending()
    return candidates


def fetch_awesome_list_agents(limit: int | None = None) -> list[dict]:
    candidates: list[dict] = []
    for owner, repo, path in AWESOME_LISTS:
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/{path}"
        try:
            markdown = _get_text(url, timeout=30)
        except Exception:
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/master/{path}"
            try:
                markdown = _get_text(url, timeout=30)
            except Exception as exc:
                logger.warning("Awesome list %s/%s failed: %s", owner, repo, exc)
                continue
        parsed = parse_awesome_markdown(markdown, source="awesome")
        candidates.extend(parsed)
        if limit and len(candidates) >= limit:
            return candidates[:limit]
    return candidates


def fetch_github_agents(limit: int | None = None) -> list[dict]:
    if not getattr(settings, "GITHUB_TOKEN", ""):
        logger.warning("GITHUB_TOKEN is unset; GitHub search will be rate-limited")

    candidates: list[dict] = []
    seen_repos: set[str] = set()
    headers = _github_headers()
    per_page = 100
    for query in GITHUB_QUERIES:
        try:
            payload = _get_json(
                GITHUB_SEARCH_URL,
                params={
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": per_page,
                },
                headers=headers,
            )
        except Exception as exc:
            logger.warning("GitHub search failed for %s: %s", query, exc)
            continue
        for item in payload.get("items") or []:
            full_name = safe_str(item.get("full_name"))
            if not full_name or full_name.lower() in seen_repos:
                continue
            if item.get("fork"):
                continue
            seen_repos.add(full_name.lower())
            html_url = item.get("html_url") or ""
            homepage = safe_url(item.get("homepage") or "")
            description = safe_str(item.get("description"))
            topics = " ".join(item.get("topics") or [])
            created = parse_datetime(item.get("created_at") or "")
            candidate = _candidate(
                name=item.get("name") or full_name,
                website=homepage or html_url,
                source="github",
                external_id=f"github:{full_name}",
                category_label=infer_category(f"{description} {topics}"),
                short_description=description,
                long_description=description,
                github_url=html_url,
                access="Open Source",
                pricing_model="Free",
                popularity_score=safe_int(item.get("stargazers_count")),
                upvotes=safe_int(item.get("stargazers_count")),
                created_at=created,
            )
            if candidate:
                candidates.append(candidate)
            if limit and len(candidates) >= limit:
                return candidates
        time.sleep(0.4)
    return candidates


def fetch_huggingface_agents(limit: int | None = None) -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()
    page_size = 100
    start = 0
    max_pages = 3
    for _ in range(max_pages):
        try:
            payload = _get_json(
                HF_SPACES_URL,
                params={
                    "search": "agent",
                    "sort": "likes",
                    "direction": -1,
                    "limit": page_size,
                    "skip": start,
                },
            )
        except Exception as exc:
            logger.warning("Hugging Face spaces fetch failed: %s", exc)
            break
        if not isinstance(payload, list) or not payload:
            break
        for item in payload:
            space_id = safe_str(item.get("id") or item.get("name"))
            if not space_id or space_id.lower() in seen:
                continue
            likes = safe_int(item.get("likes"))
            if likes < 10:
                continue
            haystack = f"{space_id} {item.get('cardData') or ''}"
            if not AGENT_HINT_RE.search(haystack):
                continue
            seen.add(space_id.lower())
            url = f"https://huggingface.co/spaces/{space_id}"
            name = space_id.split("/")[-1].replace("-", " ").replace("_", " ")
            candidate = _candidate(
                name=name,
                website=url,
                source="huggingface",
                external_id=f"hf:{space_id}",
                category_label="AI Agents Platform",
                short_description=safe_str(
                    (item.get("cardData") or {}).get("title")
                    if isinstance(item.get("cardData"), dict)
                    else ""
                )
                or f"Hugging Face Space for {name}",
                access="Open Source",
                pricing_model="Free",
                popularity_score=likes,
                upvotes=likes,
            )
            if candidate:
                candidates.append(candidate)
            if limit and len(candidates) >= limit:
                return candidates
        if len(payload) < page_size:
            break
        start += page_size
        time.sleep(0.3)
    return candidates


def _mentions_agent(text: str) -> bool:
    return bool(AGENT_HINT_RE.search(text or ""))


def _product_name_from_title(title: str) -> str:
    text = safe_str(title)
    lowered = text.lower()
    for prefix in ("show hn:", "show hn -", "launch hn:"):
        if lowered.startswith(prefix):
            text = text[len(prefix) :].strip()
            lowered = text.lower()
            break
    if not text or text.endswith("?") or len(text.split()) > 12:
        return ""
    if lowered.startswith(("ask hn", "tell hn", "who is hiring")):
        return ""
    return text.split("—")[0].split(":")[0].strip()


def fetch_product_hunt_agents(limit: int | None = None) -> list[dict]:
    try:
        feed = feedparser.parse(
            PRODUCT_HUNT_FEED, request_headers={"User-Agent": USER_AGENT}
        )
    except Exception as exc:
        logger.warning("Product Hunt RSS failed: %s", exc)
        return []
    candidates = []
    for entry in feed.entries:
        title = entry.get("title") or ""
        summary = entry.get("summary") or entry.get("description") or ""
        if not _mentions_agent(f"{title} {summary}"):
            continue
        url = entry.get("link") or ""
        name = _product_name_from_title(title)
        if not name:
            continue
        candidate = _candidate(
            name=name,
            website=url,
            source="producthunt",
            short_description=re.sub("<[^<]+?>", "", summary)[:500],
            category_label=infer_category(f"{title} {summary}"),
        )
        if candidate:
            candidates.append(candidate)
        if limit and len(candidates) >= limit:
            break
    return candidates


def fetch_hacker_news_agents(limit: int | None = None) -> list[dict]:
    since = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
    try:
        payload = _get_json(
            HN_SEARCH_URL,
            params={
                "query": "AI agent",
                "tags": "story",
                "numericFilters": f"created_at_i>{since}",
                "hitsPerPage": 50,
            },
        )
    except Exception as exc:
        logger.warning("Hacker News search failed: %s", exc)
        return []
    candidates = []
    for hit in payload.get("hits") or []:
        url = hit.get("url") or ""
        title = hit.get("title") or ""
        if not url or not title or not _mentions_agent(title):
            continue
        name = _product_name_from_title(title)
        if not name:
            continue
        created = None
        if hit.get("created_at"):
            created = parse_datetime(hit["created_at"])
        candidate = _candidate(
            name=name,
            website=url,
            source="hackernews",
            short_description=title,
            category_label=infer_category(title),
            popularity_score=safe_int(hit.get("points")),
            upvotes=safe_int(hit.get("points")),
            created_at=created,
        )
        if candidate:
            candidates.append(candidate)
        if limit and len(candidates) >= limit:
            break
    return candidates


SOURCE_FETCHERS = {
    "aiagentsdirectory": fetch_directory_agents,
    "enterprisedna": fetch_enterprisedna_agents,
    "awesome": fetch_awesome_list_agents,
    "github": fetch_github_agents,
    "huggingface": fetch_huggingface_agents,
    "producthunt": fetch_product_hunt_agents,
    "hackernews": fetch_hacker_news_agents,
}


def fetch_source(source: str, limit: int | None = None) -> list[dict]:
    fetcher = SOURCE_FETCHERS.get(source)
    if not fetcher:
        raise ValueError(f"Unknown source: {source}")
    return fetcher(limit=limit)


def fetch_all_sources(
    sources: tuple[str, ...] | list[str], limit: int | None = None
) -> dict[str, list[dict]]:
    results: dict[str, list[dict]] = {}
    for source in sources:
        try:
            results[source] = fetch_source(source, limit=limit)
        except Exception as exc:
            logger.warning("Source %s failed: %s", source, exc)
            results[source] = []
    return results
