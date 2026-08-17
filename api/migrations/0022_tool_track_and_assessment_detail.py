from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0021_tool_orphan_column_nulls"),
    ]

    operations = [
        migrations.AddField(
            model_name="tool",
            name="track",
            field=models.CharField(
                choices=[
                    ("ai_tool", "AI tool"),
                    ("ai_agent", "AI agent"),
                    ("open_source", "Open-source repo"),
                    ("agent_skill", "Agent skill"),
                    ("mcp_server", "MCP server"),
                ],
                db_index=True,
                default="ai_tool",
                help_text=(
                    "Kind of directory row: hosted tool, agent, open-source "
                    "repo, skill, or MCP server."
                ),
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="tool",
            name="assessment_detail",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Per-criterion scores with evidence URLs from the last "
                    "assessment."
                ),
            ),
        ),
    ]
