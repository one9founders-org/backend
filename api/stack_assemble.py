"""Assemble a free-first stack from the live catalog and persist it.

The model never names tools from memory. It only ranks and lanes tools
that `smart_search` already returned. If OpenAI is down, a heuristic
fallback still produces a saved stack you can return to.
"""

from __future__ import annotations

import json
import logging
import re

from django.conf import settings
from openai import OpenAI

from api.models import JobStack, Tool
from api.smart_search import smart_search

logger = logging.getLogger(__name__)

AI_TOOL = "ai_tool"
AI_AGENT = "ai_agent"
OPEN_SOURCE = "open_source"
AGENT_SKILL = "agent_skill"
MCP_SERVER = "mcp_server"

LANE_SPECS = [
    {
        "id": "selfhost",
        "label": "Self-host and pay nothing",
        "tracks": (OPEN_SOURCE,),
    },
    {
        "id": "skills",
        "label": "Drop into Claude today",
        "tracks": (AGENT_SKILL, MCP_SERVER),
    },
    {
        "id": "agents",
        "label": "Agents that act",
        "tracks": (AI_AGENT,),
    },
    {
        "id": "hosted",
        "label": "Hosted tools",
        "tracks": (AI_TOOL,),
    },
]

WORKER_ITEM = {
    "slug": None,
    "name": "One9 Worker",
    "note": "Schedule this job and get a diff",
    "cost": "free",
    "cost_label": "One9",
    "href": "/worker",
    "track": AI_AGENT,
}

WORKER_LANE_ID = "worker"
WORKER_LANE_LABEL = "Run it on autopilot"

ASSEMBLE_SYSTEM_PROMPT = """You assemble a free-first founder stack from a \
fixed candidate list. You never invent a tool, domain, or slug.
Return ONLY valid JSON:
{
  "title": "short title for this stack",
  "blurb": "one sentence on what this stack gets done",
  "cash_out": "one sentence on cost, INR if paid",
  "picks": [
    {"slug": "exact-candidate-slug", "lane": "selfhost|skills|agents|hosted", \
"note": "why this tool, under 12 words"}
  ]
}
Rules:
- Every slug MUST be in the candidate list.
- Prefer free / open-source / skills before paid hosted tools.
- At most 3 picks per lane. Omit a lane if nothing fits.
- Do not mention One9 Worker; the server adds it.
- lane must be one of: selfhost, skills, agents, hosted.
"""

_EXCHANGE = 83.5
_MAX_PER_LANE = 3


def _client() -> OpenAI:
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _guess_track(tool: Tool) -> str:
    """Prefer a non-default persisted track; else re-run the classifier.

    Rows still on the ``ai_tool`` default may be uncategorized GitHub
    repos, so we re-classify those. Explicit tracks (open_source, MCP,
    skill, agent) are trusted as already bucketed.
    """
    from api.hygiene.track import classify_track

    stored = (tool.track or "").strip()
    if stored in {AI_AGENT, OPEN_SOURCE, AGENT_SKILL, MCP_SERVER}:
        return stored
    name = tool.name or ""
    text = " ".join(
        filter(
            None,
            [
                name,
                tool.short_description or "",
                (tool.description or "")[:400],
                " ".join(tool.tags or []),
                " ".join(tool.use_cases or []),
            ],
        )
    )
    return classify_track(name, tool.website or "", text)


def _cost_for(tool: Tool, track: str) -> tuple[str, str]:
    if track == OPEN_SOURCE:
        return "free", "Open source"
    if track == AGENT_SKILL:
        return "skill", "SKILL.md"
    if track == MCP_SERVER:
        return "free", "MCP"
    if tool.pricing_type == "free" or (
        tool.free_tier_available and not tool.pricing_from
    ):
        return "free", "Free"
    if tool.free_tier_available:
        return "free", "Free tier"
    inr = None
    if tool.pricing_inr_override is not None:
        inr = round(float(tool.pricing_inr_override))
    elif tool.pricing_from is not None:
        inr = round(float(tool.pricing_from) * _EXCHANGE)
    if inr and inr > 0:
        return "paid", f"₹{inr:,}/mo"
    return "paid", "Paid"


