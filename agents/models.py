from django.db import models


class AgentCategory(models.Model):
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    label = models.CharField(max_length=200)
    agent_count = models.IntegerField(default=0)
    growth_rate = models.FloatField(default=0)
    new_agents_30d = models.IntegerField(default=0)
    icon = models.CharField(max_length=50, blank=True, null=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Agent Categories"
        ordering = ["-agent_count"]

    def __str__(self):
        return f"{self.label} ({self.agent_count})"


class AIAgent(models.Model):
    ACCESS_CHOICES = [
        ("Open Source", "Open Source"),
        ("Closed Source", "Closed Source"),
        ("API", "API"),
    ]
    PRICING_CHOICES = [
        ("Free", "Free"),
        ("Freemium", "Freemium"),
        ("Paid", "Paid"),
    ]

    external_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    slug = models.SlugField(max_length=200, unique=True, db_index=True)
    name = models.CharField(max_length=300, db_index=True)

    category = models.ForeignKey(
        AgentCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agents",
    )
    category_name = models.CharField(max_length=200, blank=True)
    industry = models.CharField(max_length=200, blank=True)
    access = models.CharField(max_length=50, choices=ACCESS_CHOICES, blank=True)
    pricing_model = models.CharField(max_length=50, choices=PRICING_CHOICES, blank=True)

    short_description = models.TextField(blank=True)
    long_description = models.TextField(blank=True)
    key_features = models.JSONField(default=list)
    use_cases = models.JSONField(default=list)

    logo_url = models.URLField(max_length=500, blank=True)
    image_url = models.URLField(max_length=500, blank=True)
    video_url = models.URLField(max_length=500, blank=True)

    popularity_score = models.IntegerField(default=0, db_index=True)
    upvotes = models.IntegerField(default=0)
    views = models.IntegerField(default=0)
    bookmark_count = models.IntegerField(default=0)
    review_count = models.IntegerField(default=0)
    average_rating = models.FloatField(default=0)

    views_24h = models.IntegerField(default=0)
    views_7d = models.IntegerField(default=0)
    views_30d = models.IntegerField(default=0)
    upvotes_24h = models.IntegerField(default=0)
    upvotes_7d = models.IntegerField(default=0)
    upvotes_30d = models.IntegerField(default=0)

    website = models.URLField(max_length=500, blank=True)
    github_url = models.URLField(max_length=500, blank=True)
    twitter_url = models.URLField(max_length=500, blank=True)
    linkedin_url = models.URLField(max_length=500, blank=True)
    discord_url = models.URLField(max_length=500, blank=True)
    email = models.EmailField(blank=True)

    is_featured = models.BooleanField(default=False)
    seo_boost = models.BooleanField(default=False)
    source = models.CharField(max_length=100, default="aiagentsdirectory")

    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI Agent"
        verbose_name_plural = "AI Agents"
        ordering = ["-popularity_score"]
        indexes = [
            models.Index(fields=["category", "-popularity_score"]),
            models.Index(fields=["pricing_model"]),
            models.Index(fields=["access"]),
        ]

    def __str__(self):
        return self.name
