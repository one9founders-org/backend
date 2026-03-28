from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0015_add_inr_pricing_and_site_config")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="user_role",
            field=models.CharField(
                max_length=50,
                blank=True,
                default="",
                help_text=(
                    "founder | cofounder | investor" " | student | professional | other"
                ),
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="startup_name",
            field=models.CharField(max_length=255, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="user",
            name="startup_website",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="startup_stage",
            field=models.CharField(max_length=100, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="user",
            name="team_size",
            field=models.CharField(max_length=50, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="user",
            name="industry",
            field=models.JSONField(default=list, blank=True),
        ),
        migrations.AddField(
            model_name="user",
            name="challenges",
            field=models.JSONField(default=list, blank=True),
        ),
        migrations.AddField(
            model_name="user",
            name="ai_tasks",
            field=models.JSONField(default=list, blank=True),
        ),
        migrations.AddField(
            model_name="user",
            name="time_lost_per_week",
            field=models.CharField(max_length=50, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="user",
            name="ai_comfort_level",
            field=models.CharField(max_length=100, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="user",
            name="referral_source",
            field=models.CharField(max_length=100, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="user",
            name="profile_completed",
            field=models.BooleanField(default=False),
        ),
    ]
