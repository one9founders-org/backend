from django.db import models


class Paper(models.Model):
    DIFFICULTY_CHOICES = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]

    arxiv_id = models.CharField(max_length=20, unique=True, db_index=True)
    title = models.TextField()
    abstract = models.TextField()
    authors = models.JSONField(default=list)
    categories = models.JSONField(default=list)
    published_at = models.DateTimeField()
    updated_at_arxiv = models.DateTimeField(null=True, blank=True)

    pdf_url = models.URLField()
    arxiv_url = models.URLField()
    hf_url = models.URLField(blank=True)
    code_url = models.URLField(blank=True)
    demo_url = models.URLField(blank=True)

    hf_upvotes = models.IntegerField(default=0)
    citation_count = models.IntegerField(default=0)

    ai_summary = models.TextField(blank=True)
    ai_tags = models.JSONField(default=list)
    ai_difficulty = models.CharField(
        max_length=20, choices=DIFFICULTY_CHOICES, blank=True
    )
    is_enriched = models.BooleanField(default=False)

    is_trending = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title[:100]

    class Meta:
        db_table = "research_papers"
        ordering = ["-published_at"]
        indexes = [
            models.Index(fields=["-published_at"]),
            models.Index(fields=["-hf_upvotes"]),
            models.Index(fields=["is_trending"]),
            models.Index(fields=["is_enriched"]),
        ]


class Author(models.Model):
    name = models.CharField(max_length=300, db_index=True)
    paper_count = models.IntegerField(default=0)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    papers = models.ManyToManyField(Paper, related_name="author_records", blank=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "research_authors"
        ordering = ["-paper_count"]
