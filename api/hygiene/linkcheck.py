"""Check whether a tool's website is still alive, and where it really lands.

Sampling production found ~40% of non-GPT tool URLs were dead, parked, or
truncated. This module produces the evidence to fix or retire them.
"""

import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

from . import LINK_RETRIES, LINK_TIMEOUT
from .classify import host_of

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

OK = "ok"
REDIRECTED = "redirected"
BROKEN = "broken"
UNREACHABLE = "unreachable"
PARKED = "parked"
MALFORMED = "malformed"
UNCHECKED = "unchecked"

LINK_STATUS_CHOICES = [
    (OK, "OK"),
    (REDIRECTED, "Redirected"),
    (BROKEN, "Broken (4xx/5xx)"),
    (UNREACHABLE, "Unreachable (DNS/timeout)"),
    (PARKED, "Parked or payment-walled"),
    (MALFORMED, "Malformed URL"),
    (UNCHECKED, "Not checked"),
]

# 402 in the wild almost always means an expired/parked domain, not a real
# paywall on a marketing site.
PARKED_CODES = frozenset({402, 403, 410})

# Listing URLs that carry no item id are useless -- they resolve to a
# store's front page rather than the tool.
_ID_REQUIRED_HOSTS = {
    "play.google.com": "id",
    "apps.apple.com": None,  # needs a path segment beyond /app
}


@dataclass
class LinkResult:
    status: str = UNCHECKED
    http_code: int | None = None
    final_url: str = ""
    host_changed: bool = False
    detail: str = ""
    flags: list[str] = field(default_factory=list)


def is_malformed(url: str) -> str:
    """Return a reason string when a URL is structurally useless, else ''."""
    if not url or not url.strip():
        return "empty url"
    candidate = url if "://" in url else f"https://{url}"
    parsed = urlparse(candidate)
    if not parsed.netloc:
        return "no host"
    if any(char.isspace() for char in parsed.netloc):
        return "host contains whitespace"
    if "." not in parsed.netloc:
        return "host has no domain suffix"

    host = host_of(url)
    if host in _ID_REQUIRED_HOSTS:
        required = _ID_REQUIRED_HOSTS[host]
        if required and f"{required}=" not in (parsed.query or ""):
            return f"{host} url missing ?{required}= parameter"
        if required is None and parsed.path.strip("/").count("/") < 1:
            return f"{host} url missing app path"
    return ""


def _request(url: str, method: str):
    return requests.request(
        method,
        url,
        timeout=LINK_TIMEOUT,
        allow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
    )


def check_url(url: str) -> LinkResult:
    """Resolve a URL and describe what happened. Never raises."""
    malformed = is_malformed(url)
    if malformed:
        return LinkResult(status=MALFORMED, detail=malformed)

    target = url if "://" in url else f"https://{url}"
    response = None
    last_error = ""

    # HEAD first (cheap); many marketing sites reject it, so fall back to GET.
    for method in ("HEAD", "GET"):
        for attempt in range(LINK_RETRIES + 1):
            try:
                response = _request(target, method)
                break
            except requests.RequestException as exc:
                last_error = type(exc).__name__
                response = None
        if response is not None and response.status_code < 400:
            break

    if response is None:
        return LinkResult(status=UNREACHABLE, detail=last_error or "no response")

    code = response.status_code
    final_url = response.url or target
    host_changed = host_of(final_url) != host_of(target)

    if code in PARKED_CODES:
        status = PARKED
    elif code >= 400:
        status = BROKEN
    elif host_changed:
        status = REDIRECTED
    else:
        status = OK

    return LinkResult(
        status=status,
        http_code=code,
        final_url=final_url,
        host_changed=host_changed,
        detail=f"HTTP {code}",
    )


def check_many(urls: list[str]) -> dict[str, LinkResult]:
    """Sequential by design -- these are third-party sites, so stay polite."""
    results: dict[str, LinkResult] = {}
    for url in urls:
        if url in results:
            continue
        results[url] = check_url(url)
    return results
