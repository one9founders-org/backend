# Generated manually for INR pricing feature

import django.db.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0014_add_is_startup_to_user"),
    ]

    operations = [
        # Add INR pricing fields to Tool
        migrations.AddField(
            model_name="tool",
            name="pricing_inr_override",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text=(
                    "Manual INR price override"
                    " (takes precedence over converted rate)"
                ),
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="tool",
            name="pricing_has_india_plan",
            field=models.BooleanField(
                default=False,
                help_text="Whether this tool offers India-specific pricing",
            ),
        ),
        migrations.AddField(
            model_name="tool",
            name="gst_applicable",
            field=models.BooleanField(
                default=True,
                help_text="Whether 18% GST applies to this tool for Indian users",
            ),
        ),
        # Create SiteConfig model
        migrations.CreateModel(
            name="SiteConfig",
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
                    "key",
                    models.CharField(db_index=True, max_length=100, unique=True),
                ),
                ("value", models.TextField()),
                ("description", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "site_config",
                "ordering": ["key"],
            },
        ),
        # Create PricingReport model
        migrations.CreateModel(
            name="PricingReport",
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
                ("reported_by_email", models.EmailField(blank=True, max_length=254)),
                (
                    "session_id",
                    models.CharField(blank=True, max_length=255),
                ),
                (
                    "message",
                    models.TextField(
                        blank=True,
                        help_text="Details about the incorrect pricing",
                    ),
                ),
                ("is_resolved", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "tool",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pricing_reports",
                        to="api.tool",
                    ),
                ),
            ],
            options={
                "db_table": "pricing_reports",
                "ordering": ["-created_at"],
            },
        ),
    ]
