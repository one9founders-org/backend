"""
Smart Search Engine — AI Intent Parsing + Hybrid FAISS Search

Upgrades the basic FAISS similarity search into an intelligent,
filter-aware, intent-understanding search engine.
"""

import hashlib
import json
import logging

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from openai import OpenAI

logger = logging.getLogger(__name__)

INTENT_CACHE_TTL = 3600  # 1 hour
SEARCH_CACHE_TTL = 1800  # 30 minutes


# 1. AI Intent Parser
INTENT_SYSTEM_PROMPT = (
    "You are a search-intent parser for an AI tool discovery platform"
    " used by founders and entrepreneurs.\n\n"
    "Given a user's natural-language query, extract structured search intent.\n\n"
    "You MUST return valid JSON with these exact keys:\n"
    "{\n"
    '  "semantic_query": "a clean, rephrased search string optimized'
    ' for semantic similarity matching",\n'
    '  "filters": {\n'
    '    "max_price": null or number (e.g. 20),\n'
    '    "min_price": null or number,\n'
    '    "pricing_type": [] (subset of ["free", "freemium", "paid"]),\n'
    '    "categories": [] (category slugs relevant to the query),\n'
    '    "startup_friendly": null or true,\n'
    '    "min_rating": null or number (1-5),\n'
    '    "platforms": [] (subset of ["web", "ios", "android", "desktop", "api"]),\n'
    '    "has_free_trial": null or true\n'
    "  },\n"
    '  "mode": "search" or "task_decomposition",\n'
    '  "micro_tasks": [],\n'
    '  "sort_by": "relevance" or "price_low" or "price_high"'
    ' or "rating" or "popularity",\n'
    '  "result_explanation": "a one-line summary of'
    ' what was understood from the query"\n'
    "}\n\n"
    "Rules:\n"
    '- If the query describes a specific GOAL or WORKFLOW (e.g. "launch a podcast",'
    ' "automate my marketing", "build a SaaS"), set mode to "task_decomposition"'
    " and populate micro_tasks with 3-6 actionable sub-tasks.\n"
    '- If the query is a direct tool search (e.g. "best SEO tool",'
    ' "cheap writing assistant"), set mode to "search" and leave micro_tasks empty.\n'
    "- Always populate semantic_query with a clear, descriptive search phrase.\n"
    "- Only set filter values when the user EXPLICITLY mentions them. Do not guess.\n"
    '- For pricing_type: "free" = completely free,'
    ' "freemium" = has free tier + paid plans, "paid" = paid only.\n'
    "- Return ONLY valid JSON, no markdown, no explanation."
)


def _cache_key(prefix, query):
    """Generate a short, safe cache key from a query string."""
    h = hashlib.md5(query.lower().strip().encode()).hexdigest()[:12]  # nosec B324
    return f"smart_search:{prefix}:{h}"


def parse_search_intent(query):
    """
    Use GPT-4o-mini to parse a natural-language query into structured intent.

    Returns a dict with semantic_query, filters, mode, micro_tasks, etc.
    Falls back to a basic intent if the API call fails.
    """
    cache_k = _cache_key("intent", query)
    cached = cache.get(cache_k)
    if cached:
        logger.debug("Intent cache hit for: %s", query)
        return cached

    fallback_intent = {
        "semantic_query": query,
        "filters": {},
        "mode": "search",
        "micro_tasks": [],
        "sort_by": "relevance",
        "result_explanation": f'Showing results for "{query}"',
    }

    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0.1,
            max_tokens=500,
            response_format={"type": "json_object"},
        )

        text = response.choices[0].message.content.strip()
        intent = json.loads(text)

        # Validate required keys
        if "semantic_query" not in intent or not intent["semantic_query"]:
            intent["semantic_query"] = query
        intent.setdefault("filters", {})
        intent.setdefault("mode", "search")
        intent.setdefault("micro_tasks", [])
        intent.setdefault("sort_by", "relevance")
        intent.setdefault("result_explanation", f'Results for "{query}"')

        cache.set(cache_k, intent, INTENT_CACHE_TTL)
        logger.info("Parsed intent for '%s': mode=%s", query, intent["mode"])
        return intent

    except Exception as e:
        logger.warning("Intent parsing failed for '%s': %s", query, e)
        return fallback_intent


