#!/bin/bash
# One-shot: inspect, then start overnight assess_tools --apply detached.
# Do not merge this branch. Do not start a second pass if one is alive.
set -euo pipefail
cd /var/www/one9founders

echo "===== CONTAINERS ====="
docker compose up -d --no-build || docker compose up -d || true
docker compose ps

echo "===== GIT ====="
git rev-parse --short HEAD
git log -1 --oneline
HEAD=$(git rev-parse --short HEAD)
if [ "$HEAD" != "5a4c48d" ]; then
  echo "Expected SHA 5a4c48d (#87) on the box; found $HEAD. Not starting assess."
  exit 1
fi

echo "===== ENV PRESENT (names only) ====="
python3 -c "
from pathlib import Path
text = Path('.env').read_text()
for key in ('OPENAI_API_KEY', 'HYGIENE_ASSESS_MODEL'):
    present = any(
        line.startswith(key + '=') and line.split('=', 1)[1].strip()
        for line in text.splitlines()
    )
    print(key, 'yes' if present else 'NO (code default gpt-4o-mini)')
"

echo "===== RUNNING HYGIENE / ASSESS ====="
if docker compose exec -T web pgrep -f "hygiene_pass|assess_tools" > /dev/null 2>&1; then
  echo "NOT IDLE — not starting a second pass."
  docker compose exec -T web ps aux | grep -E 'hygiene_pass|assess_tools' | grep -v grep || true
  exit 1
fi
echo "IDLE"

echo "===== START assess_tools --limit 0 --apply --budget-usd 40 ====="
docker compose exec --detach -T -e PYTHONUNBUFFERED=1 web \
  python manage.py assess_tools --limit 0 --apply --budget-usd 40
sleep 8
echo "===== PROCESS ====="
docker compose exec -T web ps aux | grep -E 'assess_tools|manage.py' | grep -v grep || echo "process not visible yet"

echo "===== SNAPSHOT ====="
docker compose exec -T web python manage.py shell -c "
from api.models import Tool
print('assessed:', Tool.objects.filter(criteria_completed__gt=0).count())
print('provisional+:', Tool.objects.filter(overall_score__isnull=False).count())
"
echo "===== STARTED (overnight; SSH will disconnect) ====="
