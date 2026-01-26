"""
AI News Pipeline Models.

Handles the 4-stage pipeline:
raw_scraped_items -> qualified_news_items -> drafts -> published_articles
"""

import hashlib
from typing import Any, Dict, Optional

from django.db import models
from django.utils import timezone


class ScrapedItem(models.Model):
    """
    Stage 1: Raw scraped items from various sources.
    All items from scrapers land here first.
    """

    STATUS_CHOICES = [
        ("scraped", "Scraped"),
        ("processing", "Processing"),
        ("qualified", "Qualified"),
        ("rejected", "Rejected"),
        ("duplicate", "Duplicate"),
        ("error", "Error"),
    ]

    SOURCE_CHOICES = [
        ("producthunt", "Product Hunt"),
        ("taaft", "There's An AI For That"),
        ("futurepedia", "Futurepedia"),
        ("huggingface", "Hugging Face"),
        ("manual", "Manual Entry"),
    ]

    source = models.CharField(max_length=50, choices=SOURCE_CHOICES, db_index=True)
    source_url = models.URLField(max_length=500)
    external_url = models.URLField(max_length=500, blank=True)

    title = models.CharField(max_length=500)
    description = models.TextField()
    category = models.CharField(max_length=100, blank=True)
    tags = models.JSONField(default=list, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    images = models.JSONField(default=list, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)

    content_hash = models.CharField(
        max_length=64, unique=True, db_index=True, help_text="SHA256 hash for dedup"
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="scraped", db_index=True
    )
    status_reason = models.TextField(blank=True)

    scrape_batch_id = models.CharField(
        max_length=100, blank=True, db_index=True, help_text="Batch ID for idempotency"
    )
    scraped_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "raw_scraped_items"
        ordering = ["-scraped_at"]
        indexes = [
            models.Index(fields=["source", "status"]),
            models.Index(fields=["scraped_at", "status"]),
        ]

    def __str__(self):
        return f"[{self.source}] {self.title[:50]}"

    def save(self, *args, **kwargs):
        if not self.content_hash:
            content = f"{self.source}:{self.title}:{self.source_url}"
            self.content_hash = hashlib.sha256(content.encode()).hexdigest()
        super().save(*args, **kwargs)

    @classmethod
    def create_from_scraper_output(
        cls, source: str, item: Dict[str, Any], batch_id: str
    ) -> Optional["ScrapedItem"]:
        """Create a ScrapedItem from scraper output, handling duplicates."""
        title = item.get("title", "")
        source_url = item.get("url", "")

        content = f"{source}:{title}:{source_url}"
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        if cls.objects.filter(content_hash=content_hash).exists():
            return None

        return cls.objects.create(
            source=source,
            source_url=source_url,
            external_url=item.get("external_url", ""),
            title=title,
            description=item.get("description", ""),
            category=item.get("category", ""),
            tags=item.get("tags", []),
            metrics=item.get("metrics", {}),
            images=item.get("images", []),
            raw_data=item.get("raw", {}),
            content_hash=content_hash,
            scrape_batch_id=batch_id,
        )


class QualifiedNewsItem(models.Model):
    """
    Stage 2: Items that passed initial filtering and scoring.
    Contains AI-generated relevance scores.
    """

    STATUS_CHOICES = [
        ("scored", "Scored"),
        ("auto_rejected", "Auto Rejected"),
        ("queued", "Queued for Review"),
        ("auto_approved", "Auto Approved"),
        ("manually_approved", "Manually Approved"),
        ("manually_rejected", "Manually Rejected"),
    ]

    scraped_item = models.OneToOneField(
        ScrapedItem, on_delete=models.CASCADE, related_name="qualified_item"
    )

    relevance_score = models.IntegerField(
        default=0, db_index=True, help_text="AI relevance score 0-100"
    )
    founder_relevance = models.IntegerField(
        default=0, help_text="Relevance to founders 0-100"
    )
    practical_impact = models.IntegerField(
        default=0, help_text="Practical impact score 0-100"
    )
    novelty_score = models.IntegerField(default=0, help_text="Novelty score 0-100")

    scoring_rationale = models.TextField(blank=True, help_text="AI explanation")
    scoring_model = models.CharField(max_length=50, default="gpt-4o-mini")

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="scored", db_index=True
    )
    status_reason = models.TextField(blank=True)

    reviewed_by = models.CharField(max_length=100, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "qualified_news_items"
        ordering = ["-relevance_score", "-created_at"]
        indexes = [
            models.Index(fields=["status", "-relevance_score"]),
            models.Index(fields=["created_at", "status"]),
        ]

    def __str__(self):
        return f"[{self.relevance_score}] {self.scraped_item.title[:50]}"

    def auto_categorize(self) -> str:
        """Determine status based on relevance score."""
        if self.relevance_score < 40:
            return "auto_rejected"
        elif self.relevance_score >= 70:
            return "auto_approved"
        else:
            return "queued"


class NewsDraft(models.Model):
    """
    Stage 3: AI-generated article drafts ready for publishing.
    """

    STATUS_CHOICES = [
        ("generating", "Generating"),
        ("generated", "Generated"),
        ("editing", "Editing"),
        ("ready", "Ready to Publish"),
        ("scheduled", "Scheduled"),
        ("published", "Published"),
        ("failed", "Generation Failed"),
    ]

    qualified_item = models.OneToOneField(
        QualifiedNewsItem, on_delete=models.CASCADE, related_name="draft"
    )

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    excerpt = models.TextField(max_length=300, help_text="Short preview/hook")
    content = models.TextField(help_text="Full article content (HTML)")

    hook = models.TextField(blank=True, help_text="Opening hook")
    why_matters = models.TextField(blank=True, help_text="Why this matters section")
    founder_takeaway = models.TextField(blank=True, help_text="Key takeaway")

    category = models.CharField(max_length=100, blank=True, db_index=True)
    tags = models.JSONField(default=list, blank=True)

    seo_title = models.CharField(max_length=70, blank=True)
    seo_description = models.CharField(max_length=160, blank=True)
    featured_image = models.URLField(blank=True)

    generation_model = models.CharField(max_length=50, default="gpt-4o-mini")
    generation_prompt_version = models.CharField(max_length=20, default="v1")

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="generating", db_index=True
    )
    status_reason = models.TextField(blank=True)

    scheduled_for = models.DateTimeField(null=True, blank=True, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "news_drafts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["scheduled_for", "status"]),
        ]

    def __str__(self):
        return f"[{self.status}] {self.title[:50]}"

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            base_slug = slugify(self.title)[:200]
            self.slug = f"{base_slug}-{timezone.now().strftime('%Y%m%d')}"
        super().save(*args, **kwargs)