def _item_from_tool(tool: Tool, note: str = "") -> dict:
    track = _guess_track(tool)
    cost, cost_label = _cost_for(tool, track)
    return {
        "slug": tool.slug,
        "name": tool.name,
        "note": (note or tool.short_description or "")[:160],
        "cost": cost,
        "cost_label": cost_label,
        "href": f"/tool/{tool.slug}",
        "track": track,
    }


def _free_rank(item: dict) -> tuple:
    order = {"free": 0, "skill": 1, "paid": 2}
    return (order.get(item.get("cost"), 9), item.get("name") or "")


def _candidates_from_search(query: str, top_k: int = 24) -> list[Tool]:
    rows = smart_search(query, top_k=top_k) or []
    slugs = [r.get("slug") for r in rows if r.get("slug")]
    if not slugs:
        return []
    tools = {t.slug: t for t in Tool.objects.filter(slug__in=slugs, is_active=True)}
    ordered = [tools[s] for s in slugs if s in tools]
    return ordered


def _heuristic_picks(tools: list[Tool]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {spec["id"]: [] for spec in LANE_SPECS}
    for tool in tools:
        track = _guess_track(tool)
        item = _item_from_tool(tool)
        for spec in LANE_SPECS:
            if track in spec["tracks"] and len(buckets[spec["id"]]) < _MAX_PER_LANE:
                buckets[spec["id"]].append(item)
                break
    for lane_id, items in buckets.items():
        items.sort(key=_free_rank)
        buckets[lane_id] = items[:_MAX_PER_LANE]
    return buckets


def _lanes_from_buckets(buckets: dict[str, list[dict]]) -> list[dict]:
    lanes = []
    for spec in LANE_SPECS:
        items = buckets.get(spec["id"]) or []
        if items:
            lanes.append({"id": spec["id"], "label": spec["label"], "items": items})
    lanes.append(
        {
            "id": WORKER_LANE_ID,
            "label": WORKER_LANE_LABEL,
            "items": [dict(WORKER_ITEM)],
        }
    )
    return lanes


def _llm_picks(query: str, tools: list[Tool]) -> dict | None:
    if not tools:
        return None
    catalog = [
        {
            "slug": t.slug,
            "name": t.name,
            "track": _guess_track(t),
            "pricing": t.pricing_type,
            "free_tier": t.free_tier_available,
            "blurb": (t.short_description or "")[:160],
        }
        for t in tools[:24]
    ]
    try:
        response = _client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": ASSEMBLE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"job": query, "candidates": catalog},
                        ensure_ascii=True,
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=700,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(response.choices[0].message.content or "{}")
        if not isinstance(parsed, dict):
            return None
        return parsed
    except Exception as e:
        logger.warning("Stack assemble LLM failed for '%s': %s", query, e)
        return None


def _apply_llm_picks(parsed: dict, tools: list[Tool]) -> dict[str, list[dict]]:
    by_slug = {t.slug: t for t in tools}
    valid_lanes = {spec["id"] for spec in LANE_SPECS}
    buckets: dict[str, list[dict]] = {spec["id"]: [] for spec in LANE_SPECS}
    seen: set[str] = set()
    for pick in parsed.get("picks") or []:
        if not isinstance(pick, dict):
            continue
        slug = (pick.get("slug") or "").strip()
        lane = (pick.get("lane") or "").strip()
        if slug not in by_slug or lane not in valid_lanes or slug in seen:
            continue
        if len(buckets[lane]) >= _MAX_PER_LANE:
            continue
        seen.add(slug)
        note = re.sub(r"\s+", " ", str(pick.get("note") or "")).strip()[:160]
        buckets[lane].append(_item_from_tool(by_slug[slug], note))
    return buckets


def _title_from_query(query: str) -> str:
    text = re.sub(r"\s+", " ", query).strip()
    if len(text) <= 80:
        return text[0].upper() + text[1:] if text else "Founder stack"
    return text[:77].rstrip() + "…"


def _cash_out(lanes: list[dict]) -> str:
    paid = [
        item
        for lane in lanes
        if lane.get("id") != "worker"
        for item in lane.get("items") or []
        if item.get("cost") == "paid"
    ]
    free_n = sum(
        1
        for lane in lanes
        if lane.get("id") != "worker"
        for item in lane.get("items") or []
        if item.get("cost") in ("free", "skill")
    )
    if not paid:
        return f"{free_n} free picks. Paid sits last, and nothing here needs a card."
    labels = ", ".join(item.get("cost_label") or item.get("name") for item in paid[:3])
    return f"{free_n} free picks first. Paid only if you need it: {labels}."


def assemble_and_save(
    query: str,
    *,
    source: str = "agent",
    created_by=None,
) -> JobStack:
    query = (query or "").strip()
    tools = _candidates_from_search(query)
    heuristic = _heuristic_picks(tools)
    parsed = _llm_picks(query, tools) if tools else None
    if parsed:
        buckets = _apply_llm_picks(parsed, tools)
        # If the model dropped everything, fall back to the heuristic.
        if not any(buckets.values()):
            buckets = heuristic
        title = (parsed.get("title") or "").strip()[:200] or _title_from_query(query)
        blurb = (parsed.get("blurb") or "").strip()[:400]
        cash = (parsed.get("cash_out") or "").strip()[:400]
    else:
        buckets = heuristic
        title = _title_from_query(query)
        blurb = f"A free-first stack for: {query}"
        cash = ""

    lanes = _lanes_from_buckets(buckets)
    if not cash:
        cash = _cash_out(lanes)
    if not blurb:
        blurb = f"A free-first stack for: {query}"

    stack = JobStack(
        query=query[:500],
        title=title[:200],
        blurb=blurb,
        cash_out=cash[:400],
        source="person" if source == "person" else "agent",
        created_by=(
            created_by if getattr(created_by, "is_authenticated", False) else None
        ),
        lanes=lanes,
    )
    stack.save()
    return stack


def save_person_stack(
    *,
    query: str,
    title: str,
    blurb: str,
    cash_out: str,
    lanes: list,
    created_by=None,
) -> JobStack:
    """Persist a person-edited stack. Unknown slugs are dropped; Worker is appended."""
    query = (query or "").strip()[:500]
    raw_items = []
    for lane in lanes or []:
        if not isinstance(lane, dict):
            continue
        for item in lane.get("items") or []:
            if isinstance(item, dict) and item.get("slug"):
                raw_items.append(item)

    slugs = [i["slug"] for i in raw_items]
    tools = {t.slug: t for t in Tool.objects.filter(slug__in=slugs, is_active=True)}
    buckets: dict[str, list[dict]] = {spec["id"]: [] for spec in LANE_SPECS}
    lane_for_slug = {}
    for lane in lanes or []:
        if not isinstance(lane, dict):
            continue
        lane_id = lane.get("id")
        for item in lane.get("items") or []:
            if isinstance(item, dict) and item.get("slug"):
                lane_for_slug[item["slug"]] = lane_id

    for slug, tool in tools.items():
        item = _item_from_tool(tool)
        track = item["track"]
        requested = lane_for_slug.get(slug)
        placed = False
        if requested in buckets and len(buckets[requested]) < _MAX_PER_LANE:
            buckets[requested].append(item)
            placed = True
        if not placed:
            for spec in LANE_SPECS:
                if track in spec["tracks"] and len(buckets[spec["id"]]) < _MAX_PER_LANE:
                    buckets[spec["id"]].append(item)
                    break

    built = _lanes_from_buckets(buckets)
    stack = JobStack(
        query=query,
        title=(title or _title_from_query(query))[:200],
        blurb=(blurb or f"A free-first stack for: {query}")[:400],
        cash_out=(cash_out or _cash_out(built))[:400],
        source="person",
        created_by=(
            created_by if getattr(created_by, "is_authenticated", False) else None
        ),
        lanes=built,
    )
    stack.save()
    return stack
