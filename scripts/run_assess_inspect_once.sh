#!/bin/bash
# Inspect only. Restart assess --apply once if nothing is running.
set -euo pipefail
cd /var/www/one9founders

echo "===== GIT ====="
git rev-parse --short HEAD
git log -1 --oneline

echo "===== PROCESS ====="
docker compose exec -T web ps aux | grep -E 'hygiene_pass|assess_tools|manage.py' | grep -v grep || echo "no matching process"

echo "===== COUNTS ====="
docker compose exec -T web python manage.py shell -c "
from django.db.models import Count
from api.models import Tool
print('assessed:', Tool.objects.filter(criteria_completed__gt=0).count())
print('provisional+:', Tool.objects.filter(overall_score__isnull=False).count())
print('last_assessed:', Tool.objects.filter(last_assessed_at__isnull=False).count())
print('distribution:')
for row in Tool.objects.values('criteria_completed').annotate(n=Count('id')).order_by('criteria_completed'):
    print(' ', row['criteria_completed'], row['n'])
"

RUNNING=0
if docker compose exec -T web pgrep -f "assess_tools" > /dev/null 2>&1; then
  RUNNING=1
  echo "===== ALREADY RUNNING — not starting a second pass ====="
fi

if [ "$RUNNING" = "0" ]; then
  echo "===== IDLE — starting one assess_tools --apply ====="
  docker compose exec --detach -T web python manage.py assess_tools --limit 0 --apply --budget-usd 40
  sleep 20
  echo "===== PROCESS AFTER START ====="
  docker compose exec -T web ps aux | grep -E 'assess_tools|manage.py' | grep -v grep || echo "still not visible"
fi
