#!/bin/bash
set -euo pipefail
cd /var/www/one9founders

echo "===== CONTAINERS ====="
docker compose ps

echo "===== ENV PRESENT (names only) ====="
python3 -c "
from pathlib import Path
text = Path('.env').read_text()
for key in ('OPENAI_API_KEY', 'GITHUB_TOKEN', 'DISCOVERY_TRIGGER_SECRET'):
    present = any(
        line.startswith(key + '=') and line.split('=', 1)[1].strip()
        for line in text.splitlines()
    )
    print(key, 'yes' if present else 'NO')
"

echo "===== CRON ====="
crontab -l 2>/dev/null | grep -n discover || echo "no discovery cron"

echo "===== RUNNING DISCOVERY ====="
docker compose exec -T web ps aux | grep -E 'run_tool_discovery|discover' | grep -v grep || echo "no discovery process"

echo "===== DISCOVERY DB ====="
docker compose exec -T web python manage.py shell -c '
from django.db.models import Count
from api.models import DiscoveryRun, Tool
print("tools", Tool.objects.count())
print("active", Tool.objects.filter(is_active=True).count())
print("auto_tag", Tool.objects.filter(tags__contains=["auto-discovery"]).count())
print("by_status", list(DiscoveryRun.objects.values("status").annotate(n=Count("id"))))
print("by_type", list(DiscoveryRun.objects.values("run_type").annotate(n=Count("id"))))
for row in DiscoveryRun.objects.order_by("-id")[:20]:
    print(row.created_at, row.run_type, row.status, row.tool_name, (row.reasons or "")[:180])
'

echo "===== CANDIDATES (dry) ====="
docker compose exec -T web python manage.py discover_candidates

if [ "${DISCOVERY_ACTION:-inspect-and-run}" = "inspect-and-run" ]; then
  echo "===== START RUN ====="
  docker compose exec -T web bash -lc 'nohup python manage.py run_tool_discovery > /tmp/tool-discovery.log 2>&1 &'
  sleep 3
  docker compose exec -T web ps aux | grep run_tool_discovery | grep -v grep || echo "process not visible yet"
  docker compose exec -T web tail -n 40 /tmp/tool-discovery.log || true
  echo "Started detached run_tool_discovery"
fi
