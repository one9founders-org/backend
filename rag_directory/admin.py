from django.contrib import admin

from .models import GitHubSnapshot, RagTool


@admin.register(RagTool)
class RagToolAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "category",
        "pricing_model",
        "overall_rating",
        "github_stars",
        "status",
        "featured",
    ]
    list_filter = ["category", "pricing_model", "status", "featured"]
    search_fields = ["name", "description"]
    prepopulated_fields = {"slug": ("name",)}
    ordering = ["-overall_rating", "-github_stars"]
    list_editable = ["featured", "status"]


@admin.register(GitHubSnapshot)
class GitHubSnapshotAdmin(admin.ModelAdmin):
    list_display = ["tool", "stars", "forks", "open_issues", "snapshot_date"]
    list_filter = ["snapshot_date"]
    search_fields = ["tool__name"]
    ordering = ["-snapshot_date"]
