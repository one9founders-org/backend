import logging
import math

from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django_summernote.fields import SummernoteTextField
from pgvector.django import VectorField

logger = logging.getLogger(__name__)


class User(AbstractUser):
    avatar_url = models.URLField(blank=True, null=True)
    is_startup = models.BooleanField(
        default=False, help_text="Whether the user is a startup founder"
    )

    class Meta:
        db_table = "users"


class Category(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "categories"
        verbose_name_plural = "Categories"


class Tool(models.Model):
    PRICING_CHOICES = [
        ("free", "Free"),
        ("freemium", "Freemium"),
        ("paid", "Paid"),
        ("trial", "Free Trial"),
        ("contact", "Contact Sales"),
        ("usage_based", "Usage Based"),
    ]
    PRICING_TYPE_CHOICES = [
        ("free", "Free"),
        ("freemium", "Freemium"),
        ("paid", "Paid"),
    ]
    BILLING_CHOICES = [
        ("monthly", "Monthly"),
        ("yearly", "Yearly"),
        ("one_time", "One Time"),
        ("usage", "Pay as you go"),
    ]

    name = models.CharField(max_length=255, db_index=True, unique=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    short_description = models.CharField(max_length=200, blank=True)
    description = models.TextField()
    categories = models.ManyToManyField(Category, related_name="tools", blank=True)

    # URLs
    website = models.URLField(blank=True, null=True)
    affiliate_url = models.URLField(blank=True, null=True)
    logo_url = models.URLField(blank=True, null=True)
    video_demo_url = models.URLField(blank=True, null=True)
    landing_page_screenshot = models.URLField(
        blank=True, null=True, help_text="Screenshot/preview of the tool's landing page"
    )

    # Pricing
    pricing_models = models.JSONField(
        default=list, blank=True, help_text="['free', 'paid']"
    )
    pricing_tiers = models.JSONField(
        default=list,
        blank=True,
        help_text="[{'name': 'Pro', 'price': 20, 'billing': 'monthly'}]",
    )
    pricing_from = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    free_tier_available = models.BooleanField(default=False)
    free_trial_days = models.IntegerField(blank=True, null=True)
    pricing_type = models.CharField(
        max_length=20,
        choices=PRICING_TYPE_CHOICES,
        default="freemium",
        db_index=True,
        help_text="Primary pricing type: free, freemium, or paid",
    )

    # Content
    tags = models.JSONField(default=list, blank=True)
    use_cases = models.JSONField(default=list, blank=True)
    integrations = models.JSONField(default=list, blank=True)
    features = models.JSONField(default=list, blank=True)
    platforms = models.JSONField(default=list, blank=True)
    startup_benefits = models.TextField(
        blank=True, help_text="How this tool helps startups/founders"
    )
    ideal_for = models.JSONField(
        default=list,
        blank=True,
        help_text="e.g., ['early-stage', 'bootstrapped', 'SaaS']",
    )

    # Stats
    rating = models.DecimalField(
        max_digits=3, decimal_places=1, default=0.0, db_index=True
    )
    review_count = models.IntegerField(default=0)
    views_count = models.IntegerField(default=0)
    startup_friendly = models.BooleanField(
        default=False, help_text="Has startup discount/free tier"
    )

    # Status
    verified = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    # Display order for homepage ranking (lower = higher priority)
    display_order = models.IntegerField(
        default=9999,
        db_index=True,
        help_text="Display order on homepage (lower = higher)",
    )

    # Relations
    alternatives = models.ManyToManyField(
        "self", blank=True, symmetrical=False, related_name="alternative_to"
    )

    # Extension
    domain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="Root domain extracted from website URL (e.g. runway.ml)",
    )

    # Security
    security_score = models.IntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Security score from 0-100 based on 10-point assessment",
    )
    security_assessed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the security assessment was last performed",
    )

    # AI
    embedding = VectorField(dimensions=1536, blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.name)

        # Auto-enrich with AI if only basic fields provided
        if self.name and self.description and not self.tags:
            try:
                from .ai_enrichment import enrich_tool_data

                enriched = enrich_tool_data(self.name, self.description, self.website)

                self.short_description = enriched.get("short_description", "")[:200]
                self.tags = enriched.get("tags", [])
                self.use_cases = enriched.get("use_cases", [])
                self.features = enriched.get("features", [])
                self.platforms = enriched.get("platforms", [])
                self.integrations = enriched.get("integrations", [])
                self.startup_benefits = enriched.get("startup_benefits", "")
                self.ideal_for = enriched.get("ideal_for", [])
                self.startup_friendly = enriched.get("startup_friendly", False)
                self.pricing_models = enriched.get("pricing_models", [])
                self.pricing_tiers = enriched.get("pricing_tiers", [])
                self.free_tier_available = enriched.get("free_tier_available", False)
                if not self.free_trial_days:
                    self.free_trial_days = enriched.get("free_trial_days")
            except Exception:
                pass

        # Generate embedding
        if self.embedding is None and self.name and self.description:
            try:
                from django.conf import settings
                from openai import OpenAI

                client = OpenAI(api_key=settings.OPENAI_API_KEY)

                parts = [
                    self.name,
                    self.short_description or "",
                    self.description,
                    " ".join(self.tags or []),
                    " ".join(self.use_cases or []),
                    " ".join(self.features or []),
                    self.startup_benefits or "",
                    " ".join(self.ideal_for or []),
                ]
                text = " ".join(filter(None, parts))

                response = client.embeddings.create(
                    model="text-embedding-ada-002", input=text
                )
                self.embedding = response.data[0].embedding
            except Exception as e:
                logger.warning(
                    "Failed to generate embedding for tool %s: %s", self.name, e
                )
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "tools"
        ordering = ["display_order", "-is_featured", "-rating"]


