"""One server-side event path for discovery ranking and funnel counts.

Browser analytics may mirror an event for product debugging, but Trending reads
only rows stored here. The same event_id is ignored on a second delivery.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.utils import timezone

from .models import CatalogEvent, Tool, ToolClick

RANKING_CLICK_ACTIONS = {"visit_tool", "official_site_click"}
TOOL_CLICK_ACTIONS = {
    "detail_view": "view_details",
    "official_site_click": "visit_tool",
    "view_details": "view_details",
    "visit_tool": "visit_tool",
    "write_review": "write_review",
    "i_use_this": "i_use_this",
}
MAX_RANKED_CLICKS = 5
BOT_MARKERS = (
    "bot",
    "spider",
    "crawler",
    "slurp",
    "wget",
    "headless",
    "python-requests",
)


def looks_like_automation(user_agent: str, internal: bool) -> bool:
    if internal:
        return True
    ua = (user_agent or "").lower()
    return any(marker in ua for marker in BOT_MARKERS)


def record_catalog_event(*, payload: dict, user_agent: str = "", internal: bool = False):
    """Persist one event. Returns (event, created)."""
    raw_id = payload.get("event_id") or ""
    try:
        event_id = uuid.UUID(str(raw_id)) if raw_id else uuid.uuid4()
    except (TypeError, ValueError):
        event_id = uuid.uuid4()

    existing = CatalogEvent.objects.filter(event_id=event_id).first()
    if existing:
        return existing, False

    event_name = (payload.get("event_name") or "").strip()[:64]
    if not event_name:
        raise ValueError("event_name is required")

    automated = looks_like_automation(user_agent, internal)
    session_id = (payload.get("session_id") or "")[:64]
    entity_type = (payload.get("entity_type") or "")[:32]
    entity_slug = (payload.get("entity_slug") or "")[:255]
    try:
        entity_id = str(payload.get("entity_id") or "")[:64]
    except Exception:
        entity_id = ""
    position = payload.get("result_position")
    try:
        position = int(position) if position is not None and position != "" else None
    except (TypeError, ValueError):
        position = None
    if position is not None and position < 0:
        position = None

    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    safe_context = {
        key: context[key]
        for key in ("results_count", "offer", "sort", "filter_count")
        if key in context
    }

    counts = not automated
    tool = _tool_for(entity_type, entity_id, entity_slug)
    click_action = TOOL_CLICK_ACTIONS.get(event_name)
    if (
        counts
        and tool is not None
        and click_action == "visit_tool"
        and session_id
        and _ranked_click_cap_reached(tool, session_id)
    ):
        counts = False

    event = CatalogEvent.objects.create(
        event_name=event_name,
        event_id=event_id,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_slug=entity_slug or (tool.slug if tool else ""),
        surface=(payload.get("surface") or "")[:64],
        result_position=position,
        query_id=(payload.get("query_id") or "")[:64],
        campaign=(payload.get("campaign") or "")[:128],
        session_id=session_id,
        context=safe_context,
        counts_for_ranking=counts,
    )
    if tool is not None and click_action:
        ToolClick.objects.create(
            tool=tool,
            action=click_action,
            session_id=session_id[:255],
            surface=event.surface,
            result_position=position,
            query_id=event.query_id,
            campaign=event.campaign,
            event_id=event_id,
            counts_for_ranking=counts,
        )
    return event, True


def _tool_for(entity_type: str, entity_id: str, entity_slug: str) -> Tool | None:
    if entity_type not in {"", "tool"}:
        return None
    if entity_id.isdigit():
        return Tool.objects.filter(pk=int(entity_id), is_active=True).first()
    if entity_slug:
        return Tool.objects.filter(slug=entity_slug, is_active=True).first()
    return None


def _ranked_click_cap_reached(tool: Tool, session_id: str) -> bool:
    since = timezone.now() - timedelta(hours=24)
    ranked = ToolClick.objects.filter(
        tool=tool,
        session_id=session_id,
        action="visit_tool",
        counts_for_ranking=True,
        created_at__gte=since,
    ).count()
    return ranked >= MAX_RANKED_CLICKS
