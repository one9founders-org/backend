#!/bin/bash
# One-shot: point Free AI Music Creator at its real logo (not og.jpg banner).
set -euo pipefail
cd /var/www/one9founders

docker compose exec -T web python manage.py shell -c '
from api.models import Tool, ToolSubmission

slug = "free-ai-music-creator"
logo = "https://musicaura.ai/logo.png"
tool = Tool.objects.filter(slug=slug).first()
if not tool:
    raise SystemExit(f"tool not found: {slug}")

print("before", tool.id, tool.name, tool.logo_url)
tool.logo_url = logo
tool.save(update_fields=["logo_url", "updated_at"])
print("after", tool.logo_url)

updated = ToolSubmission.objects.filter(
    approved_tool=tool
).update(logo_url=logo)
updated += ToolSubmission.objects.filter(
    submitter_email__iexact="zhouwan9001@gmail.com"
).exclude(approved_tool=tool).update(logo_url=logo)
print("submissions_updated", updated)
'
