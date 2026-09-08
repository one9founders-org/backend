"""Hand-verified public facts for high-visibility directory listings.

AI enrichment used a 14-day trial in its example JSON, so featured tools such
as Claude were stored with a fake trial, placeholder integrations, and model
names as pricing tiers. These records overlay the API while the stored row is
stale, and `correct_verified_listings` writes the same facts to the database.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

# Official consumer plans (claude.ai), not API token prices.
# Sources checked 8 Sep 2026:
# - https://support.claude.com/en/articles/11049762-choose-a-claude-plan
# - https://support.claude.com/en/articles/8325606-what-is-the-pro-plan
# - https://support.claude.com/en/articles/11049741-what-is-the-max-plan
# - https://support.claude.com/en/articles/9266767-what-is-the-team-plan
CLAUDE_PLAN_SOURCE = (
    "https://support.claude.com/en/articles/11049762-choose-a-claude-plan"
)
CLAUDE_PRO_SOURCE = (
    "https://support.claude.com/en/articles/8325606-what-is-the-pro-plan"
)
CLAUDE_MAX_SOURCE = (
    "https://support.claude.com/en/articles/11049741-what-is-the-max-plan"
)
CLAUDE_TEAM_SOURCE = (
    "https://support.claude.com/en/articles/9266767-what-is-the-team-plan"
)
CLAUDE_API_PRICING_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"

CLAUDE_FIELDS = {
    "short_description": (
        "Anthropic's AI assistant for writing, coding, research, and Claude Code."
    ),
    "description": (
        "Claude is Anthropic's AI assistant for chat, writing, coding, research, "
        "and document analysis. Anyone in a supported location can use the "
        "permanent Free plan at claude.ai — that is an ongoing usage-limited "
        "plan, not a time-limited Pro trial. Anthropic does not advertise a "
        "standing free trial of Pro or Max; paid plans start at Pro "
        "($20/month or $200/year in the US), then Max 5x ($100/month) and "
        "Max 20x ($200/month). Team and Enterprise are separate organization "
        "plans. API usage is billed separately in the Claude Console and is "
        "not included in a claude.ai subscription."
    ),
    "pricing_type": "freemium",
    "pricing_models": ["freemium", "paid"],
    "pricing_from": Decimal("20.00"),
    "free_tier_available": True,
    "free_trial_days": None,
    "pricing_tiers": [
        {
            "name": "Free",
            "price": 0,
            "billing": "monthly",
            "note": (
                "Permanent plan with limited usage; session limits "
                "reset about every 5 hours."
            ),
            "source": CLAUDE_PLAN_SOURCE,
        },
        {
            "name": "Pro",
            "price": 20,
            "billing": "monthly",
            "note": (
                "$200/year. At least 5× Free usage per session. "
                "No standing Pro trial."
            ),
            "source": CLAUDE_PRO_SOURCE,
        },
        {
            "name": "Max 5x",
            "price": 100,
            "billing": "monthly",
            "note": "5× Pro usage per session. Monthly billing only.",
            "source": CLAUDE_MAX_SOURCE,
        },
        {
            "name": "Max 20x",
            "price": 200,
            "billing": "monthly",
            "note": "20× Pro usage per session. Monthly billing only.",
            "source": CLAUDE_MAX_SOURCE,
        },
        {
            "name": "Team Standard",
            "price": 25,
            "billing": "monthly",
            "note": (
                "Min 2 seats. $20/member/month if billed annually. " "API not included."
            ),
            "source": CLAUDE_TEAM_SOURCE,
        },
    ],
    "startup_benefits": (
        "Start on the permanent Free plan at claude.ai with no credit card and "
        "no trial expiry. Upgrade to Pro at $20/month when you need more usage, "
        "Claude Code, or priority access. Anthropic does not offer a standing "
        "discount or Pro trial on request. API tokens are a separate Console bill."
    ),
    "features": [
        "Claude Code:: Agentic coding in the terminal and IDEs on Pro and Max.",
        "Long context:: Current Claude models offer up to 1M-token "
        "context on supported SKUs.",
        "Artifacts:: Interactive docs, code, and visuals generated in chat.",
        "Projects:: Persistent files and instructions for ongoing work.",
        "Vision:: Read images, PDFs, and other documents in conversation.",
    ],
    "platforms": ["web", "desktop", "ios", "android"],
    "integrations": ["Google Drive", "Gmail", "Slack", "GitHub", "MCP"],
    "use_cases": [
        "Writing, editing, and research",
        "Software development with Claude Code",
        "Analyzing documents, spreadsheets, and images",
        "Day-to-day Q&A for founders and operators",
    ],
    "ideal_for": ["founders", "developers", "researchers", "bootstrapped"],
    "tags": ["AI Assistant", "Writing", "Coding", "Anthropic", "Claude Code"],
    "startup_friendly": True,
}


def claude_is_stale(tool) -> bool:
    """True when the stored Claude row still has enrichment leftovers."""
    models = [str(m).lower() for m in (tool.pricing_models or [])]
    tiers = tool.pricing_tiers or []
    tier_names = {str(t.get("name", "")).lower() for t in tiers if isinstance(t, dict)}
    integrations = [str(i).lower() for i in (tool.integrations or [])]
    try:
        pricing_from = (
            float(tool.pricing_from) if tool.pricing_from is not None else None
        )
    except (TypeError, ValueError):
        pricing_from = None
    return bool(
        tool.free_trial_days == 14
        or "trial" in models
        or integrations == ["tool1", "tool2"]
        or "opus 4.5" in tier_names
        or "sonnet 4.5" in tier_names
        or "haiku 4.5" in tier_names
        or pricing_from == 0
    )


VERIFIED_LISTINGS = {
    "claude": {
        "name": "Claude",
        "fields": CLAUDE_FIELDS,
        "stale_if": claude_is_stale,
    }
}


def fields_for_stale_tool(tool) -> dict | None:
    listing = VERIFIED_LISTINGS.get(getattr(tool, "slug", "") or "")
    if not listing:
        return None
    stale_if = listing.get("stale_if")
    if stale_if and not stale_if(tool):
        return None
    return listing["fields"]


def overlay_verified_listing(
    instance, data: dict, exchange_rate: float = 83.5, gst_rate: float = 0.18
) -> dict:
    """Patch a serializer payload when the stored row is still stale."""
    patch = fields_for_stale_tool(instance)
    if not patch:
        return data
    for key, value in patch.items():
        if key in data:
            if key == "pricing_from" and value is not None:
                data[key] = f"{Decimal(value):.2f}"
            else:
                data[key] = value
    if "pricing_from" in patch and "pricing_inr" in data:
        price = patch["pricing_from"]
        if price:
            inr = round(float(price) * exchange_rate)
            data["pricing_inr"] = inr
            gst_on = data.get("gst_applicable")
            if gst_on is None:
                gst_on = getattr(instance, "gst_applicable", True)
            data["pricing_inr_with_gst"] = (
                round(inr * (1 + gst_rate)) if gst_on else inr
            )
        else:
            data["pricing_inr"] = None
            data["pricing_inr_with_gst"] = None
    return data


def persist_verified_listings(*, apply: bool) -> list[dict]:
    """Dry-run or write verified fields. Returns per-slug reports."""
    from api.models import Tool

    reports = []
    for slug, listing in VERIFIED_LISTINGS.items():
        tool = Tool.objects.filter(slug=slug).first()
        if tool is None:
            reports.append({"slug": slug, "status": "missing"})
            continue
        stale = listing["stale_if"](tool) if listing.get("stale_if") else True
        report = {
            "slug": slug,
            "status": "stale" if stale else "already_current",
            "before": {
                "free_trial_days": tool.free_trial_days,
                "pricing_from": (
                    str(tool.pricing_from) if tool.pricing_from is not None else None
                ),
                "pricing_models": tool.pricing_models,
            },
        }
        if apply and stale:
            fields = dict(listing["fields"])
            Tool.objects.filter(pk=tool.pk).update(**fields, updated_at=timezone.now())
            report["status"] = "updated"
        reports.append(report)
    return reports
