"""Orchestrate agent catalog scrape -> ingest."""

import logging

from agents.discovery import ALL_SOURCES
from agents.discovery.ingest import ensure_categories, ingest_candidates
from agents.discovery.sources import fetch_all_sources, fetch_directory_categories
from agents.models import AgentCategory, AIAgent

logger = logging.getLogger(__name__)


def run_agent_scrape(
    sources: tuple[str, ...] | list[str] | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict:
    selected = tuple(sources or ALL_SOURCES)
    unknown = [source for source in selected if source not in ALL_SOURCES]
    if unknown:
        raise ValueError(f"Unknown sources: {', '.join(unknown)}")

    if "aiagentsdirectory" in selected and not dry_run:
        labels = [item["label"] for item in fetch_directory_categories()]
        if labels:
            ensure_categories(labels)

    fetched = fetch_all_sources(selected, limit=limit)
    combined: list[dict] = []
    source_counts = {}
    for source, items in fetched.items():
        source_counts[source] = len(items)
        combined.extend(items)

    existing_count = AIAgent.objects.count()
    result = ingest_candidates(combined, dry_run=dry_run)
    result["sources"] = source_counts
    result["candidates"] = len(combined)
    result["categories"] = AgentCategory.objects.count()
    result["total_agents"] = (
        existing_count + result["created"] if dry_run else AIAgent.objects.count()
    )
    return result
