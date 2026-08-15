"""Free popularity and verification signals -- no paid search API.

Replaces the Google Programmable Search stage ($5 per 1,000 queries) with
sources that are free and keyless:

  Tranco    domain popularity rank, from a bulk list refreshed locally
  Wikidata  notability + an independent one-line description
  HN        mentions and points from the Algolia search API

None of these individually replace a search engine. Together they answer
the two questions the search stage existed to answer: is this a real,
known product, and how popular is it relative to the rest of the directory.
"""

import json
import logging
import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import requests
from django.conf import settings

from .classify import host_of
from .linkcheck import USER_AGENT

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15

HN_ENDPOINT = "https://hn.algolia.com/api/v1/search"
WIKIDATA_ENDPOINT = "https://www.wikidata.org/w/api.php"

# Hosting platforms where a subdomain belongs to a user, not to the
# platform's owner. Without this, every *.github.io page inherits
# github.io's global rank and a hobby demo outranks Figma.
SHARED_HOSTING_SUFFIXES = frozenset(
    {
        "github.io",
        "gitlab.io",
        "vercel.app",
        "netlify.app",
        "netlify.com",
        "herokuapp.com",
        "streamlit.app",
        "replit.app",
        "repl.co",
        "glitch.me",
        "notion.site",
        "webflow.io",
        "wixsite.com",
        "framer.app",
        "framer.website",
        "bubbleapps.io",
        "softr.app",
        "carrd.co",
        "pages.dev",
        "workers.dev",
        "surge.sh",
        "firebaseapp.com",
        "web.app",
        "azurewebsites.net",
        "onrender.com",
        "fly.dev",
        "railway.app",
        "t.me",
        "telegram.me",
        "discord.gg",
        "gumroad.com",
        "substack.com",
        "medium.com",
    }
)

# The list runs to 1M, and traffic falls off roughly geometrically, so
# score on a log scale. Buckets were tried first and were too coarse --
# every domain inside the top 10k tied, which left the most important
# part of the directory with no ordering at all.
_RANK_CEILING = 1_000_000
_LOG_CEILING = math.log10(_RANK_CEILING)


@dataclass
class Signals:
    tranco_rank: int | None = None
    rank_inherited: bool = False  # rank came from a parent domain
    shared_hosting: bool = False
    wikidata_id: str = ""
    wikidata_description: str = ""
    hn_story_count: int = 0
    hn_points: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def has_any(self) -> bool:
        return bool(self.tranco_rank or self.wikidata_id or self.hn_story_count)


# --- Tranco -----------------------------------------------------------


def tranco_db_path() -> Path:
    return Path(
        getattr(
            settings,
            "TRANCO_DB_PATH",
            Path(settings.BASE_DIR) / "data" / "tranco.sqlite3",
        )
    )


def is_shared_host(host: str) -> bool:
    return any(
        host == suffix or host.endswith(f".{suffix}")
        for suffix in SHARED_HOSTING_SUFFIXES
    )


def _registrable_candidates(host: str) -> list[str]:
    """Progressively shorter parent domains, longest first."""
    parts = host.split(".")
    return [".".join(parts[i:]) for i in range(1, max(1, len(parts) - 1))]


def lookup_tranco(host: str, connection: sqlite3.Connection) -> tuple[int | None, bool]:
    """Return (rank, inherited_from_parent).

    A host on shared hosting never inherits its platform's rank -- that is
    the platform's traffic, not the tool's.
    """
    if not host:
        return None, False

    cursor = connection.execute("SELECT rank FROM ranks WHERE domain = ?", (host,))
    row = cursor.fetchone()
    if row:
        return int(row[0]), False

    if is_shared_host(host):
        return None, False

    for parent in _registrable_candidates(host):
        cursor = connection.execute(
            "SELECT rank FROM ranks WHERE domain = ?", (parent,)
        )
        row = cursor.fetchone()
        if row:
            return int(row[0]), True
    return None, False


def open_tranco() -> sqlite3.Connection | None:
    path = tranco_db_path()
    if not path.exists():
        logger.warning(
            "Tranco database missing at %s; run manage.py refresh_tranco", path
        )
        return None
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def rank_score(rank: int | None, *, inherited: bool = False) -> float:
    """Map a Tranco rank onto 0..1, continuously.

    rank 1 -> 1.0, rank 1,000 -> 0.5, rank 1,000,000 -> 0.0.
    """
    if not rank or rank < 1:
        return 0.0
    score = 1.0 - (math.log10(rank) / _LOG_CEILING)
    score = max(0.0, min(score, 1.0))
    # A rank borrowed from a parent domain describes the parent company,
    # not this specific tool, so it counts for less.
    return round(score * (0.5 if inherited else 1.0), 4)


# --- Wikidata ---------------------------------------------------------