class Review(models.Model):
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    # Required
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="reviews")
    user_name = models.CharField(max_length=255, blank=True)
    rating = models.IntegerField(choices=RATING_CHOICES)
    comment = models.TextField(blank=True)

    # Optional
    user_email = models.EmailField(blank=True)
    title = models.CharField(max_length=255, blank=True)
    pros = models.JSONField(default=list, blank=True)
    cons = models.JSONField(default=list, blank=True)

    # Meta
    verified_purchase = models.BooleanField(default=False)
    helpful_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Auto-extract pros/cons from comment if not provided
        if self.comment and not self.pros and not self.cons:
            try:
                import json

                from django.conf import settings
                from openai import OpenAI

                client = OpenAI(api_key=settings.OPENAI_API_KEY)

                prompt = f"""Extract pros and cons from this review:

"{self.comment}"

Return JSON: {{"pros": ["pro1", "pro2"], "cons": ["con1", "con2"]}}
Only return JSON."""

                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                )
                data = json.loads(
                    response.choices[0]
                    .message.content.strip()
                    .replace("```json", "")
                    .replace("```", "")
                )
                self.pros = data.get("pros", [])
                self.cons = data.get("cons", [])
            except Exception as e:
                logger.warning("Failed to extract pros/cons from review: %s", e)

        super().save(*args, **kwargs)

        # Update tool rating
        from django.db.models import Avg, Count

        stats = Review.objects.filter(tool=self.tool).aggregate(
            avg_rating=Avg("rating"), count=Count("id")
        )
        self.tool.rating = round(stats["avg_rating"] or 0, 1)
        self.tool.review_count = stats["count"]
        self.tool.save(update_fields=["rating", "review_count"])

    def __str__(self):
        return (
            f"{self.title} by {self.user_name}"
            if self.title
            else f"{self.user_name} - {self.tool.name}"
        )

    class Meta:
        db_table = "reviews"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tool", "-created_at"]),
        ]


class UserFavorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorites")
    tool = models.ForeignKey(
        Tool, on_delete=models.CASCADE, related_name="favorited_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.tool.name}"

    class Meta:
        db_table = "user_favorites"
        unique_together = ("user", "tool")
        ordering = ["-created_at"]


class ToolSubmission(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    # Required from user
    name = models.CharField(max_length=255)
    description = models.TextField()
    website = models.URLField()
    submitter_email = models.EmailField()
    submitter_name = models.CharField(max_length=255)

    # Optional from user
    logo_url = models.URLField(blank=True)
    short_description = models.CharField(max_length=200, blank=True)
    categories = models.ManyToManyField(Category, blank=True)
    pricing_info = models.TextField(blank=True, help_text="Pricing details")

    # AI enriched (auto-filled)
    enriched_data = models.JSONField(
        default=dict, blank=True, help_text="AI-generated data"
    )

    # Admin
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True
    )
    admin_notes = models.TextField(blank=True)
    approved_tool = models.ForeignKey(
        Tool,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submission",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Auto-enrich on creation
        if not self.pk and not self.enriched_data:
            try:
                from .ai_enrichment import enrich_tool_data

                self.enriched_data = enrich_tool_data(
                    self.name, self.description, self.website
                )
            except Exception:
                pass
        super().save(*args, **kwargs)

    def approve_and_create_tool(self):
        """Convert submission to Tool"""
        tool = Tool.objects.create(
            name=self.name,
            description=self.description,
            short_description=self.short_description
            or self.enriched_data.get("short_description", ""),
            website=self.website,
            logo_url=self.logo_url,
            tags=self.enriched_data.get("tags", []),
            use_cases=self.enriched_data.get("use_cases", []),
            features=self.enriched_data.get("features", []),
            platforms=self.enriched_data.get("platforms", []),
            integrations=self.enriched_data.get("integrations", []),
            startup_benefits=self.enriched_data.get("startup_benefits", ""),
            ideal_for=self.enriched_data.get("ideal_for", []),
            pricing_models=self.enriched_data.get("pricing_models", []),
            pricing_tiers=self.enriched_data.get("pricing_tiers", []),
            free_tier_available=self.enriched_data.get("free_tier_available", False),
            startup_friendly=self.enriched_data.get("startup_friendly", False),
        )
        tool.categories.set(self.categories.all())
        self.status = "approved"
        self.approved_tool = tool
        self.save()
        return tool

    def __str__(self):
        return f"{self.name} - {self.status}"

    class Meta:
        db_table = "tool_submissions"
        ordering = ["-created_at"]


class NewsletterSubscription(models.Model):
    email = models.EmailField(unique=True)
    source = models.CharField(max_length=50, default="homepage", db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email

    class Meta:
        db_table = "newsletter_subscriptions"
        ordering = ["-created_at"]


class Deal(models.Model):
    tool = models.ForeignKey(
        Tool, on_delete=models.CASCADE, related_name="deals", null=True, blank=True
    )
    offer_title = models.CharField(max_length=255, default="Special Offer")
    old_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    new_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_percentage = models.IntegerField(default=0)
    expiry_date = models.DateField(db_index=True, null=True, blank=True)
    claims_count = models.IntegerField(default=0)
    deal_url = models.URLField(default="#")
    featured_deal = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.tool.name} - {self.discount_percentage}% OFF"

    class Meta:
        db_table = "deals"
        ordering = ["-featured_deal", "-created_at"]


class ToolUsage(models.Model):
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="usages")
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="tool_usages",
        null=True,
        blank=True,
    )
    session_id = models.CharField(max_length=255, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        user_str = self.user.username if self.user else self.session_id or "Anonymous"
        return f"{user_str} uses {self.tool.name}"

    class Meta:
        db_table = "tool_usages"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tool", "-created_at"]),
        ]


class SearchQuery(models.Model):
    query = models.CharField(max_length=500, db_index=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="searches"
    )
    session_id = models.CharField(max_length=255, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    results_count = models.IntegerField(default=0)
    filters = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"'{self.query}' - {self.results_count} results"

    class Meta:
        db_table = "search_queries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
        ]


class ToolClick(models.Model):
    ACTION_CHOICES = [
        ("view_details", "View Details"),
        ("visit_tool", "Visit Tool"),
        ("write_review", "Write Review"),
        ("i_use_this", "I Use This"),
    ]

    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="clicks")
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, db_index=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="clicks"
    )
    session_id = models.CharField(max_length=255, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    referrer = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} on {self.tool.name}"

    class Meta:
        db_table = "tool_clicks"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tool", "action", "-created_at"]),
        ]


class News(models.Model):
    # Basic
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    excerpt = models.TextField(max_length=300, help_text="Short preview")
    content = SummernoteTextField()

    # Media
    featured_image = models.URLField(blank=True)

    # Relations
    related_tools = models.ManyToManyField(
        Tool, blank=True, related_name="news_articles"
    )
    author = models.CharField(max_length=255, default="Admin")

    # Categorization
    category = models.CharField(max_length=100, blank=True, db_index=True)
    tags = models.JSONField(default=list, blank=True)

    # Meta
    reading_time = models.IntegerField(default=0, help_text="Minutes to read")
    views_count = models.IntegerField(default=0)
    upvote_count = models.IntegerField(default=0, help_text="Number of upvotes")
    is_published = models.BooleanField(default=False, db_index=True)
    is_featured = models.BooleanField(default=False)

    # Timestamps
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.title)

        # Auto-calculate reading time (avg 200 words/min)
        if self.content:
            from django.utils.html import strip_tags

            word_count = len(strip_tags(self.content).split())
            self.reading_time = max(1, math.ceil(word_count / 200))

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    class Meta:
        db_table = "news"
        verbose_name_plural = "News"
        ordering = ["-published_at"]


