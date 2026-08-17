#!/bin/bash
set -euo pipefail
cd /var/www/one9founders

echo "===== GIT ====="
git rev-parse --short HEAD

echo "===== PGREP ====="
docker compose exec -T web pgrep -af python || echo "no python in container"

echo "===== COUNTS ====="
docker compose exec -T web python manage.py shell -c "
from django.db.models import Count
from api.models import Tool
print('assessed', Tool.objects.filter(criteria_completed__gt=0).count())
print('provisional', Tool.objects.filter(overall_score__isnull=False).count())
print('last_assessed', Tool.objects.filter(last_assessed_at__isnull=False).count())
print('distribution')
for row in Tool.objects.values('criteria_completed').annotate(n=Count('id')).order_by('criteria_completed'):
    print(row['criteria_completed'], row['n'])
"

if docker compose exec -T web pgrep -f assess_tools >/dev/null 2>&1; then
  echo "===== RUNNING — leaving the single pass alone ====="
  exit 0
fi

echo "===== NOT RUNNING ====="
if [ -f /var/tmp/assess_batch.pid ] && kill -0 "$(cat /var/tmp/assess_batch.pid)" 2>/dev/null; then
  echo "host batch pid $(cat /var/tmp/assess_batch.pid) alive"
  tail -20 /var/tmp/assess_batch.log || true
  exit 0
fi

echo "===== starting host batch loop ====="
cat > /var/tmp/assess_batch.sh << 'ENDSCRIPT'
#!/bin/bash
set -u
cd /var/www/one9founders
SPENT=0
CAP=40
LOG=/var/tmp/assess_batch.log
echo "==== start $(date -u) cap=$CAP ====" >> "$LOG"
while true; do
  remain=$(python3 -c "print(round(max(0.0, $CAP - $SPENT), 4))")
  if python3 -c "import sys; sys.exit(0 if float('$remain') < 0.05 else 1)"; then
    echo "stop budget spent=$SPENT $(date -u)" >> "$LOG"
    break
  fi
  echo "batch remain=$remain spent=$SPENT $(date -u)" >> "$LOG"
  out=$(docker compose exec -T web python manage.py assess_tools --limit 8 --apply --budget-usd "$remain" 2>&1) || true
  echo "$out" >> "$LOG"
  batch_spent=$(printf '%s\n' "$out" | sed -n 's/.*Spend:[[:space:]]*\$\([0-9.]*\).*/\1/p' | tail -1)
  processed=$(printf '%s\n' "$out" | sed -n 's/.*Processed:[[:space:]]*\([0-9]*\).*/\1/p' | tail -1)
  SPENT=$(python3 -c "print(round($SPENT + float('${batch_spent:-0}' or 0), 6))")
  echo "after processed=${processed:-0} batch_spent=${batch_spent:-0} total=$SPENT" >> "$LOG"
  if printf '%s\n' "$out" | grep -q 'Aborted:'; then
    echo "stop aborted $(date -u)" >> "$LOG"
    break
  fi
  if [ "${processed:-0}" -eq 0 ]; then
    echo "stop processed=0 $(date -u)" >> "$LOG"
    break
  fi
done
echo "==== done spent=$SPENT $(date -u) ====" >> "$LOG"
ENDSCRIPT
chmod +x /var/tmp/assess_batch.sh
nohup /var/tmp/assess_batch.sh >/var/tmp/assess_batch.nohup 2>&1 &
echo $! > /var/tmp/assess_batch.pid
echo started pid $!
sleep 20
kill -0 "$(cat /var/tmp/assess_batch.pid)" && echo pid_alive
tail -20 /var/tmp/assess_batch.log || true
