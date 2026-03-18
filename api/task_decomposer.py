"""
Task Decomposer — Breaks macro goals into micro-task Tech Stack Recipes.

When a user says "I want to launch a podcast" or "automate my marketing",
this module breaks that goal into actionable micro-tasks and recommends
the best AI tool for each step.
"""

import json
import logging

from django.conf import settings
from django.core.cache import cache
from openai import OpenAI

from .smart_search import _cache_key, hybrid_search

logger = logging.getLogger(__name__)

DECOMPOSER_CACHE_TTL = 3600  # 1 hour

DECOMPOSE_SYSTEM_PROMPT = """You are an expert startup advisor and AI tools specialist.

Given a user's goal, break it into 3-6 specific, actionable micro-tasks that an AI tool could help accomplish.

Return valid JSON:
{
  "goal_summary": "A clean 1-sentence summary of the user's goal",
  "steps": [
    {
      "step": 1,
      "task": "Short task name (e.g., 'Audio Recording & Editing')",
      "description": "1-2 sentence explanation of this step",
      "search_query": "Optimized search query to find the best AI tool for this task"
    }
  ],
  "estimated_monthly_budget": "A rough estimate like '$0-50/mo' or 'Mostly free'",
  "time_to_setup": "Rough estimate like '1-2 hours' or '1 weekend'"
}

Rules:
- Each step should be a task an AI TOOL can help with, not a general business step.
- search_query should be specific enough to find AI tools (e.g., "AI podcast transcription tool" not just "transcription").
- Order steps logically (start to finish of the workflow).
- Focus on practical, actionable tasks that founders would actually need.
- Return ONLY valid JSON."""


def decompose_task(macro_goal):
    """
    Use GPT-4o-mini to break a macro goal into micro-tasks.
    Returns a structured dict with steps and search queries.
    """
    cache_k = _cache_key("decompose", macro_goal)
    cached = cache.get(cache_k)
    if cached:
        return cached

    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": DECOMPOSE_SYSTEM_PROMPT},
                {"role": "user", "content": macro_goal},
            ],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"},
        )

        text = response.choices[0].message.content.strip()
        decomposed = json.loads(text)

        # Validate structure
        decomposed.setdefault("goal_summary", macro_goal)
        decomposed.setdefault("steps", [])
        decomposed.setdefault("estimated_monthly_budget", "Varies")
        decomposed.setdefault("time_to_setup", "Varies")

        cache.set(cache_k, decomposed, DECOMPOSER_CACHE_TTL)
        logger.info(
            "Decomposed '%s' into %d steps", macro_goal, len(decomposed["steps"])
        )
        return decomposed

    except Exception as e:
        logger.warning("Task decomposition failed for '%s': %s", macro_goal, e)
        return {
            "goal_summary": macro_goal,
            "steps": [],
            "estimated_monthly_budget": "Unknown",
            "time_to_setup": "Unknown",
        }


def build_tech_stack_recipe(original_query, micro_tasks, filters=None, intent=None):
    """
    Build a full Tech Stack Recipe:
    1. Re-decompose with GPT for richer step info (if micro_tasks are thin)
    2. For each step, run hybrid_search to find the best tools
    3. Return a structured recipe response

    Args:
        original_query: The user's original query string
        micro_tasks: List of task strings from the intent parser
        filters: Optional dict of structured filters to apply globally
        intent: The full parsed intent dict
    """
    # Get the full decomposition with descriptions and search queries
    decomposed = decompose_task(original_query)

    # If decomposer gave us better steps, use those; otherwise build from micro_tasks
    if decomposed.get("steps"):
        steps = decomposed["steps"]
    else:
        steps = [
            {
                "step": i + 1,
                "task": task,
                "description": f"Find the best AI tool for {task}",
                "search_query": f"AI tool for {task}",
            }
            for i, task in enumerate(micro_tasks)
        ]

    # Run hybrid search for each micro-task
    recipe_steps = []
    all_recommended_tools = set()

    for step in steps:
        search_query = step.get("search_query", step.get("task", ""))

        # Run hybrid search with any global filters
        step_results = hybrid_search(
            semantic_query=search_query,
            filters=filters,
            top_k=3,  # Top 3 tools per step
            sort_by="relevance",
        )

        # Avoid recommending the same tool in multiple steps if possible
        unique_results = []
        for r in step_results:
            if r["id"] not in all_recommended_tools:
                unique_results.append(r)
                all_recommended_tools.add(r["id"])
            if len(unique_results) >= 3:
                break

        # If deduplication removed all results, fall back to original
        if not unique_results and step_results:
            unique_results = step_results[:2]

        # Add match context to each tool result
        for tool in unique_results:
            sim = tool.get("similarity", 0)
            reasons = []
            if sim >= 0.6:
                reasons.append("Best fit for this step")
            elif sim >= 0.4:
                reasons.append("Good fit")

            if tool.get("free_tier_available") or tool.get("pricing_type") == "free":
                reasons.append("Free to start")
            if tool.get("startup_friendly"):
                reasons.append("Startup-friendly")

            rating = float(tool.get("rating") or 0)
            if rating >= 4.0:
                reasons.append(f"{rating}★ rated")

            tool["match_reason"] = " · ".join(reasons) if reasons else "Relevant tool"

        recipe_steps.append(
            {
                "step": step.get("step", len(recipe_steps) + 1),
                "task": step.get("task", ""),
                "description": step.get("description", ""),
                "recommended_tools": unique_results,
                "tool_count": len(unique_results),
            }
        )

    return {
        "mode": "task_decomposition",
        "goal": decomposed.get("goal_summary", original_query),
        "parsed_intent": {
            "semantic_query": (
                intent.get("semantic_query", original_query)
                if intent
                else original_query
            ),
            "filters": {k: v for k, v in (filters or {}).items() if v},
            "explanation": intent.get("result_explanation", "") if intent else "",
        },
        "estimated_monthly_budget": decomposed.get(
            "estimated_monthly_budget", "Varies"
        ),
        "time_to_setup": decomposed.get("time_to_setup", "Varies"),
        "steps": recipe_steps,
        "total_steps": len(recipe_steps),
        "total_tools_recommended": len(all_recommended_tools),
    }