class PublishedArticle(models.Model):
    """
    Stage 4: Published articles linked to the main News model.
    Tracks publishing metadata and performance.
    """

    draft = models.OneToOneField(
        NewsDraft, on_delete=models.SET_NULL, null=True, related_name="published"
    )
    news = models.OneToOneField(
        "News",
        on_delete=models.CASCADE,
        related_name="pipeline_article",
        help_text="Link to main News model",
    )

    source = models.CharField(max_length=50, db_index=True)
    original_url = models.URLField(max_length=500)
    relevance_score = models.IntegerField(default=0)

    published_at = models.DateTimeField(auto_now_add=True, db_index=True)
    publish_slot = models.IntegerField(
        default=1, help_text="Which slot of the day (1-5)"
    )

    views_count = models.IntegerField(default=0)
    engagement_score = models.FloatField(default=0.0)

    class Meta:
        db_table = "published_articles"
        ordering = ["-published_at"]
        indexes = [
            models.Index(fields=["published_at", "source"]),
        ]

    def __str__(self):
        return f"Published: {self.news.title[:50]}"


class PipelineRun(models.Model):
    """
    Tracks pipeline execution for monitoring and debugging.
    """

    RUN_TYPE_CHOICES = [
        ("scrape", "Scraping"),
        ("score", "Scoring"),
        ("generate", "Content Generation"),
        ("publish", "Publishing"),
        ("full", "Full Pipeline"),
    ]

    STATUS_CHOICES = [
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    run_type = models.CharField(max_length=20, choices=RUN_TYPE_CHOICES, db_index=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="running", db_index=True
    )

    source = models.CharField(max_length=50, blank=True, db_index=True)
    batch_id = models.CharField(max_length=100, unique=True, db_index=True)

    items_processed = models.IntegerField(default=0)
    items_succeeded = models.IntegerField(default=0)
    items_failed = models.IntegerField(default=0)

    error_message = models.TextField(blank=True)
    logs = models.JSONField(default=list, blank=True)

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "pipeline_runs"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["run_type", "status"]),
            models.Index(fields=["started_at"]),
        ]

    def __str__(self):
        return f"[{self.run_type}] {self.batch_id} - {self.status}"

    def complete(self, success: bool = True, error: str = ""):
        """Mark the run as completed."""
        self.status = "completed" if success else "failed"
        self.error_message = error
        self.completed_at = timezone.now()
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        self.save()

    def add_log(self, message: str, level: str = "info"):
        """Add a log entry."""
        self.logs.append(
            {
                "timestamp": timezone.now().isoformat(),
                "level": level,
                "message": message,
            }
        )
        self.save(update_fields=["logs"])


class PipelineConfig(models.Model):
    """
    Configuration for the pipeline, including kill-switch.
    """

    key = models.CharField(max_length=100, unique=True, db_index=True)
    value = models.JSONField()
    description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "pipeline_config"

    def __str__(self):
        return f"{self.key}: {self.value}"

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """Get a config value."""
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set(cls, key: str, value: Any, description: str = "", updated_by: str = ""):
        """Set a config value."""
        obj, _ = cls.objects.update_or_create(
            key=key,
            defaults={
                "value": value,
                "description": description,
                "updated_by": updated_by,
            },
        )
        return obj

    @classmethod
    def is_publishing_enabled(cls) -> bool:
        """Check if publishing is enabled (kill-switch)."""
        return cls.get("publishing_enabled", True)

    @classmethod
    def get_max_articles_per_day(cls) -> int:
        """Get maximum articles to publish per day."""
        return cls.get("max_articles_per_day", 5)

    @classmethod
    def get_score_thresholds(cls) -> Dict[str, int]:
        """Get scoring thresholds."""
        return cls.get(
            "score_thresholds",
            {"auto_reject": 40, "auto_approve": 70},
        )
