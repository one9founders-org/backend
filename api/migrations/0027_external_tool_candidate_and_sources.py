from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


SOURCE_CHOICES = [
    ("producthunt", "Product Hunt"),
    ("taaft", "There's An AI For That"),
    ("g2", "G2"),
    ("linkedin", "LinkedIn"),
    ("github", "GitHub"),
    ("hackernews", "Hacker News"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0026_fintech_evidence_page"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExternalToolCandidate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=SOURCE_CHOICES, db_index=True, max_length=32
                    ),
                ),
                ("external_id", models.CharField(blank=True, max_length=255)),
                ("source_url", models.URLField(max_length=500)),
                ("name", models.CharField(max_length=255)),
                ("official_url", models.URLField(blank=True, max_length=500)),
                ("payload", models.JSONField(blank=True, default=dict)),
                (
                    "content_hash",
                    models.CharField(blank=True, db_index=True, max_length=64),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("published", "Published"),
                            ("error", "Error"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("review_notes", models.TextField(blank=True)),
                (
                    "discovered_at",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "linked_tool",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="external_candidates",
                        to="api.tool",
                    ),
                ),
            ],
            options={
                "db_table": "external_tool_candidates",
                "ordering": ["-discovered_at"],
            },
        ),
        migrations.CreateModel(
            name="ToolSource",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=SOURCE_CHOICES, db_index=True, max_length=32
                    ),
                ),
                ("label", models.CharField(blank=True, max_length=120)),
                ("url", models.URLField(max_length=500)),
                ("external_id", models.CharField(blank=True, max_length=255)),
                (
                    "observed_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tool",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="source_references",
                        to="api.tool",
                    ),
                ),
            ],
            options={
                "db_table": "tool_sources",
                "ordering": ["source", "-observed_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="externaltoolcandidate",
            constraint=models.UniqueConstraint(
                fields=("source", "source_url"),
                name="uniq_external_candidate_source_url",
            ),
        ),
        migrations.AddConstraint(
            model_name="externaltoolcandidate",
            constraint=models.UniqueConstraint(
                condition=models.Q(("external_id", ""), _negated=True),
                fields=("source", "external_id"),
                name="uniq_external_candidate_external_id",
            ),
        ),
        migrations.AddIndex(
            model_name="externaltoolcandidate",
            index=models.Index(
                fields=["source", "status"],
                name="extcand_source_status_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="toolsource",
            constraint=models.UniqueConstraint(
                fields=("tool", "source", "url"),
                name="uniq_tool_source_reference",
            ),
        ),
    ]
