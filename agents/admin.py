from django.contrib import admin

from .models import AgentCategory, AIAgent


@admin.register(AgentCategory)
class AgentCategoryAdmin(admin.ModelAdmin):
    list_display = ["label", "agent_count", "growth_rate", "new_agents_30d"]
    ordering = ["-agent_count"]
    search_fields = ["label", "slug"]


@admin.register(AIAgent)
class AIAgentAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "category_name",
        "pricing_model",
        "access",
        "popularity_score",
        "views",
        "upvotes",
        "is_featured",
    ]
    list_filter = ["category", "pricing_model", "access", "is_featured"]
    search_fields = ["name", "short_description"]
    readonly_fields = [
        "popularity_score",
        "upvotes",
        "views",
        "bookmark_count",
        "review_count",
        "average_rating",
        "views_24h",
        "views_7d",
        "views_30d",
        "upvotes_24h",
        "upvotes_7d",
        "upvotes_30d",
    ]
    raw_id_fields = ["category"]
