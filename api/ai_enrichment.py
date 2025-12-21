import google.generativeai as genai
from django.conf import settings
import json
import re

genai.configure(api_key=settings.GEMINI_API_KEY)

def enrich_tool_data(name, description, url=None):
    """Use AI with Google Search to populate all tool fields from basic info"""
    
    prompt = f"""Search the web for information about {name} ({url or ''}) and provide accurate, up-to-date data.

Tool: {name}
Description: {description}

Return JSON with:
{{
  "short_description": "50 char summary",
  "tags": ["tag1", "tag2", "tag3"],
  "use_cases": ["use case 1", "use case 2"],
  "features": ["feature 1", "feature 2"],
  "categories": ["category1", "category2"],
  "pricing_model": "free/freemium/paid/trial",
  "pricing_from": 20.00,
  "platforms": ["web", "ios", "android", "desktop"],
  "integrations": ["tool1", "tool2"],
  "startup_benefits": "How this helps startups/founders",
  "ideal_for": ["early-stage", "bootstrapped", "SaaS"],
  "startup_friendly": true
}}

Only return valid JSON.
"""
    
    try:
        model = genai.GenerativeModel(
            'gemini-2.0-flash-exp',
            tools='google_search_retrieval'
        )
        response = model.generate_content(prompt)
        
        # Extract JSON from response
        text = response.text.strip()
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return data
        return {}
    except Exception as e:
        print(f"AI enrichment error: {e}")
        return {}
