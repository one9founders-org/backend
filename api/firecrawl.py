"""Thin Firecrawl v2 client. Map + scrape only — scoring stays in-process."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests
from django.conf import settings

FIRECRAWL_BASE = "https://api.firecrawl.dev/v2"
DEFAULT_TIMEOUT = 90
# Hobby plan is about 10 req/min. Stay under that between map/scrape calls.
MIN_INTERVAL = 6.0
MAX_RETRIES = 4
MAP_SEARCH = (
    "privacy security compliance trust about DPDP SOC ISO consent "
    "residency localization KYC AML"
)

logger = logging.getLogger(__name__)


class FirecrawlError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class MappedLink:
    url: str
    title: str = ""
    description: str = ""


@dataclass
class ScrapedPage:
    url: str
    title: str
    markdown: str


def is_configured() -> bool:
    return bool(getattr(settings, "FIRECRAWL_API_KEY", "") or "")


def _headers() -> dict[str, str]:
    key = getattr(settings, "FIRECRAWL_API_KEY", "") or ""
    if not key:
        raise FirecrawlError("FIRECRAWL_API_KEY is not set.")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _raise_for_status(response: requests.Response) -> None:
    if response.status_code == 200:
        return
    try:
        payload = response.json()
        detail = payload.get("error") or payload.get("message") or response.text
    except ValueError:
        detail = response.text or f"HTTP {response.status_code}"
    raise FirecrawlError(str(detail), status_code=response.status_code)


def _retry_wait(response: requests.Response) -> float:
    raw = response.headers.get("Retry-After")
    try:
        return max(float(raw), MIN_INTERVAL)
    except (TypeError, ValueError):
        return MIN_INTERVAL


def _as_links(raw) -> list[MappedLink]:
    links: list[MappedLink] = []
    if not isinstance(raw, list):
        return links
    for item in raw:
        if isinstance(item, str) and item.strip():
            links.append(MappedLink(url=item.strip()))
            continue
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        if not url:
            continue
        links.append(
            MappedLink(
                url=url,
                title=(item.get("title") or "").strip(),
                description=(item.get("description") or "").strip(),
            )
        )
    return links


class FirecrawlClient:
    def __init__(
        self,
        session: requests.Session | None = None,
        min_interval: float = MIN_INTERVAL,
    ):
        self.session = session or requests.Session()
        self.min_interval = min_interval
        self._last = 0.0

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)

    def _post(self, path: str, payload: dict) -> requests.Response:
        last_error: FirecrawlError | None = None
        for attempt in range(MAX_RETRIES):
            self._throttle()
            response = self.session.post(
                f"{FIRECRAWL_BASE}{path}",
                headers=_headers(),
                json=payload,
                timeout=DEFAULT_TIMEOUT,
            )
            self._last = time.monotonic()
            if response.status_code == 429:
                wait = _retry_wait(response)
                logger.warning(
                    "Firecrawl 429 on %s (attempt %s/%s), retry in %.1fs",
                    path,
                    attempt + 1,
                    MAX_RETRIES,
                    wait,
                )
                last_error = FirecrawlError("Rate limit exceeded.", status_code=429)
                time.sleep(wait)
                continue
            _raise_for_status(response)
            return response
        raise last_error or FirecrawlError("Rate limit exceeded.", status_code=429)

    def map(
        self,
        url: str,
        *,
        search: str = MAP_SEARCH,
        limit: int = 200,
    ) -> list[MappedLink]:
        response = self._post(
            "/map",
            {
                "url": url,
                "search": search,
                "limit": limit,
                "ignoreQueryParameters": True,
                "location": {"country": "IN"},
            },
        )
        body = response.json()
        if not body.get("success", True):
            raise FirecrawlError(str(body.get("error") or "Map failed."))
        return _as_links(body.get("links") or [])

    def scrape(self, url: str) -> ScrapedPage:
        response = self._post(
            "/scrape",
            {
                "url": url,
                "formats": ["markdown"],
                "location": {"country": "IN"},
            },
        )
        body = response.json()
        if not body.get("success", True):
            raise FirecrawlError(str(body.get("error") or "Scrape failed."))
        data = body.get("data") or {}
        metadata = data.get("metadata") or {}
        markdown = data.get("markdown") or ""
        source = (metadata.get("sourceURL") or url).strip() or url
        title = (metadata.get("title") or "").strip()
        return ScrapedPage(url=source, title=title, markdown=markdown)
