from django.db import migrations


class Migration(migrations.Migration):
    """Join the two 0022 leaves that landed on main independently."""

    dependencies = [
        ("api", "0022_jobstack"),
        ("api", "0022_tool_track_and_assessment_detail"),
    ]

    operations = []
