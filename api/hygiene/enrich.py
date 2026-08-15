"""Build a complete, grounded tool record from verified evidence.

Inputs are facts scraped from the tool's own site plus Google search
evidence. The model is only asked to organise and phrase that evidence --
never to recall a tool from memory -- so unknown tools fail loudly instead
of being confabulated.
"""

import json
import logging

from django.conf import settings
from openai import OpenAI, OpenAIError

from . import (
    MAX_TAGS,
    MIN_TAGS,
    TARGET_DESCRIPTION_WORDS,
    TARGET_SHORT_DESCRIPTION_WORDS,
)
from .taxonomy import ALL_TAGS, balance, dedupe, infer_tags
from .websearch import SearchEvidence

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """You write factual entries for a software tool directory.

You will be given evidence gathered from a tool's own website and from \
independent sources (Wikidata, Hacker News, and optionally a web search). \
Use ONLY that evidence. You have no other knowledge of the tool.

Rules:
- Never invent features, pricing, integrations, or customers.
- If the evidence is too thin to describe the tool, set "insufficient_evidence" \
to true and leave the other fields empty. This is expected and useful.
- No marketing language, superlatives, slogans, or "revolutionary"/"cutting-edge".
- Write plainly, in the third person, about what the tool does and who uses it.
- Choose tags ONLY from the provided allowed_tags list. Never invent a tag.

Return a single JSON object, no prose around it."""

RESPONSE_SHAPE = {
    "insufficient_evidence": "boolean",
    "short_description": f"string, {TARGET_SHORT_DESCRIPTION_WORDS[0]}-"
    f"{TARGET_SHORT_DESCRIPTION_WORDS[1]} words, no trailing period",
    "description": f"string, {TARGET_DESCRIPTION_WORDS[0]}-"
    f"{TARGET_DESCRIPTION_WORDS[1]} words",
    "tags": f"array of {MIN_TAGS}-{MAX_TAGS} strings from allowed_tags",
    "use_cases": "array of 3-5 short strings, each a concrete task",
    "features": "array of 3-6 short strings",
    "ideal_for": "array of 2-4 audience strings",
    "startup_benefits": "string, 1-2 sentences, or empty if unsupported",
    "pricing_type": "one of: free, freemium, paid",
    "confidence": "number 0-1, how well the evidence supports the entry",
}


def _client() -> OpenAI:
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _model_name() -> str:
    return getattr(settings, "HYGIENE_ENRICH_MODEL", DEFAULT_MODEL)


def build_evidence_payload(
    name: str,
    website: str,
    facts,
    search: SearchEvidence | None,
    candidate_tags: list[str],
    signals=None,
) -> dict:
    """Assemble everything the model is allowed to reason from."""
    payload = {
        "tool_name": name,
        "website": website,
        "site_title": getattr(facts, "title", None),
        "site_meta_description": getattr(facts, "meta_description", None),
        "site_text_excerpt": (getattr(facts, "source_text", "") or "")[:1500],
        "detected_pricing_hint": getattr(facts, "pricing", None),
        "github_stars": getattr(facts, "stars", None),
        "github_topics": getattr(facts, "topics", None) or [],
    }
    if search is not None:
        payload["google"] = {
            "official_site_confirmed": search.official_site_matched,
            "listed_in_directories": search.directory_hits,
            "result_titles": search.titles[:6],
            "result_snippets": search.snippets[:6],
        }
    if signals is not None:
        # Wikidata's description is written by people with no stake in the
        # product, which makes it the best non-marketing evidence available.
        payload["independent_sources"] = {
            "wikidata_description": signals.wikidata_description,
            "listed_on_wikidata": bool(signals.wikidata_id),
            "hacker_news_stories": signals.hn_story_count,
            "domain_popularity_rank": signals.tranco_rank,
        }
    payload["allowed_tags"] = list(ALL_TAGS)
    payload["suggested_tags"] = candidate_tags
    payload["response_shape"] = RESPONSE_SHAPE
    return payload


def _coerce_list(value, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out[:limit]


def enrich(
    name: str,
    website: str,
    facts,
    search: SearchEvidence | None = None,
    signals=None,
) -> dict:
    """Return an enriched record dict, or {'insufficient_evidence': True}."""
    seed_text = " ".join(
        filter(
            None,
            [
                name,
                getattr(facts, "title", "") or "",
                getattr(facts, "meta_description", "") or "",
                getattr(facts, "source_text", "") or "",
                " ".join((search.snippets if search else [])[:4]),
                getattr(signals, "wikidata_description", "") or "",
            ],
        )
    )
    candidate_tags = infer_tags(seed_text)
    payload = build_evidence_payload(
        name, website, facts, search, candidate_tags, signals
    )

    try:
        response = _client().chat.completions.create(
            model=_model_name(),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, default=str)},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=800,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except (OpenAIError, json.JSONDecodeError, IndexError) as exc:
        logger.warning("Enrichment failed for %s: %s", name, exc)
        return {"insufficient_evidence": True, "error": str(exc)}

    if data.get("insufficient_evidence"):
        return {"insufficient_evidence": True, "confidence": data.get("confidence", 0)}

    # Tags are the field most likely to drift, so validate hard and top up
    # from the deterministic inference rather than trusting the model.
    tags = balance(dedupe(_coerce_list(data.get("tags"), MAX_TAGS)))
    if len(tags) < MIN_TAGS:
        tags = balance(dedupe(tags + candidate_tags))

    pricing = str(data.get("pricing_type") or "").strip().lower()
    if pricing not in {"free", "freemium", "paid"}:
        pricing = ""

    return {
        "insufficient_evidence": False,
        "short_description": str(data.get("short_description") or "").strip(),
        "description": str(data.get("description") or "").strip(),
        "tags": tags,
        "use_cases": _coerce_list(data.get("use_cases"), 5),
        "features": _coerce_list(data.get("features"), 6),
        "ideal_for": _coerce_list(data.get("ideal_for"), 4),
        "startup_benefits": str(data.get("startup_benefits") or "").strip(),
        "pricing_type": pricing,
        "confidence": float(data.get("confidence") or 0),
    }
