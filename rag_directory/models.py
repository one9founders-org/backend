from django.db import models


class RagTool(models.Model):
    CATEGORY_CHOICES = [
        ("vector_db", "Vector Database"),
        ("rag_framework", "RAG Framework"),
        ("embedding_model", "Embedding Model"),
    ]
    PRICING_CHOICES = [
        ("free", "Free"),
        ("freemium", "Freemium"),
        ("paid", "Paid"),
        ("open_source", "Open Source"),
    ]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("deprecated", "Deprecated"),
        ("stale", "Stale"),
    ]

    slug = models.SlugField(unique=True, max_length=100)
    name = models.CharField(max_length=200)
    logo_url = models.URLField(blank=True)
    description = models.TextField()
    long_description = models.TextField(blank=True)
    website_url = models.URLField()
    docs_url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    github_repo = models.CharField(max_length=200, blank=True)

    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    pricing_model = models.CharField(max_length=20, choices=PRICING_CHOICES)
    pricing_details = models.JSONField(default=dict, blank=True)

    deployment_options = models.JSONField(default=list)
    sdk_languages = models.JSONField(default=list)
    integrations = models.JSONField(default=list)
    specs = models.JSONField(default=dict, blank=True)
    security_certs = models.JSONField(default=list)

    rating_scores = models.JSONField(default=dict)
    overall_rating = models.DecimalField(max_digits=3, decimal_places=1, default=0)

    featured = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    github_stars = models.IntegerField(default=0)
    github_forks = models.IntegerField(default=0)
    last_commit_at = models.DateTimeField(null=True, blank=True)
    latest_release = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "rag_tools"
        ordering = ["-overall_rating", "-github_stars"]
        indexes = [
            models.Index(fields=["category", "status"]),
            models.Index(fields=["pricing_model"]),
            models.Index(fields=["-github_stars"]),
            models.Index(fields=["-overall_rating"]),
        ]


class GitHubSnapshot(models.Model):
    tool = models.ForeignKey(
        RagTool, on_delete=models.CASCADE, related_name="github_snapshots"
    )
    stars = models.IntegerField(default=0)
    forks = models.IntegerField(default=0)
    open_issues = models.IntegerField(default=0)
    contributors = models.IntegerField(default=0)
    last_commit_at = models.DateTimeField(null=True)
    latest_release = models.CharField(max_length=100, blank=True)
    snapshot_date = models.DateField()

    def __str__(self):
        return f"{self.tool.name} - {self.snapshot_date}"

    class Meta:
        db_table = "github_snapshots"
        ordering = ["-snapshot_date"]
        unique_together = ["tool", "snapshot_date"]