WIKIDATA_OFFICIAL_WEBSITE = "P856"
WIKIDATA_CANDIDATES = 5


def _official_websites(entity_id: str) -> list[str]:
    """Hosts listed as the entity's official website (property P856)."""
    try:
        response = requests.get(
            WIKIDATA_ENDPOINT,
            params={
                "action": "wbgetclaims",
                "entity": entity_id,
                "property": WIKIDATA_OFFICIAL_WEBSITE,
                "format": "json",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        claims = response.json().get("claims", {}).get(WIKIDATA_OFFICIAL_WEBSITE, [])
    except (requests.RequestException, json.JSONDecodeError) as exc:
        logger.debug("Wikidata claims lookup failed for %s: %s", entity_id, exc)
        return []

    hosts = []
    for claim in claims:
        value = (
            claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if isinstance(claim, dict)
            else None
        )
        if isinstance(value, str):
            hosts.append(host_of(value))
    return [host for host in hosts if host]


def fetch_wikidata(name: str, website: str = "") -> tuple[str, str]:
    """Return (entity_id, description) for the entity matching this tool.

    A label match alone is not enough: searching "Perplexity" returns a
    1990 video game whose label matches exactly. The entity is only
    accepted when its official-website claim (P856) resolves to the same
    host as the tool, which is unambiguous.
    """
    target_host = host_of(website)
    if not name or not target_host:
        return "", ""

    try:
        response = requests.get(
            WIKIDATA_ENDPOINT,
            params={
                "action": "wbsearchentities",
                "search": name,
                "language": "en",
                "format": "json",
                "limit": WIKIDATA_CANDIDATES,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        results = response.json().get("search") or []
    except (requests.RequestException, json.JSONDecodeError) as exc:
        logger.debug("Wikidata lookup failed for %s: %s", name, exc)
        return "", ""

    for candidate in results:
        entity_id = candidate.get("id") or ""
        if not entity_id:
            continue
        hosts = _official_websites(entity_id)
        if any(
            host == target_host
            or host.endswith(f".{target_host}")
            or target_host.endswith(f".{host}")
            for host in hosts
        ):
            return entity_id, (candidate.get("description") or "")
    return "", ""


# --- Hacker News ------------------------------------------------------


def fetch_hn(domain: str) -> tuple[int, int]:
    """Return (story_count, total_points) for mentions of a domain."""
    if not domain:
        return 0, 0
    try:
        response = requests.get(
            HN_ENDPOINT,
            params={"query": domain, "tags": "story", "hitsPerPage": 20},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, json.JSONDecodeError) as exc:
        logger.debug("HN lookup failed for %s: %s", domain, exc)
        return 0, 0

    hits = payload.get("hits") or []
    # Only count stories that actually point at the domain, otherwise a
    # generic name matches unrelated threads.
    relevant = [
        hit
        for hit in hits
        if domain in (hit.get("url") or "")
        or domain.split(".")[0] in (hit.get("title") or "").lower()
    ]
    points = sum(int(hit.get("points") or 0) for hit in relevant)
    return len(relevant), points


def hn_score(story_count: int, points: int) -> float:
    if not story_count:
        return 0.0
    return round(min(points / 1500.0, 1.0) * 0.6 + min(story_count / 8.0, 1.0) * 0.4, 4)


# --- Combined ---------------------------------------------------------


def gather(
    name: str,
    website: str,
    *,
    connection: sqlite3.Connection | None = None,
    use_wikidata: bool = True,
    use_hn: bool = True,
) -> Signals:
    """Collect every free signal available for one tool."""
    host = host_of(website)
    signals = Signals(shared_hosting=is_shared_host(host))

    if connection is not None:
        rank, inherited = lookup_tranco(host, connection)
        signals.tranco_rank = rank
        signals.rank_inherited = inherited
        if inherited:
            signals.notes.append("rank inherited from parent domain")
    if signals.shared_hosting:
        signals.notes.append("hosted on a shared platform")

    if use_wikidata:
        entity, description = fetch_wikidata(name, website)
        signals.wikidata_id = entity
        signals.wikidata_description = description

    if use_hn and host:
        signals.hn_story_count, signals.hn_points = fetch_hn(host)

    return signals


def external_score(signals: Signals) -> float:
    """Blend the free signals into the 0..1 the ranker expects."""
    tranco = rank_score(signals.tranco_rank, inherited=signals.rank_inherited)
    hn = hn_score(signals.hn_story_count, signals.hn_points)
    wikidata = 0.25 if signals.wikidata_id else 0.0

    # Tranco dominates because it is the only direct traffic proxy; the
    # others mostly rescue tools the list does not cover.
    combined = tranco * 0.65 + hn * 0.20 + wikidata * 0.15
    if signals.shared_hosting:
        combined *= 0.5
    return round(min(combined, 1.0), 4)
