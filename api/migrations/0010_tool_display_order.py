from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0009_news_upvote_count_newsupvote"),
    ]

    operations = [
        migrations.AddField(
            model_name="tool",
            name="display_order",
            field=models.IntegerField(
                db_index=True,
                default=9999,
                help_text="Display order on homepage (lower = higher)",
            ),
        ),
        migrations.AlterModelOptions(
            name="tool",
            options={"ordering": ["display_order", "-is_featured", "-rating"]},
        ),
    ]
