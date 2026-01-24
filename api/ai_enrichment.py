import json
import re

import openai
from django.conf import settings

openai.api_key = settings.OPENAI_API_KEY


def enrich_tool_data(name, description, url=None):
    """Use AI to populate all tool fields from basic info"""

    prompt = f"""Analyze this tool and provide structured data:

Tool: {name}
Description: {description}
Website: {url or 'Not provided'}

Return JSON with:
{{
  "short_description": "50 char summary",
  "tags": ["tag1", "tag2", "tag3"],
  "use_cases": ["use case 1", "use case 2"],
  "features": ["feature 1", "feature 2"],
  "categories": ["category1", "category2"],
  "pricing_models": ["free", "freemium", "paid", "trial"],
  "pricing_tiers": [
    {{"name": "Basic", "price": 0, "billing": "monthly"}},
    {{"name": "Pro", "price": 20, "billing": "monthly"}}
  ],
  "pricing_from": 20.00,
  "platforms": ["web", "ios", "android", "desktop"],
  "integrations": ["tool1", "tool2"],
  "startup_benefits": "How this helps startups/founders",
  "ideal_for": ["early-stage", "bootstrapped", "SaaS"],
  "startup_friendly": true,
  "free_tier_available": true,
  "free_trial_days": 14
}}

Only return valid JSON.
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )

        # Extract JSON from response
        text = response.choices[0].message.content.strip()
        json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return data
        return {}
    except Exception as e:
        print(f"AI enrichment error: {e}")
        return {}
