from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .models import (
    Category,
    Deal,
    Guide,
    Lab,
    News,
    NewsletterSubscription,
    NewsUpvote,
    Review,
    Tool,
    ToolSubmission,
    User,
    UserFavorite,
    Workshop,
)
from .pipeline_models import (
    NewsDraft,
    PipelineConfig,
    PipelineRun,
    PublishedArticle,
    QualifiedNewsItem,
    ScrapedItem,
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
    filter_horizontal = ["categories"]
    raw_id_fields = ["alternatives"]
    exclude = ["embedding"]


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
class NewsAdmin(SummernoteModelAdmin):
    summernote_fields = ("content",)
    list_display = [
        "title",
        "author",
        "category",
        "reading_time",
        "upvote_count",
        "views_count",
        "is_published",
        "is_featured",
        "published_at",
    ]
    list_filter = ["is_published", "is_featured", "category"]
    search_fields = ["title", "content", "excerpt"]
    prepopulated_fields = {"slug": ("title",)}
    raw_id_fields = ["related_tools"]
    readonly_fields = [
        "reading_time",
        "views_count",
        "upvote_count",
        "created_at",
        "updated_at",
    ]


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


# Pipeline Models Admin
@admin.register(ScrapedItem)
class ScrapedItemAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "source",
        "status",
        "scraped_at",
        "scrape_batch_id",
    ]
    list_filter = ["source", "status", "scraped_at"]
    search_fields = ["title", "description", "source_url"]
    readonly_fields = ["content_hash", "scraped_at", "processed_at"]
    date_hierarchy = "scraped_at"


@admin.register(QualifiedNewsItem)
class QualifiedNewsItemAdmin(admin.ModelAdmin):
    list_display = [
        "get_title",
        "relevance_score",
        "founder_relevance",
        "practical_impact",
        "novelty_score",
        "status",
        "created_at",
    ]
    list_filter = ["status", "scoring_model", "created_at"]
    search_fields = ["scraped_item__title", "scoring_rationale"]
    readonly_fields = ["created_at", "updated_at"]
    raw_id_fields = ["scraped_item"]

    def get_title(self, obj):
        return obj.scraped_item.title[:50]

    get_title.short_description = "Title"


@admin.register(NewsDraft)
class NewsDraftAdmin(SummernoteModelAdmin):
    summernote_fields = ("content",)
    list_display = [
        "title",
        "category",
        "status",
        "scheduled_for",
        "created_at",
    ]
    list_filter = ["status", "category", "created_at"]
    search_fields = ["title", "content", "excerpt"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["created_at", "updated_at", "published_at"]
    raw_id_fields = ["qualified_item"]
    actions = ["publish_drafts"]

    def publish_drafts(self, request, queryset):
        """Publish selected drafts to the News model."""
        from .pipeline_engine import PipelineEngine
        from .pipeline_models import PipelineConfig

        if not PipelineConfig.is_publishing_enabled():
            self.message_user(
                request,
                "Publishing is disabled. Enable it in Pipeline Config first.",
                level="error",
            )
            return

        engine = PipelineEngine()
        published_count = 0
        failed_count = 0

        for draft in queryset.filter(status__in=["generated", "ready", "editing"]):
            slot, _ = engine.get_next_publish_slot()
            result = engine.publish_draft(draft, slot)
            if result:
                published_count += 1
            else:
                failed_count += 1

        if published_count > 0:
            self.message_user(
                request, f"Successfully published {published_count} article(s)."
            )
        if failed_count > 0:
            self.message_user(
                request,
                f"Failed to publish {failed_count} article(s).",
                level="warning",
            )

    publish_drafts.short_description = "Publish selected drafts to News"


@admin.register(PublishedArticle)
class PublishedArticleAdmin(admin.ModelAdmin):
    list_display = [
        "get_title",
        "source",
        "relevance_score",
        "publish_slot",
        "views_count",
        "published_at",
    ]
    list_filter = ["source", "published_at"]
    search_fields = ["news__title"]
    readonly_fields = ["published_at", "views_count", "engagement_score"]
    raw_id_fields = ["draft", "news"]
    date_hierarchy = "published_at"

    def get_title(self, obj):
        return obj.news.title[:50]

    get_title.short_description = "Title"


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = [
        "batch_id",
        "run_type",
        "status",
        "source",
        "items_processed",
        "items_succeeded",
        "items_failed",
        "started_at",
        "duration_seconds",
    ]
    list_filter = ["run_type", "status", "source", "started_at"]
    search_fields = ["batch_id", "error_message"]
    readonly_fields = [
        "started_at",
        "completed_at",
        "duration_seconds",
        "logs",
    ]
    date_hierarchy = "started_at"


@admin.register(PipelineConfig)
class PipelineConfigAdmin(admin.ModelAdmin):
    list_display = ["key", "value", "updated_at", "updated_by"]
    search_fields = ["key", "description"]
    readonly_fields = ["updated_at"]


@admin.register(NewsUpvote)
class NewsUpvoteAdmin(admin.ModelAdmin):
    list_display = ["news", "user", "session_id", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["news__title", "user__username", "session_id"]
    readonly_fields = ["created_at"]
    raw_id_fields = ["news", "user"]


# --- Learning Content Admin ---


class LearningContentAdmin(SummernoteModelAdmin):
    """Base admin for Guide, Lab, and Workshop models."""

    summernote_fields = ("content",)
    list_display = [
        "title",
        "difficulty",
        "category",
        "audience",
        "pricing",
        "is_published",
        "is_featured",
        "last_updated",
        "published_at",
    ]
    list_filter = [
        "is_published",
        "is_featured",
        "difficulty",
        "category",
        "audience",
        "pricing",
    ]
    search_fields = ["title", "short_description", "content"]
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ["tools_used"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "title",
                    "slug",
                    "short_description",
                    "content",
                    "featured_image",
                    "author",
                )
            },
        ),
        (
            "Classification",
            {
                "fields": (
                    "difficulty",
                    "estimated_time",
                    "category",
                    "audience",
                    "tools_used",
                )
            },
        ),
        (
            "Pricing",
            {
                "fields": ("pricing", "price_amount"),
                "classes": ("collapse",),
            },
        ),
        (
            "SEO",
            {
                "fields": ("meta_title", "meta_description"),
                "classes": ("collapse",),
            },
        ),
        (
            "Status & Dates",
            {
                "fields": (
                    "is_published",
                    "is_featured",
                    "last_updated",
                    "published_at",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


@admin.register(Guide)
class GuideAdmin(LearningContentAdmin):
    pass


@admin.register(Lab)
class LabAdmin(LearningContentAdmin):
    pass


@admin.register(Workshop)
class WorkshopAdmin(LearningContentAdmin):
    pass