class LearningContent(models.Model):
    """Abstract base model for Guides, Labs, and Workshops."""

    DIFFICULTY_CHOICES = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]

    CATEGORY_CHOICES = [
        ("ai-fundamentals", "AI Fundamentals"),
        ("machine-learning", "Machine Learning"),
        ("natural-language-processing", "Natural Language Processing"),
        ("computer-vision", "Computer Vision"),
        ("automation", "Automation"),
        ("data-analytics", "Data & Analytics"),
        ("marketing", "Marketing"),
        ("product-development", "Product Development"),
        ("sales", "Sales"),
        ("operations", "Operations"),
        ("security", "Security"),
        ("other", "Other"),
    ]

    AUDIENCE_CHOICES = [
        ("founders", "Founders"),
        ("developers", "Developers"),
        ("marketers", "Marketers"),
        ("product-managers", "Product Managers"),
        ("designers", "Designers"),
        ("non-technical", "Non-Technical"),
        ("everyone", "Everyone"),
    ]

    PRICING_CHOICES = [
        ("free", "Free"),
        ("paid", "Paid"),
        ("freemium", "Freemium"),
    ]

    # Core fields
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    short_description = models.CharField(max_length=300, blank=True)
    content = SummernoteTextField(blank=True)
    featured_image = models.URLField(blank=True)
    author = models.CharField(max_length=255, default="One9Founders")

    # Classification fields
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default="beginner",
        db_index=True,
    )
    estimated_time = models.CharField(
        max_length=50,
        blank=True,
        help_text="e.g., '30 min', '2 hours', '1-2 hours'",
    )
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default="ai-fundamentals",
        db_index=True,
    )
    audience = models.CharField(
        max_length=30,
        choices=AUDIENCE_CHOICES,
        default="founders",
        db_index=True,
    )

    # Taxonomy: tools used
    tools_used = models.ManyToManyField(
        Tool,
        blank=True,
        related_name="%(class)s_content",
        help_text="AI tools referenced or used in this content",
    )

    # Pricing
    pricing = models.CharField(
        max_length=20,
        choices=PRICING_CHOICES,
        default="free",
        db_index=True,
    )
    price_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Price in USD (if applicable)",
    )

    # SEO fields
    meta_title = models.CharField(
        max_length=70,
        blank=True,
        help_text="SEO title (max 70 chars). Falls back to title if blank.",
    )
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        help_text="SEO description (max 160 chars). Falls back to short_description.",
    )

    # Status
    is_published = models.BooleanField(default=False, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)

    # Timestamps
    last_updated = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Manually set 'last updated' date for content freshness",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    class Meta:
        abstract = True
        ordering = ["-published_at", "-created_at"]


class Guide(LearningContent):
    """In-depth written guides and tutorials."""

    class Meta(LearningContent.Meta):
        db_table = "guides"
        verbose_name = "Guide"
        verbose_name_plural = "Guides"


class Lab(LearningContent):
    """Hands-on, interactive lab exercises."""

    class Meta(LearningContent.Meta):
        db_table = "labs"
        verbose_name = "Lab"
        verbose_name_plural = "Labs"


class Workshop(LearningContent):
    """Live or recorded workshop sessions."""

    class Meta(LearningContent.Meta):
        db_table = "workshops"
        verbose_name = "Workshop"
        verbose_name_plural = "Workshops"


class NewsUpvote(models.Model):
    """Track upvotes on news articles."""

    news = models.ForeignKey(News, on_delete=models.CASCADE, related_name="upvotes")
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="news_upvotes",
        null=True,
        blank=True,
    )
    session_id = models.CharField(
        max_length=255, blank=True, db_index=True, help_text="For anonymous upvotes"
    )
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        user_str = self.user.username if self.user else self.session_id or "Anonymous"
        return f"{user_str} upvoted {self.news.title[:30]}"

    class Meta:
        db_table = "news_upvotes"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["news", "-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["news", "user"],
                condition=models.Q(user__isnull=False),
                name="unique_user_upvote",
            ),
            models.UniqueConstraint(
                fields=["news", "session_id"],
                condition=models.Q(session_id__gt=""),
                name="unique_session_upvote",
            ),
        ]


class ToolSuggestion(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("reviewed", "Reviewed"),
        ("rejected", "Rejected"),
    ]

    domain = models.CharField(max_length=255, db_index=True)
    suggested_by = models.CharField(
        max_length=255, default="extension_user", blank=True
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.domain} - {self.status}"

    class Meta:
        db_table = "tool_suggestions"
        ordering = ["-created_at"]


class ToolSentimentLog(models.Model):
    # Link directly to the existing Tool model!
    tool = models.ForeignKey(
        Tool, on_delete=models.CASCADE, related_name="sentiment_logs"
    )
    source = models.CharField(
        max_length=50, default="Unknown", help_text="e.g., G2, Reddit, X"
    )

    weighted_score = models.FloatField()
    raw_aspect_data = models.JSONField()

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def _str_(self):
        date_str = self.created_at.date()
        return f"{self.tool.name} Sentiment: {self.weighted_score} ({date_str})"

    class Meta:
        db_table = "tool_sentiment_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tool", "-created_at"]),
        ]
