from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0021_tool_orphan_column_nulls"),
    ]

    operations = [
        migrations.CreateModel(
            name="JobStack",
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
                    "public_id",
                    models.CharField(db_index=True, max_length=12, unique=True),
                ),
                ("query", models.CharField(max_length=500)),
                ("title", models.CharField(max_length=200)),
                ("blurb", models.TextField(blank=True)),
                ("cash_out", models.CharField(blank=True, max_length=400)),
                (
                    "source",
                    models.CharField(
                        choices=[("agent", "Agent"), ("person", "Person")],
                        db_index=True,
                        default="agent",
                        max_length=12,
                    ),
                ),
                ("lanes", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="job_stacks",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "job_stacks",
                "ordering": ["-created_at"],
            },
        ),
    ]
