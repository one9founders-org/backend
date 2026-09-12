"""
GitHub most-starred open-source tools scraper.

Pulls highly starred, user-facing OSS repos (Reticle-class tools, MCP servers,
LLM CLIs, agents) via the GitHub Search API. No browser required.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.discovery.github_queries import (  # noqa: E402
    GITHUB_SEED_REPOS,
    GITHUB_STAR_QUERIES,
)
from config.scraper_settings import GitHubConfig  # noqa: E402
from utils.logger import ScraperLogger, setup_logging  # noqa: E402
from utils.output import OutputWriter, normalize_item  # noqa: E402
from utils.rate_limiter import RateLimiter  # noqa: E402


class GitHubStarredScraper:
    """Scrape most-starred open-source tool repos from GitHub."""

    def __init__(
        self,
        limit: int = GitHubConfig.DEFAULT_LIMIT,
        min_stars: int = GitHubConfig.MIN_STARS,
        output_dir: Optional[Path] = None,
        token: Optional[str] = None,
    ) -> None:
        self.limit = limit
        self.min_stars = min_stars
        self.output_dir = output_dir or GitHubConfig.OUTPUT_DIR
        self.token = token or os.getenv("GITHUB_TOKEN", "") or ""

        self.logger: ScraperLogger = setup_logging("github", GitHubConfig.LOG_DIR)
        self.rate_limiter = RateLimiter(min_delay=0.8, max_delay=1.5)
        self.output_writer = OutputWriter("GitHub", self.output_dir)
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=GitHubConfig.MAX_RETRIES,
            backoff_factor=GitHubConfig.RETRY_BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": GitHubConfig.USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        else:
            self.logger.warning(
                "GITHUB_TOKEN unset; GitHub search will be rate-limited"
            )
        session.headers.update(headers)
        return session

    def _search(self, query: str, per_page: int = 50) -> List[Dict[str, Any]]:
        self.rate_limiter.wait()
        try:
            response = self.session.get(
                "https://api.github.com/search/repositories",
                params={
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": per_page,
                },
                timeout=GitHubConfig.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return list(response.json().get("items") or [])
        except requests.RequestException as exc:
            self.logger.error(f"GitHub search failed for q={query!r}: {exc}")
            return []

    def _repo(self, full_name: str) -> Optional[Dict[str, Any]]:
        self.rate_limiter.wait()
        try:
            response = self.session.get(
                f"https://api.github.com/repos/{full_name}",
                timeout=GitHubConfig.REQUEST_TIMEOUT,
            )
            if response.status_code == 404:
                self.logger.warning(f"Seed repo not found: {full_name}")
                return None
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else None
        except requests.RequestException as exc:
            self.logger.error(f"GitHub repo lookup failed for {full_name}: {exc}")
            return None

    def _normalize(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if item.get("fork") or item.get("archived"):
            return None
        stars = int(item.get("stargazers_count") or 0)
        if stars < self.min_stars and item.get("full_name") not in GITHUB_SEED_REPOS:
            return None
        full_name = (item.get("full_name") or "").strip()
        html_url = item.get("html_url") or ""
        if not full_name or not html_url:
            return None
        license_info = item.get("license") or {}
        license_spdx = ""
        if isinstance(license_info, dict):
            license_spdx = (
                license_info.get("spdx_id") or license_info.get("key") or ""
            ).strip()
        homepage = (item.get("homepage") or "").strip()
        topics = list(item.get("topics") or [])
        return normalize_item(
            title=f"github/{full_name}",
            description=item.get("description") or "",
            url=html_url,
            external_url=homepage or html_url,
            category="open-source",
            tags=topics,
            metrics={"stars": stars, "forks": item.get("forks_count") or 0},
            images=[],
            raw={
                "full_name": full_name,
                "license": license_spdx,
                "pushed_at": item.get("pushed_at") or "",
                "homepage": homepage,
            },
        )

    def scrape(self) -> List[Dict[str, Any]]:
        """Return normalized most-starred OSS tool items, highest stars first."""
        self.logger.info(
            f"Scraping most-starred GitHub tools "
            f"(limit={self.limit}, min_stars={self.min_stars})"
        )
        seen: set[str] = set()
        items: List[Dict[str, Any]] = []

        def _add(raw: Dict[str, Any]) -> None:
            normalized = self._normalize(raw)
            if not normalized:
                return
            key = (normalized.get("url") or "").lower().rstrip("/")
            if not key or key in seen:
                return
            seen.add(key)
            items.append(normalized)

        for query in GITHUB_STAR_QUERIES:
            self.logger.info(f"Star query: {query}")
            for raw in self._search(query, per_page=50):
                _add(raw)

        # Seeds always considered (even below min_stars / after search fills).
        for full_name in GITHUB_SEED_REPOS:
            raw = self._repo(full_name)
            if raw:
                _add(raw)

        items.sort(
            key=lambda row: int((row.get("metrics") or {}).get("stars") or 0),
            reverse=True,
        )
        items = items[: self.limit]
        self.logger.info(f"Scraping complete. Total items: {len(items)}")
        return items

    def save_output(self, items: Optional[List[Dict[str, Any]]] = None) -> Path:
        rows = items if items is not None else self.scrape()
        for row in rows:
            self.output_writer.add_item(row)
        return self.output_writer.write()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scrape most-starred open-source GitHub tool repos"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=GitHubConfig.DEFAULT_LIMIT,
        help=f"Max repos to return (default {GitHubConfig.DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--min-stars",
        type=int,
        default=GitHubConfig.MIN_STARS,
        help=f"Minimum stars for non-seed repos (default {GitHubConfig.MIN_STARS})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional output JSON path (directory parent is used)",
    )
    args = parser.parse_args()

    output_dir = None
    if args.output:
        out_path = Path(args.output)
        output_dir = out_path.parent if out_path.suffix else out_path

    scraper = GitHubStarredScraper(
        limit=args.limit,
        min_stars=args.min_stars,
        output_dir=output_dir,
    )
    items = scraper.scrape()
    path = scraper.save_output(items)
    if args.output and Path(args.output).suffix:
        # Re-write to the exact path the caller asked for.
        import json
        from datetime import datetime

        payload = {
            "source": "GitHub",
            "scrape_date": datetime.utcnow().isoformat() + "Z",
            "items": items,
        }
        Path(args.output).write_text(json.dumps(payload, indent=2))
        print(f"Wrote {len(items)} items to {args.output}")
    else:
        print(f"Wrote {len(items)} items to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
