from django.db import migrations


def seed_credit(apps, schema_editor):
    from api.fintech import CREDIT_REVIEWED_AT, CREDIT_VENDORS, seed_stack

    seed_stack(
        CREDIT_VENDORS,
        stack="credit",
        reviewed_at=CREDIT_REVIEWED_AT,
        check_model=apps.get_model("api", "FintechCheck"),
        rating_model=apps.get_model("api", "FintechRating"),
        tool_model=apps.get_model("api", "Tool"),
    )


def unseed_credit(apps, schema_editor):
    FintechRating = apps.get_model("api", "FintechRating")
    FintechRating.objects.filter(stack="credit").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0024_fintech_check_and_rating"),
    ]

    operations = [
        migrations.RunPython(seed_credit, unseed_credit),
    ]
