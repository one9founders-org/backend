from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0025_seed_credit_ratings"),
    ]

    operations = [
        migrations.CreateModel(
            name="FintechEvidencePage",
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
                ("url", models.URLField(max_length=500)),
                ("title", models.CharField(blank=True, max_length=300)),
                ("markdown", models.TextField(blank=True)),
                ("crawled_at", models.DateTimeField()),
                (
                    "tool",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fintech_evidence_pages",
                        to="api.tool",
                    ),
                ),
            ],
            options={
                "db_table": "fintech_evidence_pages",
                "ordering": ["-crawled_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="fintechevidencepage",
            constraint=models.UniqueConstraint(
                fields=("tool", "url"),
                name="uniq_fintech_evidence_tool_url",
            ),
        ),
    ]
