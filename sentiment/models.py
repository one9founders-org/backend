from django.db import models
from django.utils import timezone

class ToolSentiment(models.Model):

    SENTIMENT_CHOICES = [
        ('positive', 'Positive'),
        ('mixed', 'Mixed'),
        ('negative', 'Negative'),
        ('insufficient_data', 'Insufficient Data'),
    ]

    CONFIDENCE_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
        ('none', 'None'),
    ]

    tool_name = models.CharField(max_length=255, unique=True)
    overall_score = models.FloatField(null=True, blank=True)
    sentiment_label = models.CharField(
        max_length=20,
        choices=SENTIMENT_CHOICES,
        default='insufficient_data'
    )
    confidence = models.CharField(
        max_length=10,
        choices=CONFIDENCE_CHOICES,
        default='none'
    )
    source_count = models.IntegerField(default=0)
    top_praises = models.JSONField(default=list)
    top_complaints = models.JSONField(default=list)
    red_flags = models.JSONField(default=list)
    one_line_summary = models.TextField(blank=True)
    was_corrected = models.BooleanField(default=False)
    last_analysed = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Tool Sentiment"

    def __str__(self):
        return f"{self.tool_name} → {self.sentiment_label} ({self.overall_score})"

    def needs_refresh(self):
        if not self.last_analysed:
            return True
        age = timezone.now() - self.last_analysed
        return age.total_seconds() > 172800