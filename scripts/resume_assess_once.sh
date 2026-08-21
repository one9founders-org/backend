#!/bin/bash
# Resume assess_tools from last_assessed_at. One host-side loop.
# Do not merge this branch.
set -euo pipefail
cd /var/www/one9founders

echo "===== GIT $(git rev-parse --short HEAD) ====="
git log -1 --oneline

echo "===== COUNTS ====="
docker compose exec -T web python manage.py shell -c "
from api.models import Tool
print('assessed', Tool.objects.filter(criteria_completed__gt=0).count())
print('provisional', Tool.objects.filter(overall_score__isnull=False).count())
print('last_assessed', Tool.objects.filter(last_assessed_at__isnull=False).count())
print('unassessed', Tool.objects.filter(last_assessed_at__isnull=True).exclude(website='').count())
"

PIDFILE=/var/tmp/assess_batch.pid
if [ -f "$PIDFILE" ]; then
  old=$(cat "$PIDFILE")
  if kill -0 "$old" 2>/dev/null; then
    echo "===== already running pid=$old — not starting a second pass ====="
    tail -20 /var/tmp/assess_batch.log || true
    exit 0
  fi
  echo "stale pidfile $old"
fi

echo "===== starting host batch loop ====="
cat > /var/tmp/assess_batch.sh << 'ENDSCRIPT'
#!/bin/bash
set -u
cd /var/www/one9founders
SPENT=0
CAP=40
LOG=/var/tmp/assess_batch.log
echo "==== resume $(date -u) cap=$CAP ====" >> "$LOG"
consecutive_empty=0
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
  updated=$(printf '%s\n' "$out" | sed -n 's/.*Updated:[[:space:]]*\([0-9]*\).*/\1/p' | tail -1)
  SPENT=$(python3 -c "print(round($SPENT + float('${batch_spent:-0}' or 0), 6))")
  echo "after processed=${processed:-0} updated=${updated:-0} batch_spent=${batch_spent:-0} total=$SPENT" >> "$LOG"

  if printf '%s\n' "$out" | grep -q 'Aborted:'; then
    echo "stop aborted $(date -u)" >> "$LOG"
    break
  fi

  # Daily request cap: wait and retry instead of treating the batch as done.
  if printf '%s\n' "$out" | grep -q '429\|Rate limit reached'; then
    echo "rate_limit sleep 120 $(date -u)" >> "$LOG"
    consecutive_empty=0
    sleep 120
    continue
  fi

  if [ "${processed:-0}" -eq 0 ]; then
    consecutive_empty=$((consecutive_empty + 1))
    echo "empty_batch n=$consecutive_empty $(date -u)" >> "$LOG"
    if [ "$consecutive_empty" -ge 2 ]; then
      echo "stop processed=0 $(date -u)" >> "$LOG"
      break
    fi
    sleep 30
    continue
  fi
  consecutive_empty=0
  # Stay under ~10k requests/day (~7 tools/min). A batch of 8 already
  # takes ~70s; add 25s so a full day does not hit the RPD wall again.
  sleep 25
done
echo "==== done spent=$SPENT $(date -u) ====" >> "$LOG"
ENDSCRIPT
chmod +x /var/tmp/assess_batch.sh
nohup /var/tmp/assess_batch.sh >/var/tmp/assess_batch.nohup 2>&1 &
echo $! > "$PIDFILE"
echo "started pid $!"
sleep 20
if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "pid_alive $(cat "$PIDFILE")"
else
  echo "pid_died"
  cat /var/tmp/assess_batch.nohup || true
  exit 1
fi
echo "===== LOG TAIL ====="
tail -25 /var/tmp/assess_batch.log || true
