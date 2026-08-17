"""Collect citable pages for the assessment pass.

The scorer in assess.py is only as honest as this dict. Every value is a
page (or a recorded absence) with a URL the model is allowed to cite.
No URL, no score — that rule is enforced downstream, so this module's job
is to actually fetch the pages rather than inventing them.

Caps exist so a 10k-row run cannot explode token cost or wall-clock:
at most six body fetches per tool, 8s each, ~2,500 characters of visible
text. Negative results are cached: a 404 on /security is itself evidence
and must not be retried for the rest of the process.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from api.discovery.facts import fetch_github_repo_meta, parse_github_repo

from . import (
    EVIDENCE_HTML_LIMIT,
    EVIDENCE_MAX_FETCHES,
    EVIDENCE_TEXT_LIMIT,
    EVIDENCE_TIMEOUT,
)
from .classify import host_of
from .linkcheck import OK, REDIRECTED, USER_AGENT, check_url
from .track import OPEN_SOURCE, is_code_host

logger = logging.getLogger(__name__)

# Tried in round-robin: first path of each group, then seconds, so one
# failed privacy URL does not spend the whole budget before pricing.
PATH_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "security_privacy",
        (
            "/privacy",
            "/privacy-policy",
            "/security",
            "/trust",
            "/legal",
            "/dpa",
        ),
    ),
    ("pricing_value", ("/pricing", "/plans")),
    ("integrations", ("/integrations", "/apps", "/marketplace")),
    ("support", ("/support", "/contact", "/help", "/docs")),
    ("update_frequency", ("/changelog", "/releases", "/whats-new")),
    ("functionality", ("/features", "/product")),
    ("startup_friendliness", ("/startups", "/students")),
)

_PAGE_CACHE: dict[str, dict] = {}


def clear_evidence_cache() -> None:
    _PAGE_CACHE.clear()


def _visible_text(html: str, limit: int = EVIDENCE_TEXT_LIMIT) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    return " ".join(soup.stripped_strings)[:limit]


def _origin(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc
    return f"{scheme}://{netloc}" if netloc else ""


def fetch_page(url: str) -> dict:
    """GET one URL. Never raises. Cached for the life of the process."""
    cached = _PAGE_CACHE.get(url)
    if cached is not None:
        return cached

    try:
        response = requests.get(
            url,
            timeout=EVIDENCE_TIMEOUT,
            allow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            },
        )
        status = response.status_code
        final_url = response.url or url
        html = response.text[:EVIDENCE_HTML_LIMIT]
    except requests.RequestException as exc:
        result = {
            "url": url,
            "text": f"Fetch failed: {type(exc).__name__}. Not evidence of absence.",
            "http_status": None,
            "present": False,
            "https": urlparse(url).scheme == "https",
            "absence": False,
        }
        _PAGE_CACHE[url] = result
        return result

    https = urlparse(final_url).scheme == "https"
    if status == 403:
        text = (
            "HTTP 403: the page may exist but blocked this fetch. "
            "Not evidence of absence."
        )
        present, absence = False, False
    elif 200 <= status < 400:
        text = _visible_text(html)
        present, absence = True, False
    elif status in {404, 410}:
        text = f"HTTP {status}: no published page at this path."
        present, absence = False, True
    else:
        text = f"HTTP {status}: page not usable as evidence."
        present, absence = False, False

    result = {
        "url": final_url,
        "text": text,
        "http_status": status,
        "present": present,
        "https": https,
        "absence": absence,
    }
    _PAGE_CACHE[url] = result
    if final_url != url:
        _PAGE_CACHE[final_url] = result
    return result


def _transport_item(final_url: str, http_code: int | None, reachable: bool) -> dict:
    parsed = urlparse(final_url if "://" in final_url else f"https://{final_url}")
    https = parsed.scheme == "https"
    if not reachable:
        text = "Could not resolve the website. HTTPS unknown."
    elif https:
        text = (
            "Final URL uses HTTPS. Encryption in transit is advertised by "
            "the scheme; this is not a test of the server's TLS configuration."
        )
    else:
        text = "Final URL is not served over HTTPS."
    return {
        "url": final_url,
        "text": text,
        "http_status": http_code,
        "present": reachable,
        "https": https,
        "absence": False,
    }


def collect_github_evidence(website: str) -> dict:
    """One GitHub API call instead of marketing-page fetches."""
    meta = fetch_github_repo_meta(website)
    if not meta:
        return {}
    url = meta["html_url"]
    text = (
        f"license={meta['license'] or 'none'}; "
        f"last_push={meta['pushed_at'] or 'unknown'}; "
        f"open_issues={meta['open_issues']}; "
        f"archived={meta['archived']}; "
        f"stars={meta['stars']}; "
        f"description={(meta['description'] or '')[:500]}"
    )
    if meta.get("topics"):
        text += f"; topics={', '.join(meta['topics'][:12])}"
    item = {
        "url": url,
        "text": text,
        "http_status": 200,
        "present": True,
        "https": True,
        "absence": False,
    }
    return {
        "transport": _transport_item(url, 200, True),
        "github": item,
    }


def _path_queue() -> list[str]:
    paths = ["/"]
    depth = max(len(group) for _cid, group in PATH_GROUPS)
    for index in range(depth):
        for _cid, group in PATH_GROUPS:
            if index < len(group):
                paths.append(group[index])
    return paths


def collect_html_evidence(website: str) -> dict:
    link = check_url(website)
    final_url = link.final_url or (
        website if "://" in (website or "") else f"https://{website}"
    )
    reachable = link.status in {OK, REDIRECTED}
    evidence = {
        "transport": _transport_item(final_url, link.http_code, reachable),
    }
    if not reachable:
        evidence["homepage"] = {
            "url": final_url,
            "text": f"Website {link.status}: {link.detail or 'unreachable'}.",
            "http_status": link.http_code,
            "present": False,
            "https": urlparse(final_url).scheme == "https",
            "absence": False,
        }
        return evidence

    origin = _origin(final_url)
    if not origin:
        return evidence

    fetches = 0
    seen_paths: set[str] = set()
    for path in _path_queue():
        if fetches >= EVIDENCE_MAX_FETCHES:
            break
        if path in seen_paths:
            continue
        seen_paths.add(path)
        url = urljoin(origin.rstrip("/") + "/", path.lstrip("/") if path != "/" else "")
        if path == "/":
            url = origin.rstrip("/") + "/"
        page = fetch_page(url)
        fetches += 1
        label = "homepage" if path == "/" else f"path:{path}"
        evidence[label] = page

    return evidence


def collect_evidence(website: str, track: str = "") -> dict:
    """Pages and recorded absences the model may cite for one tool."""
    if not (website or "").strip():
        return {}
    if (
        track == OPEN_SOURCE
        or parse_github_repo(website)
        or is_code_host(host_of(website))
    ):
        github = collect_github_evidence(website)
        if github:
            return github
    return collect_html_evidence(website)
