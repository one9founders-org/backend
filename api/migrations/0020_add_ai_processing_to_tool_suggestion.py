import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0019_populate_domain_from_website"),
    ]

    operations = [
        migrations.AlterField(
            model_name="toolsuggestion",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("reviewed", "Reviewed"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="toolsuggestion",
            name="is_ai_tool",
            field=models.BooleanField(
                blank=True,
                help_text="AI verification result",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="toolsuggestion",
            name="ai_reason",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Why AI classified it this way",
            ),
        ),
        migrations.AddField(
            model_name="toolsuggestion",
            name="generated_data",
            field=models.JSONField(
                blank=True,
                help_text="OpenAI-generated tool data",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="toolsuggestion",
            name="processed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="toolsuggestion",
            name="auto_created_tool",
            field=models.ForeignKey(
                blank=True,
                help_text="The draft Tool created from this suggestion",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="suggestions",
                to="api.tool",
            ),
        ),
    ]
