"""Preferred public URL when a tool and an agent describe the same product.

Agent URLs stay preferred. They already carry search exposure, and this module
does not issue redirects. Sitemap and page metadata should agree with
``preferred_path_for_tool``.
"""

from __future__ import annotations

from django.db.models import Exists, OuterRef, Value
from django.db.models.functions import Coalesce, Length

MIN_PREFERRED_AGENT_CHARS = 40


def _agent_model():
    from agents.models import AIAgent

    return AIAgent


def preferred_agent_queryset():
    """Agents with enough text to be the canonical page for a shared slug."""
    agent = _agent_model()
    return agent.objects.annotate(
        _text_len=Length(Coalesce("short_description", Value("")))
        + Length(Coalesce("long_description", Value("")))
    ).filter(_text_len__gte=MIN_PREFERRED_AGENT_CHARS)


def annotate_preferred_agent(queryset):
    match = preferred_agent_queryset().filter(slug=OuterRef("slug"))
    return queryset.annotate(_agent_preferred=Exists(match))


def exclude_preferred_agent_duplicates(queryset):
    return queryset.exclude(slug__in=preferred_agent_queryset().values("slug"))


def preferred_path_for_tool(tool) -> str:
    if getattr(tool, "_agent_preferred", None):
        return f"/agents/{tool.slug}"
    if preferred_agent_queryset().filter(slug=tool.slug).exists():
        return f"/agents/{tool.slug}"
    return f"/tool/{tool.slug}"


def overlap_rows(limit: int = 500) -> list[dict]:
    """Reviewable map. Redirects are not applied."""
    from api.models import Tool

    agent = _agent_model()
    preferred = {
        row.slug: row
        for row in preferred_agent_queryset().only(
            "slug", "name", "website", "short_description"
        )[:limit]
    }
    if not preferred:
        return []
    tools = Tool.objects.filter(slug__in=preferred.keys()).only(
        "slug", "name", "website", "is_active"
    )
    rows = []
    for tool in tools:
        agent_row = preferred.get(tool.slug)
        if agent_row is None:
            continue
        same_site = _host(tool.website) and _host(tool.website) == _host(
            agent_row.website
        )
        rows.append(
            {
                "slug": tool.slug,
                "tool_path": f"/tool/{tool.slug}",
                "agent_path": f"/agents/{tool.slug}",
                "preferred_path": f"/agents/{tool.slug}",
                "redirect": "not_applied",
                "tool_name": tool.name,
                "agent_name": agent_row.name,
                "tool_active": tool.is_active,
                "same_website_host": bool(same_site),
                "reason": (
                    "Shared slug with a substantive agent page. "
                    "Agent URL stays canonical until a reviewed redirect."
                ),
            }
        )
    rows.sort(key=lambda row: row["slug"])
    return rows


def _host(url: str | None) -> str:
    if not url:
        return ""
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host
