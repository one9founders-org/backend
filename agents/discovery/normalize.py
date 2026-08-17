"""Shared field cleaning for agent import and live scrape."""

import re
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, validate_email
from django.utils.text import slugify

from api.discovery.sources import normalize_name, normalize_url

SKIP_CATEGORIES = {"nsfw"}

SKIP_HOSTS = {
    "aiagentsdirectory.com",
    "aiagentstore.ai",
    "theresanaiforthat.com",
    "futurepedia.io",
    "enterprisedna.co",
    "awesome.re",
}

CATEGORY_ALIASES = {
    "autonomous-agents": "AI Agents Platform",
    "ai-coding-agents": "Coding Agent",
    "coding-agents": "Coding Agent",
    "coding-agent": "Coding Agent",
    "agent-frameworks": "AI Agents Frameworks",
    "ai-agents-frameworks": "AI Agents Frameworks",
    "browser-agents": "Browser Agents",
    "web-ai-agents": "Web AI Agents",
    "voice-agents": "Voice AI Agents",
    "voice-ai-agents": "Voice AI Agents",
    "research-agents": "Research",
    "deep-research-agents": "Research",
    "sales-agents": "Sales",
    "customer-support": "Customer Service",
    "customer-service": "Customer Service",
    "personal-assistant": "Personal Assistant",
    "productivity": "Productivity",
}

CATEGORY_KEYWORDS = (
    ("coding", "Coding Agent"),
    ("swe-agent", "Coding Agent"),
    ("devtools", "Developer Tools"),
    ("developer", "Developer Tools"),
    ("browser", "Browser Agents"),
    ("computer use", "Desktop AI Agents"),
    ("desktop", "Desktop AI Agents"),
    ("voice", "Voice AI Agents"),
    ("speech", "Voice AI Agents"),
    ("sales", "Sales"),
    ("crm", "Sales"),
    ("support", "Customer Service"),
    ("customer service", "Customer Service"),
    ("research", "Research"),
    ("rag", "Research"),
    ("marketing", "Marketing"),
    ("seo", "SEO Agents"),
    ("recruit", "Recruiting"),
    ("security", "AI Security"),
    ("observab", "Observability"),
    ("workflow", "Workflow"),
    ("framework", "AI Agents Frameworks"),
    ("multi-agent", "AI Agents Frameworks"),
    ("orchestrat", "AI Agents Frameworks"),
)

_url_validator = URLValidator()
_FEATURE_SPLIT = re.compile(r"[\n\r]+")


def label_to_slug(label: str) -> str:
    return slugify((label or "").strip())


def safe_int(value, default=0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value, default=0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def safe_str(value, default="") -> str:
    if value is None:
        return default
    return str(value).strip()


def normalize_string_list(value) -> list[str]:
    """Turn pipe-delimited strings, newline lists, or JSON lists into a list."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.extend(normalize_string_list(item))
        return _dedupe_keep_order(items)
    if not isinstance(value, str):
        return []
    text = value.strip()
    if not text:
        return []
    if " || " in text:
        parts = [part.strip() for part in text.split(" || ")]
    elif _FEATURE_SPLIT.search(text):
        parts = [part.strip(" \t-•*,") for part in _FEATURE_SPLIT.split(text)]
    else:
        parts = [text]
    return _dedupe_keep_order([part for part in parts if part])


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def safe_url(value, max_length=500) -> str:
    text = safe_str(value)
    if not text:
        return ""
    if "://" not in text:
        text = "https://" + text
    if len(text) > max_length:
        return ""
    try:
        _url_validator(text)
    except ValidationError:
        return ""
    return text


def safe_email(value) -> str:
    text = safe_str(value)
    if not text:
        return ""
    try:
        validate_email(text)
    except ValidationError:
        return ""
    return text


def host_of(url: str) -> str:
    parsed = urlparse(url if "://" in (url or "") else f"https://{url or ''}")
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def is_skipped_host(url: str) -> bool:
    host = host_of(url)
    return any(
        host == skipped or host.endswith("." + skipped) for skipped in SKIP_HOSTS
    )


def is_github_repo_url(url: str) -> bool:
    parsed = urlparse(url if "://" in (url or "") else f"https://{url or ''}")
    host = (parsed.netloc or "").lower()
    if host not in {"github.com", "www.github.com"}:
        return False
    parts = [part for part in (parsed.path or "").split("/") if part]
    if len(parts) < 2:
        return False
    return parts[0].lower() not in {
        "topics",
        "orgs",
        "settings",
        "marketplace",
        "sponsors",
        "features",
        "collections",
        "about",
        "login",
    }


def github_repo_from_url(url: str) -> str:
    if not is_github_repo_url(url):
        return ""
    parsed = urlparse(url)
    parts = [part for part in (parsed.path or "").split("/") if part]
    return f"{parts[0]}/{parts[1].removesuffix('.git')}"


def canonical_category_label(label: str) -> str:
    raw = safe_str(label)
    if not raw:
        return ""
    alias = CATEGORY_ALIASES.get(label_to_slug(raw))
    return alias or raw


def infer_category(text: str, fallback: str = "AI Agents Platform") -> str:
    haystack = (text or "").lower()
    for needle, label in CATEGORY_KEYWORDS:
        if needle in haystack:
            return label
    return fallback


def map_pricing(value: str) -> str:
    text = safe_str(value).lower()
    if text in {"free", "opensource", "open source", "open-source"}:
        return "Free"
    if text in {"freemium", "free trial", "free-trial"}:
        return "Freemium"
    if text in {"paid", "subscription", "enterprise", "premium"}:
        return "Paid"
    if text in {"free", "freemium", "paid"}:
        return text.title()
    if "free" in text and "premium" in text:
        return "Freemium"
    if "free" in text:
        return "Free"
    if text:
        return "Paid"
    return ""


def map_access(value: str, github_url: str = "") -> str:
    text = safe_str(value).lower()
    if text in {"open source", "open-source", "opensource"}:
        return "Open Source"
    if text in {"closed source", "closed-source", "closedsource"}:
        return "Closed Source"
    if text == "api":
        return "API"
    if github_url:
        return "Open Source"
    return safe_str(value)


def popularity_from(item: dict) -> int:
    explicit = safe_int(item.get("popularityScore") or item.get("popularity_score"))
    if explicit:
        return explicit
    views = safe_int(item.get("views"))
    upvotes = safe_int(item.get("upvotes") or item.get("votes") or item.get("points"))
    stars = safe_int(item.get("stars") or item.get("likes"))
    return views + upvotes * 10 + stars


def unique_slug(base: str, existing: set[str]) -> str:
    slug = (slugify(base) or "agent")[:200]
    if slug not in existing:
        existing.add(slug)
        return slug
    index = 2
    while True:
        candidate = f"{slug[:190]}-{index}"
        if candidate not in existing:
            existing.add(candidate)
            return candidate
        index += 1


def should_skip_category(label: str) -> bool:
    return label_to_slug(label) in SKIP_CATEGORIES


__all__ = [
    "canonical_category_label",
    "github_repo_from_url",
    "host_of",
    "infer_category",
    "is_github_repo_url",
    "is_skipped_host",
    "label_to_slug",
    "map_access",
    "map_pricing",
    "normalize_name",
    "normalize_string_list",
    "normalize_url",
    "popularity_from",
    "safe_bool",
    "safe_email",
    "safe_float",
    "safe_int",
    "safe_str",
    "safe_url",
    "should_skip_category",
    "unique_slug",
]
