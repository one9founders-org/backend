from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0018_tool_assessment_and_language_flag"),
    ]

    operations = [
        migrations.AddField(
            model_name="tool",
            name="last_enriched_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text=(
                    "When automated discovery last refreshed this tool's description."
                ),
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="DiscoveryRun",
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
                    "run_type",
                    models.CharField(
                        choices=[("new", "New"), ("refresh", "Refresh")],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("tool_name", models.CharField(max_length=255)),
                ("url", models.URLField(blank=True, max_length=500)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("published", "Published"),
                            ("rejected", "Rejected"),
                            ("error", "Error"),
                            ("updated", "Updated"),
                            ("refresh_rejected", "Refresh rejected"),
                            ("deferred", "Deferred over cap"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("reasons", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "db_table": "discovery_runs",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["run_type", "status"],
                        name="discovery_r_run_typ_371eab_idx",
                    ),
                    models.Index(
                        fields=["-created_at"],
                        name="discovery_r_created_42ee10_idx",
                    ),
                ],
            },
        ),
    ]
