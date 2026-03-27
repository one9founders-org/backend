import json
import logging

from django.conf import settings
from django.db.models import Q
from openai import OpenAI

logger = logging.getLogger(__name__)
openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

INTENT_SYSTEM_PROMPT = """You are a search assistant for an AI tools directory.
Parse the user's query into structured search intent.
Return ONLY valid JSON:
{
  "primary_intent": "short description of main need",
  "tasks": ["task1", "task2"],
  "categories": ["writing", "marketing", "code", "images", "video", \
"chatbots", "productivity", "design", "analytics"],
  "pricing_preference": "free" | "freemium" | "paid" | null,
  "keywords": ["keyword1", "keyword2", "keyword3"]
}
Rules: tasks max 3, categories only from allowed list, keywords 3-6 \
core terms, pricing_preference only if user explicitly mentions price."""


def parse_intent(query: str) -> dict:
    if not query or not query.strip():
        return {
            "keywords": [],
            "tasks": [],
            "categories": [],
            "primary_intent": query,
        }
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0.1,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content or "{}")
    except Exception as e:
        logger.warning("Intent parsing failed for '%s': %s", query, e)
        return {
            "primary_intent": query,
            "tasks": [query],
            "categories": [],
            "pricing_preference": None,
            "keywords": query.split()[:6],
        }


def smart_search(query: str, top_k: int = 20) -> list:
    if not query or not query.strip():
        return []

    intent = parse_intent(query)
    logger.info("Smart search: '%s' -> intent=%s", query, intent)

    results = []
    seen_ids: set = set()

    # Step 1: FAISS semantic search
    try:
        from api.faiss_search import FAISSSearchService

        service = FAISSSearchService.get_instance()
        enriched_query = " ".join(
            filter(
                None,
                [intent.get("primary_intent") or query]
                + (intent.get("keywords") or []),
            )
        )
        faiss_results = service.search(
            enriched_query, top_k=top_k, similarity_threshold=0.25
        )
        if faiss_results:
            for r in faiss_results:
                seen_ids.add(r["id"])
            results.extend(faiss_results)
    except Exception as e:
        logger.warning("FAISS step failed: %s", e)

    # Step 2: SQL text search fallback
    from api.models import Tool
    from api.serializers import ToolListSerializer

    search_terms = list(
        set(
            (intent.get("keywords") or [])
            + [t for t in (intent.get("tasks") or []) if len(t) < 50]
        )
    )
    if not search_terms:
        search_terms = [query]

    sql_filter = Q()
    for term in search_terms[:5]:
        sql_filter |= (
            Q(name__icontains=term)
            | Q(short_description__icontains=term)
            | Q(description__icontains=term)
            | Q(tags__icontains=term)
            | Q(use_cases__icontains=term)
        )

    sql_qs = (
        Tool.objects.filter(sql_filter, is_active=True)
        .exclude(id__in=seen_ids)
        .prefetch_related("categories")[:top_k]
    )
    sql_results = ToolListSerializer(sql_qs, many=True).data
    for r in sql_results:
        r["similarity"] = 0.1
        seen_ids.add(r["id"])
    results.extend(sql_results)

    # Step 3: Category filter from intent
    intent_categories = intent.get("categories") or []
    if intent_categories and len(results) > top_k // 2:
        category_filtered = [
            r
            for r in results
            if any(
                c.get("slug", "").lower() in intent_categories
                or c.get("name", "").lower() in intent_categories
                for c in r.get("categories", [])
            )
        ]
        if len(category_filtered) >= 3:
            results = category_filtered

    # Step 4: Pricing filter from intent
    pricing_pref = intent.get("pricing_preference")
    if pricing_pref:
        pricing_filtered = [
            r
            for r in results
            if r.get("pricing_type", "").lower() == pricing_pref.lower()
            or pricing_pref.lower() in [p.lower() for p in r.get("pricing_models", [])]
        ]
        if len(pricing_filtered) >= 3:
            results = pricing_filtered

    results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
    return results[:top_k]


DECOMPOSE_SYSTEM_PROMPT = """You are a search assistant for an AI tools \
directory.
Break a complex multi-step task into 2-4 sub-tasks, each needing a \
different type of AI tool.
Return ONLY valid JSON: {"tasks": [{"task": "description", \
"search_query": "short query"}, ...]}"""


def decompose_task(query: str) -> list:
    if not query or len(query) < 30:
        return [{"task": query, "tools": smart_search(query)}]
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": DECOMPOSE_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0.1,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(response.choices[0].message.content or "{}")
        tasks = parsed.get("tasks", [])
        if not tasks:
            return [{"task": query, "tools": smart_search(query)}]
        return [
            {
                "task": t.get("task", ""),
                "tools": smart_search(
                    t.get("search_query", t.get("task", "")), top_k=10
                ),
            }
            for t in tasks[:4]
        ]
    except Exception as e:
        logger.warning("Task decomposition failed: %s", e)
        return [{"task": query, "tools": smart_search(query)}]
