import json
import logging
import re

from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)

PLACEHOLDER_ITEM_RE = re.compile(
    r"^(tool|integration|item|example|tag|feature)\s*\d+$", re.I
)


def sanitize_enriched(data):
    """Drop copied example values from an enrichment JSON blob."""
    if not isinstance(data, dict):
        return {}

    cleaned = dict(data)
    for key in (
        "tags",
        "use_cases",
        "features",
        "platforms",
        "integrations",
        "ideal_for",
    ):
        values = cleaned.get(key)
        if not isinstance(values, list):
            continue
        cleaned[key] = [
            item
            for item in values
            if isinstance(item, str)
            and item.strip()
            and not PLACEHOLDER_ITEM_RE.match(item.strip())
        ]

    trial = cleaned.get("free_trial_days")
    if trial in (None, "", 0, "0", "null"):
        cleaned["free_trial_days"] = None
    else:
        try:
            days = int(trial)
            cleaned["free_trial_days"] = days if days > 0 else None
        except (TypeError, ValueError):
            cleaned["free_trial_days"] = None

    models = cleaned.get("pricing_models")
    if isinstance(models, list) and cleaned.get("free_trial_days") is None:
        cleaned["pricing_models"] = [m for m in models if str(m).lower() != "trial"]

    return cleaned


def enrich_tool_data(name, description, url=None):
    """Use AI to populate all tool fields from basic info"""

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    prompt = f"""Analyze this tool and provide structured data:

Tool: {name}
Description: {description}
Website: {url or 'Not provided'}

Return JSON with this shape (values are illustrative — do not copy
them unless they are true for this tool):
{{
  "short_description": "50 char summary",
  "tags": ["tag1", "tag2", "tag3"],
  "use_cases": ["use case 1", "use case 2"],
  "features": ["feature 1", "feature 2"],
  "categories": ["category1", "category2"],
  "pricing_models": ["freemium", "paid"],
  "pricing_tiers": [
    {{"name": "Free", "price": 0, "billing": "monthly"}},
    {{"name": "Pro", "price": 20, "billing": "monthly"}}
  ],
  "pricing_from": 20.00,
  "platforms": ["web", "ios", "android", "desktop"],
  "integrations": [],
  "startup_benefits": "How this helps startups/founders",
  "ideal_for": ["early-stage", "bootstrapped", "SaaS"],
  "startup_friendly": true,
  "free_tier_available": true,
  "free_trial_days": null
}}

Rules:
- A permanent free plan is free_tier_available=true and free_trial_days=null.
- Only set free_trial_days to a positive integer when the vendor
  publishes a numbered trial (for example 7 or 30 days).
- Do not invent a trial length.
- Never use placeholder values such as tool1, tool2, tag1, or example.com.
- If a field is unknown, use null or [].
- pricing_tiers must be plan names (Free, Pro, Team), not model names.

Only return valid JSON.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )

        # Extract JSON from response
        text = response.choices[0].message.content.strip()
        json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return sanitize_enriched(data)
        return {}
    except Exception as e:
        logger.warning("AI enrichment error: %s", e)
        return {}
