#!/bin/bash
# One-shot: inspect, then classify_tracks, then a 25-row assess dry-run.
# Never starts the overnight assess_tools --apply pass.
set -euo pipefail
cd /var/www/one9founders

echo "===== CONTAINERS ====="
docker compose up -d --no-build || docker compose up -d || true
docker compose ps

echo "===== ENV PRESENT (names only) ====="
python3 -c "
from pathlib import Path
text = Path('.env').read_text()
for key in (
    'OPENAI_API_KEY',
    'HYGIENE_ASSESS_MODEL',
    'HYGIENE_ENRICH_MODEL',
):
    present = any(
        line.startswith(key + '=') and line.split('=', 1)[1].strip()
        for line in text.splitlines()
    )
    print(key, 'yes' if present else 'NO')
"

echo "===== GIT ====="
git rev-parse --short HEAD
git log -1 --oneline

echo "===== DIRECTORY AUDIT ====="
docker compose exec -T web python manage.py audit_directory

echo "===== RUNNING HYGIENE / ASSESS ====="
if docker compose exec -T web pgrep -af "hygiene_pass|assess_tools" > /dev/null 2>&1; then
  echo "NOT IDLE — a hygiene or assess job is already running. Stopping."
  docker compose exec -T web ps aux | grep -E 'hygiene_pass|assess_tools' | grep -v grep || true
  exit 1
fi
echo "IDLE"

echo "===== CLASSIFY TRACKS ====="
echo "Already applied in the previous run; not repeating."

echo "===== ASSESS SAMPLE (25 ai_tool, dry-run, budget \$5, batches of 5) ====="
# Batches avoid a process-wide evidence cache plus gunicorn sharing one
# cgroup; the first 25-row attempt was SIGKILL'd (137) after 11 model calls.
for offset in 0 5 10 15 20; do
  echo "----- offset ${offset} -----"
  docker compose exec -T -e PYTHONUNBUFFERED=1 web \
    python manage.py assess_tools --limit 5 --offset "${offset}" --track ai_tool --budget-usd 5
done

echo "===== ASSESS LOGS ====="
docker compose exec -T web sh -c '
  ls -t /app/backend/enrichment-logs/*.json 2>/dev/null | head -8 | while read -r f; do
    echo "----- $f -----"
    cat "$f"
  done
'

echo "===== DONE (no overnight assess started) ====="