# 2. Hybrid Search (ORM Filters + FAISS Ranking)


def _apply_orm_filters(queryset, filters):
    """Apply structured filters to a Tool queryset before FAISS ranking."""
    if not filters:
        return queryset

    max_price = filters.get("max_price")
    if max_price is not None:
        queryset = queryset.filter(
            Q(pricing_from__lte=max_price) | Q(pricing_from__isnull=True)
        )

    min_price = filters.get("min_price")
    if min_price is not None:
        queryset = queryset.filter(pricing_from__gte=min_price)

    pricing_types = filters.get("pricing_type", [])
    if pricing_types:
        queryset = queryset.filter(pricing_type__in=pricing_types)

    categories = filters.get("categories", [])
    if categories:
        queryset = queryset.filter(
            Q(categories__slug__in=categories)
            | Q(categories__name__icontains=categories[0])
        )

    if filters.get("startup_friendly"):
        queryset = queryset.filter(startup_friendly=True)

    min_rating = filters.get("min_rating")
    if min_rating is not None:
        queryset = queryset.filter(rating__gte=min_rating)

    platforms = filters.get("platforms", [])
    if platforms:
        for platform in platforms:
            queryset = queryset.filter(platforms__contains=[platform])

    if filters.get("has_free_trial"):
        queryset = queryset.filter(free_trial_days__isnull=False, free_trial_days__gt=0)

    return queryset.distinct()


def hybrid_search(semantic_query, filters=None, top_k=20, sort_by="relevance"):
    """
    Perform a hybrid search:
    1. Apply ORM filters to narrow the candidate pool
    2. Use FAISS to rank candidates by semantic relevance
    3. Return enriched results sorted by the requested criteria
    """
    from .faiss_search import FAISSSearchService
    from .models import Tool
    from .serializers import ToolListSerializer

    # Step 1: Get filtered tool IDs from ORM
    filtered_qs = Tool.objects.filter(is_active=True).prefetch_related("categories")
    if filters:
        filtered_qs = _apply_orm_filters(filtered_qs, filters)
    allowed_ids = set(filtered_qs.values_list("id", flat=True))

    # Step 2: Run FAISS search for semantic ranking
    service = FAISSSearchService.get_instance()
    faiss_results = None

    try:
        faiss_results = service.search(
            semantic_query, top_k=top_k * 3, similarity_threshold=0.25
        )
    except Exception as e:
        logger.warning("FAISS search failed in hybrid_search: %s", e)

    if faiss_results is not None:
        # Intersect FAISS results with ORM-filtered IDs
        ranked_results = [r for r in faiss_results if r["id"] in allowed_ids][:top_k]
    else:
        # Fallback: text search within filtered queryset
        tools = filtered_qs.filter(
            Q(name__icontains=semantic_query)
            | Q(description__icontains=semantic_query)
            | Q(tags__icontains=semantic_query)
            | Q(short_description__icontains=semantic_query)
        )[:top_k]
        serializer = ToolListSerializer(tools, many=True)
        ranked_results = serializer.data

    # Step 3: Apply sorting
    if sort_by == "price_low":
        ranked_results.sort(key=lambda x: float(x.get("pricing_from") or 9999))
    elif sort_by == "price_high":
        ranked_results.sort(
            key=lambda x: float(x.get("pricing_from") or 0), reverse=True
        )
    elif sort_by == "rating":
        ranked_results.sort(key=lambda x: float(x.get("rating") or 0), reverse=True)
    elif sort_by == "popularity":
        ranked_results.sort(key=lambda x: int(x.get("views_count") or 0), reverse=True)
    # else: keep FAISS relevance order (default)

    return ranked_results


# 3. Smart Search Orchestrator


