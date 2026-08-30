from django.db import migrations, models
import django.db.models.deletion


def seed_kyc(apps, schema_editor):
    from api.fintech import KYC_REVIEWED_AT, KYC_VENDORS, seed_stack

    seed_stack(
        KYC_VENDORS,
        stack="kyc",
        reviewed_at=KYC_REVIEWED_AT,
        check_model=apps.get_model("api", "FintechCheck"),
        rating_model=apps.get_model("api", "FintechRating"),
        tool_model=apps.get_model("api", "Tool"),
    )


def unseed_kyc(apps, schema_editor):
    FintechRating = apps.get_model("api", "FintechRating")
    FintechCheck = apps.get_model("api", "FintechCheck")
    FintechRating.objects.filter(stack="kyc").delete()
    FintechCheck.objects.filter(
        slug__in=[
            "dataLocalization",
            "consentManagement",
            "modelExplainability",
            "securityCerts",
            "biasTesting",
            "vendorViability",
        ]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0023_merge_jobstack_and_assessment"),
    ]

    operations = [
        migrations.CreateModel(
            name="FintechCheck",
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
                ("slug", models.SlugField(max_length=64, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("description", models.CharField(max_length=280)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                "db_table": "fintech_checks",
                "ordering": ["sort_order", "slug"],
            },
        ),
        migrations.CreateModel(
            name="FintechRating",
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
                    "stack",
                    models.CharField(
                        choices=[
                            ("kyc", "KYC / identity"),
                            ("credit", "Credit scoring"),
                            ("fraud", "Fraud / AML"),
                        ],
                        db_index=True,
                        default="kyc",
                        max_length=20,
                    ),
                ),
                (
                    "result",
                    models.CharField(
                        choices=[
                            ("pass", "Pass"),
                            ("fail", "Fail"),
                            ("unknown", "Unknown"),
                        ],
                        max_length=16,
                    ),
                ),
                ("rationale", models.CharField(max_length=500)),
                ("evidence_url", models.URLField(blank=True, max_length=500)),
                ("evidence_label", models.CharField(blank=True, max_length=160)),
                ("reviewed_at", models.DateField()),
                ("india_relevance", models.CharField(blank=True, max_length=400)),
                (
                    "check",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ratings",
                        to="api.fintechcheck",
                    ),
                ),
                (
                    "tool",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fintech_ratings",
                        to="api.tool",
                    ),
                ),
            ],
            options={
                "db_table": "fintech_ratings",
                "ordering": ["tool__name", "check__sort_order"],
            },
        ),
        migrations.AddConstraint(
            model_name="fintechrating",
            constraint=models.UniqueConstraint(
                fields=("tool", "check", "stack"),
                name="uniq_fintech_rating_tool_check_stack",
            ),
        ),
        migrations.RunPython(seed_kyc, unseed_kyc),
    ]
