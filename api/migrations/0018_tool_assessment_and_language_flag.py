from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0017_foundersurvey"),
    ]

    operations = [
        migrations.AddField(
            model_name="tool",
            name="criteria_completed",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Count of the 10 methodology criteria scored for this tool (0-10)",
            ),
        ),
        migrations.AddField(
            model_name="tool",
            name="overall_score",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Editorial score 0-5. Only set when criteria_completed >= 6.",
                max_digits=3,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="tool",
            name="security_criterion_score",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Score for Security & Data Privacy criterion, 0-20. Null = not assessed.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="tool",
            name="last_assessed_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When scoring criteria were last updated.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="tool",
            name="language_review_needed",
            field=models.BooleanField(
                default=False,
                help_text="True when description failed the English-language lint.",
            ),
        ),
    ]