def smart_search_orchestrator(query, top_k=20):
    """
    Main entry point for smart search.
    1. Parse user intent with GPT-4o-mini
    2. Route to either hybrid_search or task_decomposition
    3. Return a unified response envelope
    """
    from .task_decomposer import build_tech_stack_recipe

    # Check full-response cache first
    cache_k = _cache_key("result", query)
    cached_result = cache.get(cache_k)
    if cached_result:
        logger.debug("Full result cache hit for: %s", query)
        return cached_result

    # Step 1: Parse intent
    intent = parse_search_intent(query)
    mode = intent.get("mode", "search")
    filters = intent.get("filters", {})
    semantic_query = intent.get("semantic_query", query)
    sort_by = intent.get("sort_by", "relevance")

    if mode == "task_decomposition" and intent.get("micro_tasks"):
        # Step 2a: Task decomposition mode
        result = build_tech_stack_recipe(
            original_query=query,
            micro_tasks=intent["micro_tasks"],
            filters=filters,
            intent=intent,
        )
    else:
        # Step 2b: Standard search mode
        results = hybrid_search(
            semantic_query=semantic_query,
            filters=filters,
            top_k=top_k,
            sort_by=sort_by,
        )

        # Generate match reasons for top results
        results = _enrich_with_match_reasons(results, semantic_query, filters)

        result = {
            "mode": "search",
            "parsed_intent": {
                "semantic_query": semantic_query,
                "filters": {k: v for k, v in filters.items() if v},
                "sort_by": sort_by,
                "explanation": intent.get("result_explanation", ""),
            },
            "results": results,
            "total_results": len(results),
            "suggestions": _generate_search_suggestions(query, results),
        }

    cache.set(cache_k, result, SEARCH_CACHE_TTL)
    return result


# 4. Result Enrichment Helpers


def _enrich_with_match_reasons(results, semantic_query, filters):
    """Add a human-readable match_reason to each result based on why it ranked."""
    for result in results:
        reasons = []

        # Similarity-based reason
        sim = result.get("similarity", 0)
        if sim >= 0.7:
            reasons.append("Highly relevant match")
        elif sim >= 0.5:
            reasons.append("Strong match")
        elif sim >= 0.3:
            reasons.append("Related match")

        # Pricing-based reason
        if filters.get("max_price"):
            pricing_from = result.get("pricing_from")
            if pricing_from is not None and float(pricing_from) == 0:
                reasons.append("Completely free")
            elif result.get("free_tier_available"):
                reasons.append("Free tier available")
            elif result.get("pricing_type") == "freemium":
                reasons.append("Has free plan")

        # Startup-specific reason
        if result.get("startup_friendly"):
            reasons.append("Startup-friendly pricing")

        # Rating reason
        rating = float(result.get("rating") or 0)
        if rating >= 4.5:
            reasons.append(f"Top rated ({rating}★)")
        elif rating >= 4.0:
            reasons.append(f"Highly rated ({rating}★)")

        # Verified badge
        if result.get("verified"):
            reasons.append("Verified tool")

        result["match_reason"] = (
            " · ".join(reasons) if reasons else "Relevant to your search"
        )
        result["relevance_score"] = round(sim, 3) if sim else None

    return results


def _generate_search_suggestions(query, results):
    """Generate helpful follow-up suggestions based on the results."""
    suggestions = []

    if len(results) == 0:
        suggestions.append("Try broadening your search with fewer filters")
        suggestions.append("Try describing what task you want to accomplish")
    elif len(results) < 5:
        suggestions.append("Try a broader search term for more options")

    # Suggest task decomposition if the query looks like a goal
    goal_words = [
        "want to",
        "need to",
        "how to",
        "launch",
        "build",
        "create",
        "start",
        "automate",
        "grow",
    ]
    if any(w in query.lower() for w in goal_words) and len(results) > 0:
        suggestions.append(
            "Tip: Try phrasing as a goal"
            " (e.g., 'I want to automate my email marketing')"
            " for a step-by-step tool recommendation"
        )

    return suggestions
