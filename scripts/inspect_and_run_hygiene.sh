#!/bin/bash
set -euo pipefail
cd /var/www/one9founders

ACTION="${HYGIENE_ACTION:-scheduled}"
LIMIT="${HYGIENE_LIMIT:-4000}"

echo "===== CONTAINERS ====="
# If a previous deploy died after compose down, bring existing images back
# before we try to exec into them.
docker compose up -d --no-build || docker compose up -d || true
docker compose ps

echo "===== ENV PRESENT (names only) ====="
python3 -c "
from pathlib import Path
text = Path('.env').read_text()
for key in (
    'OPENAI_API_KEY',
    'TRANCO_DB_PATH',
    'HYGIENE_ENRICH_MODEL',
    'GOOGLE_SEARCH_API_KEY',
    'GOOGLE_SEARCH_CX',
):
    present = any(
        line.startswith(key + '=') and line.split('=', 1)[1].strip()
        for line in text.splitlines()
    )
    print(key, 'yes' if present else 'NO')
"

echo "===== ACTION ${ACTION} limit=${LIMIT} ====="

echo "===== DIRECTORY AUDIT ====="
docker compose exec -T web python manage.py audit_directory

crontab -l 2>/dev/null | grep -n hygiene || echo "no hygiene cron"

echo "===== RUNNING HYGIENE / ASSESS ====="
docker compose exec -T web ps aux | grep -E 'hygiene_pass|assess_tools|classify_tracks' | grep -v grep || echo "IDLE"

start_detached() {
  local label="$1"
  shift
  echo "===== START ${label} ====="
  docker compose exec --detach -T web python manage.py "$@"
  sleep 5
  docker compose exec -T web ps aux | grep -E 'manage.py|hygiene_pass|refresh_tranco|assess_tools' | grep -v grep || echo "process not visible yet"
}

refresh_tranco_if_due() {
  # Monthly, or whenever the action is explicitly refresh-tranco.
  if [ "${ACTION}" = "refresh-tranco" ] || [ "$(date -u +%d)" = "01" ]; then
    echo "===== REFRESH TRANCO ====="
    docker compose exec -T web python manage.py refresh_tranco
  fi
}

case "${ACTION}" in
  inspect|audit)
    echo "Inspect/audit only; no hygiene process started."
    ;;
  refresh-tranco)
    docker compose exec -T web python manage.py refresh_tranco
    ;;
  free-dry)
    echo "===== FREE DRY RUN (200 rows, no LLM) ====="
    docker compose exec -T web python manage.py hygiene_pass --limit 200 --no-llm
    ;;
  inspect-and-free|free)
    refresh_tranco_if_due
    start_detached "free-unchecked" \
      hygiene_pass --only-unchecked --limit "${LIMIT}" --no-llm --apply
    ;;
  full-free)
    echo "===== REFRESH TRANCO ====="
    docker compose exec -T web python manage.py refresh_tranco
    start_detached "full-free" \
      hygiene_pass --limit 0 --no-llm --apply
    ;;
  paid-dry|llm-dry)
    echo "===== LLM DRY RUN (25 products) ====="
    docker compose exec -T web python manage.py hygiene_pass --limit 25 --entry-type product
    ;;
  paid-sample|llm-sample)
    start_detached "llm-sample" \
      hygiene_pass --limit 25 --entry-type product --apply
    ;;
  inspect-and-paid|paid|llm)
    start_detached "llm-stale-products" \
      hygiene_pass --entry-type product --stale-days 30 --limit "${LIMIT}" --apply
    ;;
  scheduled)
    refresh_tranco_if_due
    start_detached "scheduled-stale" \
      hygiene_pass --stale-days 30 --limit "${LIMIT}" --no-llm --apply
    ;;
  classify-tracks)
    echo "===== CLASSIFY TRACKS ====="
    docker compose exec -T web python manage.py classify_tracks --apply
    ;;
  assess-sample)
    echo "===== ASSESS SAMPLE (25 ai_tool, dry-run) ====="
    docker compose exec -T web python manage.py assess_tools --limit 25 --track ai_tool --budget-usd 5
    ;;
  assess)
    if docker compose exec -T web pgrep -f "hygiene_pass|assess_tools" > /dev/null 2>&1; then
      echo "A hygiene or assess job is already running; not starting a second pass."
      docker compose exec -T web ps aux | grep -E 'hygiene_pass|assess_tools' | grep -v grep || true
      exit 0
    fi
    echo "===== CLASSIFY TRACKS (before assess) ====="
    docker compose exec -T web python manage.py classify_tracks --apply
    start_detached "assess-all" \
      assess_tools --limit 0 --apply --budget-usd 40
    ;;
  *)
    echo "Unknown HYGIENE_ACTION=${ACTION}" >&2
    exit 1
    ;;
esac
