#!/bin/bash
set -euo pipefail
cd /var/www/one9founders
echo "===== GIT $(git rev-parse --short HEAD) ====="
echo "===== PIDFILE ====="
if [ -f /var/tmp/assess_batch.pid ]; then
  pid=$(cat /var/tmp/assess_batch.pid)
  if kill -0 "$pid" 2>/dev/null; then
    echo "batch loop alive pid=$pid"
  else
    echo "pidfile $pid is dead"
  fi
else
  echo "no pidfile"
fi
pgrep -af "/var/tmp/assess_batch.sh" || echo "no assess_batch.sh process"
echo "===== COUNTS ====="
docker compose exec -T web python manage.py shell -c "
from django.db.models import Count, Avg
from api.models import Tool
print('assessed', Tool.objects.filter(criteria_completed__gt=0).count())
print('provisional', Tool.objects.filter(overall_score__isnull=False).count())
print('last_assessed', Tool.objects.filter(last_assessed_at__isnull=False).count())
qs=Tool.objects.filter(overall_score__isnull=False)
print('avg_overall', qs.aggregate(Avg('overall_score'))['overall_score__avg'])
print('distribution')
for row in Tool.objects.values('criteria_completed').annotate(n=Count('id')).order_by('criteria_completed'):
    print(row['criteria_completed'], row['n'])
"
echo "===== LOG TAIL ====="
tail -25 /var/tmp/assess_batch.log 2>/dev/null || echo "no batch log"
