"""Resolve a usable logo for a tool.

93% of production rows have no logo_url, which is the main reason the
directory reads as unfinished. This walks a preference chain from
best-quality to always-available and reports which source won.
"""

import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from . import LOGO_MIN_BYTES, LOGO_TIMEOUT
from .linkcheck import USER_AGENT

logger = logging.getLogger(__name__)

# Ordered best -> worst. og:image is usually a social card (wide, branded);
# apple-touch-icon is usually a clean square mark, which suits a grid better.
SOURCE_APPLE_TOUCH = "apple_touch_icon"
SOURCE_OG_IMAGE = "og_image"
SOURCE_LINK_ICON = "link_icon"
SOURCE_GOOGLE_FAVICON = "google_favicon"
SOURCE_NONE = "none"

GOOGLE_FAVICON = "https://www.google.com/s2/favicons?sz=128&domain={host}"

_SVG_OR_IMG_RE = re.compile(r"\.(?:png|jpe?g|svg|webp|ico)(?:\?|$)", re.IGNORECASE)


@dataclass
class LogoResult:
    url: str = ""
    source: str = SOURCE_NONE
    detail: str = ""

    @property
    def found(self) -> bool:
        return bool(self.url)


def _absolute(base: str, candidate: str) -> str:
    if not candidate:
        return ""
    return urljoin(base, candidate.strip())


def _icon_candidates(soup: BeautifulSoup, base_url: str) -> list[tuple[str, str]]:
    """(source, absolute_url) pairs in preference order."""
    found: list[tuple[str, str]] = []

    for rel in ("apple-touch-icon", "apple-touch-icon-precomposed"):
        tag = soup.find("link", rel=lambda v: v and rel in " ".join(v).lower())
        if tag and tag.get("href"):
            found.append((SOURCE_APPLE_TOUCH, _absolute(base_url, tag["href"])))
            break

    for attrs in ({"property": "og:image"}, {"name": "twitter:image"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            found.append((SOURCE_OG_IMAGE, _absolute(base_url, tag["content"])))
            break

    tag = soup.find("link", rel=lambda v: v and "icon" in " ".join(v).lower())
    if tag and tag.get("href"):
        found.append((SOURCE_LINK_ICON, _absolute(base_url, tag["href"])))

    return [(src, url) for src, url in found if url and _SVG_OR_IMG_RE.search(url)]


def _image_is_real(url: str) -> bool:
    """Confirm the URL serves a non-trivial image before we store it."""
    try:
        response = requests.get(
            url,
            timeout=LOGO_TIMEOUT,
            stream=True,
            headers={"User-Agent": USER_AGENT},
        )
        if response.status_code >= 400:
            return False
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "image" not in content_type:
            return False
        length = response.headers.get("Content-Length")
        if length and int(length) < LOGO_MIN_BYTES:
            return False
        return True
    except (requests.RequestException, ValueError) as exc:
        logger.debug("logo probe failed for %s: %s", url, exc)
        return False


def resolve_logo(website: str, *, verify: bool = True) -> LogoResult:
    """Best available logo for a site. Falls back to Google's favicon service."""
    if not website:
        return LogoResult(detail="no website")

    target = website if "://" in website else f"https://{website}"
    host = urlparse(target).netloc

    try:
        response = requests.get(
            target,
            timeout=LOGO_TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            allow_redirects=True,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text[:120_000], "html.parser")
        base_url = response.url or target
        host = urlparse(base_url).netloc
    except (requests.RequestException, ValueError) as exc:
        logger.debug("logo page fetch failed for %s: %s", website, exc)
        soup = None

    if soup is not None:
        for source, url in _icon_candidates(soup, base_url):
            if not verify or _image_is_real(url):
                return LogoResult(url=url, source=source)

    # Always-available fallback: it renders something recognisable for any
    # live domain, which beats an empty tile in the grid.
    if host:
        return LogoResult(
            url=GOOGLE_FAVICON.format(host=host),
            source=SOURCE_GOOGLE_FAVICON,
            detail="fell back to favicon service",
        )
    return LogoResult(detail="could not resolve host")
