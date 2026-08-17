#!/bin/bash
# Host-side batch loop: 8 tools per process (the 25-row in-container job
# SIGKILL'd). Cumulative spend cap $40. Survives SSH via nohup.
set -euo pipefail
cd /var/www/one9founders

echo "===== GIT ====="
git rev-parse --short HEAD
git log -1 --oneline

echo "===== PROCESS ====="
docker compose exec -T web ps aux | grep -E 'hygiene_pass|assess_tools' | grep -v grep || echo "no assess_tools in container"
pgrep -af "assess_loop" || echo "no host assess_loop"

echo "===== COUNTS ====="
docker compose exec -T web python manage.py shell -c "
from django.db.models import Count
from api.models import Tool
print('assessed:', Tool.objects.filter(criteria_completed__gt=0).count())
print('provisional+:', Tool.objects.filter(overall_score__isnull=False).count())
print('last_assessed:', Tool.objects.filter(last_assessed_at__isnull=False).count())
"

if pgrep -f "/var/tmp/assess_loop.sh" >/dev/null 2>&1; then
  echo "===== assess_loop already running — not starting a second ====="
  tail -30 /var/tmp/assess_loop.log || true
  exit 0
fi
if docker compose exec -T web pgrep -f "assess_tools" >/dev/null 2>&1; then
  echo "===== assess_tools already running — not starting a second ====="
  exit 0
fi

cat > /var/tmp/assess_loop.sh << 'EOF'
#!/bin/bash
set -u
cd /var/www/one9founders
SPENT=0
CAP=40
LOG=/var/tmp/assess_loop.log
echo "==== start $(date -u) cap=$CAP ====" >> "$LOG"
while true; do
  remain=$(python3 -c "print(round(max(0.0, $CAP - $SPENT), 4))")
  too_small=$(python3 -c "print(int(float('$remain') < 0.05))")
  if [ "$too_small" = "1" ]; then
    echo "stop budget spent=$SPENT cap=$CAP $(date -u)" >> "$LOG"
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
EOF
chmod +x /var/tmp/assess_loop.sh
nohup /var/tmp/assess_loop.sh >/var/tmp/assess_loop.nohup 2>&1 &
echo "started assess_loop pid $!"
sleep 25
echo "===== LOOP ALIVE ====="
pgrep -af "/var/tmp/assess_loop.sh" || echo "loop not visible"
echo "===== LOG TAIL ====="
tail -40 /var/tmp/assess_loop.log || true
echo "===== CONTAINER ====="
docker compose exec -T web ps aux | grep -E 'assess_tools' | grep -v grep || echo "batch python not visible yet"
