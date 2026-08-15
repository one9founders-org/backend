#!/bin/bash
set -euo pipefail
cd /var/www/one9founders

ACTION="${HYGIENE_ACTION:-scheduled}"
LIMIT="${HYGIENE_LIMIT:-4000}"

echo "===== CONTAINERS ====="
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
  # exec -d keeps the process in the container after this SSH session ends.
  # nohup inside `compose exec -T` is reaped when the exec exits.
  docker compose exec -d web bash -lc "python manage.py $* > /tmp/hygiene-pass.log 2>&1 && python manage.py build_faiss_index >> /tmp/hygiene-pass.log 2>&1"
  sleep 5
  docker compose exec -T web ps aux | grep -E 'hygiene_pass|build_faiss_index' | grep -v grep || echo "process not visible yet"
  docker compose exec -T web tail -n 40 /tmp/hygiene-pass.log || true
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
    echo "===== START scheduled chain ====="
    docker compose exec -d web bash -lc "python manage.py hygiene_pass --only-unchecked --limit 2500 --no-search --no-llm --apply > /tmp/hygiene-pass.log 2>&1 && python manage.py hygiene_pass --entry-type product --stale-days 14 --limit ${LIMIT} --search-budget ${LIMIT} --apply >> /tmp/hygiene-pass.log 2>&1 && python manage.py build_faiss_index >> /tmp/hygiene-pass.log 2>&1"
    sleep 5
    docker compose exec -T web ps aux | grep -E 'hygiene_pass|build_faiss_index' | grep -v grep || echo "process not visible yet"
    docker compose exec -T web tail -n 40 /tmp/hygiene-pass.log || true
    ;;
  *)
    echo "Unknown HYGIENE_ACTION=${ACTION}" >&2
    exit 1
    ;;
esac
