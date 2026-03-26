"""
Serializers for the AI News Pipeline models.
"""

from rest_framework import serializers

from .pipeline_models import (
    NewsDraft,
    PipelineConfig,
    PipelineRun,
    PublishedArticle,
    QualifiedNewsItem,
    ScrapedItem,
)


class ScrapedItemSerializer(serializers.ModelSerializer):
    """Serializer for ScrapedItem model."""

    class Meta:
        model = ScrapedItem
        fields = [
            "id",
            "source",
            "source_url",
            "external_url",
            "title",
            "description",
            "category",
            "tags",
            "metrics",
            "images",
            "status",
            "status_reason",
            "scrape_batch_id",
            "scraped_at",
            "processed_at",
        ]
        read_only_fields = ["id", "content_hash", "scraped_at", "processed_at"]


class ScrapedItemMinimalSerializer(serializers.ModelSerializer):
    """Minimal serializer for nested ScrapedItem."""

    class Meta:
        model = ScrapedItem
        fields = [
            "id",
            "source",
            "title",
            "source_url",
            "category",
            "scraped_at",
        ]


class QualifiedNewsItemSerializer(serializers.ModelSerializer):
    """Serializer for QualifiedNewsItem model."""

    scraped_item = ScrapedItemMinimalSerializer(read_only=True)

    class Meta:
        model = QualifiedNewsItem
        fields = [
            "id",
            "scraped_item",
            "relevance_score",
            "founder_relevance",
            "practical_impact",
            "novelty_score",
            "scoring_rationale",
            "scoring_model",
            "status",
            "status_reason",
            "reviewed_by",
            "reviewed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "scraped_item",
            "relevance_score",
            "founder_relevance",
            "practical_impact",
            "novelty_score",
            "scoring_rationale",
            "scoring_model",
            "created_at",
            "updated_at",
        ]


class QualifiedNewsItemMinimalSerializer(serializers.ModelSerializer):
    """Minimal serializer for nested QualifiedNewsItem."""

    source = serializers.CharField(source="scraped_item.source", read_only=True)
    original_title = serializers.CharField(source="scraped_item.title", read_only=True)

    class Meta:
        model = QualifiedNewsItem
        fields = [
            "id",
            "source",
            "original_title",
            "relevance_score",
            "status",
        ]


class NewsDraftSerializer(serializers.ModelSerializer):
    """Serializer for NewsDraft model."""

    qualified_item = QualifiedNewsItemMinimalSerializer(read_only=True)

    class Meta:
        model = NewsDraft
        fields = [
            "id",
            "qualified_item",
            "title",
            "slug",
            "excerpt",
            "content",
            "hook",
            "why_matters",
            "founder_takeaway",
            "category",
            "tags",
            "seo_title",
            "seo_description",
            "featured_image",
            "generation_model",
            "status",
            "status_reason",
            "scheduled_for",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "qualified_item",
            "slug",
            "generation_model",
            "generation_prompt_version",
            "created_at",
            "updated_at",
        ]


class NewsDraftMinimalSerializer(serializers.ModelSerializer):
    """Minimal serializer for nested NewsDraft."""

    class Meta:
        model = NewsDraft
        fields = [
            "id",
            "title",
            "status",
            "created_at",
        ]


class PublishedArticleSerializer(serializers.ModelSerializer):
    """Serializer for PublishedArticle model."""

    draft = NewsDraftMinimalSerializer(read_only=True)
    news_title = serializers.CharField(source="news.title", read_only=True)
    news_slug = serializers.CharField(source="news.slug", read_only=True)

    class Meta:
        model = PublishedArticle
        fields = [
            "id",
            "draft",
            "news_title",
            "news_slug",
            "source",
            "original_url",
            "relevance_score",
            "published_at",
            "publish_slot",
            "views_count",
            "engagement_score",
        ]
        read_only_fields = fields


class PipelineRunSerializer(serializers.ModelSerializer):
    """Serializer for PipelineRun model."""

    class Meta:
        model = PipelineRun
        fields = [
            "id",
            "run_type",
            "status",
            "source",
            "batch_id",
            "items_processed",
            "items_succeeded",
            "items_failed",
            "error_message",
            "logs",
            "started_at",
            "completed_at",
            "duration_seconds",
        ]
        read_only_fields = fields


class PipelineConfigSerializer(serializers.ModelSerializer):
    """Serializer for PipelineConfig model."""

    class Meta:
        model = PipelineConfig
        fields = [
            "id",
            "key",
            "value",
            "description",
            "updated_at",
            "updated_by",
        ]
        read_only_fields = ["id", "updated_at"]


class PipelineStatsSerializer(serializers.Serializer):
    """Serializer for pipeline statistics."""

    scraped = serializers.DictField()
    qualified = serializers.DictField()
    drafts = serializers.DictField()
    published = serializers.DictField()
    by_source = serializers.ListField()
    recent_runs = PipelineRunSerializer(many=True)
    config = serializers.DictField()
