from django.contrib import admin

from .models import Author, Paper


@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    list_display = [
        "arxiv_id",
        "title_short",
        "published_at",
        "hf_upvotes",
        "is_enriched",
        "is_trending",
    ]
    list_filter = ["is_enriched", "is_trending", "ai_difficulty"]
    search_fields = ["title", "arxiv_id", "abstract"]
    ordering = ["-published_at"]
    list_editable = ["is_trending"]
    readonly_fields = ["created_at"]

    def title_short(self, obj):
        return obj.title[:80] + "..." if len(obj.title) > 80 else obj.title

    title_short.short_description = "Title"


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ["name", "paper_count", "first_seen", "last_seen"]
    search_fields = ["name"]
    ordering = ["-paper_count"]
