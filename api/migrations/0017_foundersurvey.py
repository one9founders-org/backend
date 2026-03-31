from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0016_add_founder_profile_fields")]

    operations = [
        migrations.CreateModel(
            name="FounderSurvey",
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
                ("name", models.CharField(blank=True, max_length=200)),
                ("startup", models.CharField(blank=True, max_length=300)),
                ("stage", models.CharField(blank=True, max_length=50)),
                ("time_wasting_task", models.TextField()),
                ("area", models.CharField(blank=True, max_length=100)),
                ("hours_per_week", models.CharField(blank=True, max_length=20)),
                ("pain_score", models.CharField(blank=True, max_length=5)),
                ("tried_to_solve", models.TextField(blank=True)),
                ("freed_time_use", models.TextField(blank=True)),
                (
                    "willingness_to_pay",
                    models.CharField(blank=True, max_length=100),
                ),
                ("contact", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "ip_address",
                    models.GenericIPAddressField(blank=True, null=True),
                ),
            ],
            options={
                "db_table": "founder_surveys",
                "ordering": ["-created_at"],
                "verbose_name": "Founder Survey Response",
                "verbose_name_plural": "Founder Survey Responses",
            },
        ),
    ]
