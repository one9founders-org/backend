from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0028_alter_externaltoolcandidate_source_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="toolsubmission",
            name="listed_email_sent_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="When we emailed the submitter that their tool is live.",
                null=True,
            ),
        ),
    ]
