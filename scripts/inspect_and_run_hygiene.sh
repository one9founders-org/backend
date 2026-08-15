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
    'GOOGLE_SEARCH_API_KEY',
    'GOOGLE_SEARCH_CX',
    'HYGIENE_ENRICH_MODEL',
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

echo "===== RUNNING HYGIENE ====="
docker compose exec -T web ps aux | grep -E 'hygiene_pass' | grep -v grep || echo "no hygiene process"

start_detached() {
  local label="$1"
  shift
  echo "===== START ${label} ====="
  # Same pattern as deploy's run_tool_discovery: compose exec -d is the
  # process that survives after this SSH session. Logging goes to the
  # container's stdout (docker compose logs web).
  docker compose exec --detach -T web python manage.py "$@"
  sleep 5
  docker compose exec -T web ps aux | grep -E 'manage.py|hygiene_pass' | grep -v grep || echo "process not visible yet"
}

case "${ACTION}" in
  inspect|audit)
    echo "Inspect/audit only; no hygiene process started."
    ;;
  free-dry)
    echo "===== FREE DRY RUN (200 rows, no search, no LLM) ====="
    docker compose exec -T web python manage.py hygiene_pass --limit 200 --no-search --no-llm
    ;;
  inspect-and-free|free)
    start_detached "free-unchecked" \
      hygiene_pass --only-unchecked --limit "${LIMIT}" --no-search --no-llm --apply
    ;;
  full-free)
    start_detached "full-free" \
      hygiene_pass --limit 0 --no-search --no-llm --apply
    ;;
  paid-dry)
    echo "===== PAID DRY RUN (25 products) ====="
    docker compose exec -T web python manage.py hygiene_pass --limit 25 --entry-type product
    ;;
  paid-sample)
    start_detached "paid-sample" \
      hygiene_pass --limit 25 --entry-type product --apply
    ;;
  inspect-and-paid|paid)
    start_detached "paid-stale-products" \
      hygiene_pass --entry-type product --stale-days 14 --limit "${LIMIT}" --search-budget "${LIMIT}" --apply
    ;;
  scheduled)
    start_detached "scheduled-unchecked" \
      hygiene_pass --only-unchecked --limit 2500 --no-search --no-llm --apply
    ;;
  *)
    echo "Unknown HYGIENE_ACTION=${ACTION}" >&2
    exit 1
    ;;
esac
