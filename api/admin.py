from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .models import (
    Category,
    Deal,
    News,
    NewsletterSubscription,
    Review,
    Tool,
    ToolSubmission,
    User,
    UserFavorite,
)


class ToolResource(resources.ModelResource):
    class Meta:
        model = Tool
        exclude = ("embedding",)


class ReviewResource(resources.ModelResource):
    class Meta:
        model = Review


class DealResource(resources.ModelResource):
    class Meta:
        model = Deal


class NewsletterResource(resources.ModelResource):
    class Meta:
        model = NewsletterSubscription


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["email", "username", "first_name", "last_name", "is_active"]
    search_fields = ["email", "username"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "created_at"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Tool)
class ToolAdmin(ImportExportModelAdmin):
    resource_class = ToolResource
    list_display = [
        "name",
        "rating",
        "review_count",
        "is_featured",
        "startup_friendly",
        "is_active",
    ]
    list_filter = [
        "is_active",
        "is_featured",
        "verified",
        "startup_friendly",
        "categories",
    ]
    search_fields = ["name", "description", "tags"]
    filter_horizontal = ["categories", "alternatives"]


@admin.register(Review)
class ReviewAdmin(ImportExportModelAdmin):
    resource_class = ReviewResource
    list_display = ["tool", "user_name", "rating", "created_at"]
    list_filter = ["rating", "verified_purchase"]
    search_fields = ["user_name", "title", "comment"]


@admin.register(Deal)
class DealAdmin(ImportExportModelAdmin):
    resource_class = DealResource
    list_display = [
        "tool",
        "offer_title",
        "discount_percentage",
        "expiry_date",
        "claims_count",
        "featured_deal",
        "is_active",
    ]
    list_filter = ["featured_deal", "is_active", "expiry_date"]
    search_fields = ["tool__name", "offer_title"]
    readonly_fields = ["claims_count", "created_at", "updated_at"]


@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "author",
        "category",
        "reading_time",
        "is_published",
        "is_featured",
        "published_at",
    ]
    list_filter = ["is_published", "is_featured", "category"]
    search_fields = ["title", "content", "excerpt"]
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ["related_tools"]
    readonly_fields = ["reading_time", "views_count", "created_at", "updated_at"]


@admin.register(NewsletterSubscription)
class NewsletterSubscriptionAdmin(ImportExportModelAdmin):
    resource_class = NewsletterResource
    list_display = ["email", "source", "is_active", "created_at"]
    list_filter = ["is_active", "source"]


@admin.register(ToolSubmission)
class ToolSubmissionAdmin(admin.ModelAdmin):
    list_display = ["name", "submitter_name", "submitter_email", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["name", "submitter_email", "submitter_name"]
    readonly_fields = ["enriched_data", "created_at", "updated_at"]
    filter_horizontal = ["categories"]
    actions = ["approve_submissions"]

    def approve_submissions(self, request, queryset):
        for submission in queryset.filter(status="pending"):
            submission.approve_and_create_tool()
        self.message_user(request, f"{queryset.count()} submissions approved")

    approve_submissions.short_description = "Approve selected submissions"


admin.site.register(UserFavorite)
