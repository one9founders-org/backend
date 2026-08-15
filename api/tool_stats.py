from django.core.cache import cache
from django.db.models import Count, F

from .hygiene.visibility import publishable_queryset
from .models import Tool

TOOL_STATS_CACHE_KEY = "tool_stats"
TOOL_STATS_CACHE_TIMEOUT = 3600


def bust_tool_stats_cache():
    cache.delete(TOOL_STATS_CACHE_KEY)


def compute_tool_directory_stats():
    """Each value is one aggregate query — no per-row Python loops."""
    qs = publishable_queryset()
    by_category = list(
        qs.filter(categories__isnull=False)
        .values(category=F("categories__name"))
        .annotate(count=Count("id", distinct=True))
        .order_by("-count", "category")
    )
    return {
        "count": qs.count(),
        "fully_assessed_count": qs.filter(criteria_completed=10).count(),
        "provisionally_assessed_count": qs.filter(
            criteria_completed__gte=6, criteria_completed__lt=10
        ).count(),
        "total_tools": Tool.objects.count(),
        "by_category": by_category,
    }


def get_tool_directory_stats():
    return cache.get_or_set(
        TOOL_STATS_CACHE_KEY,
        compute_tool_directory_stats,
        TOOL_STATS_CACHE_TIMEOUT,
    )
