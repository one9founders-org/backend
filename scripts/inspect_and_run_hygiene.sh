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

echo "===== RUNNING HYGIENE ====="
docker compose exec -T web ps aux | grep -E 'hygiene_pass' | grep -v grep || echo "no hygiene process"

start_detached() {
  local label="$1"
  shift
  echo "===== START ${label} ====="
  docker compose exec --detach -T web python manage.py "$@"
  sleep 5
  docker compose exec -T web ps aux | grep -E 'manage.py|hygiene_pass|refresh_tranco' | grep -v grep || echo "process not visible yet"
}

# Used when the running image does not yet have purge_gpt_store.
# Same rule as classify(): chat.openai.com / chatgpt.com only.
purge_gpt_inline() {
  local apply="${1:-0}"
  docker compose exec -T -e APPLY="${apply}" web python - <<'PY'
import json
import os
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from api.hygiene.classify import GPT_STORE, classify
from api.models import Tool
from api.tool_stats import bust_tool_stats_cache

apply = os.environ.get("APPLY") == "1"
rows = []
for tool in Tool.objects.all().only("id", "name", "website", "slug").iterator(
    chunk_size=500
):
    entry_type, _flags = classify(tool.name, tool.website or "")
    if entry_type == GPT_STORE:
        rows.append(
            {
                "id": tool.id,
                "name": tool.name,
                "website": tool.website,
                "slug": tool.slug,
            }
        )

path = Path("/app/backend/data/gpt_store_purge.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({"count": len(rows), "rows": rows}))
print(f"Listed {len(rows):,} GPT-store rows at {path}")
if not apply:
    print("Dry run: nothing deleted. Re-run with delete-gpt to apply.")
else:
    ids = [row["id"] for row in rows]
    deleted = 0
    batch = 200
    for start in range(0, len(ids), batch):
        count, _detail = Tool.objects.filter(pk__in=ids[start : start + batch]).delete()
        deleted += count
        if start and start % 1000 == 0:
            print(f"  progress {start:,}/{len(ids):,}")
    bust_tool_stats_cache()
    print(f"Deleted {deleted:,} database rows (tools + cascaded relations).")
PY
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
  show-log)
    echo "===== LATEST HYGIENE LOG ====="
    docker compose exec -T web python - <<'PY'
import json
from pathlib import Path

logs = sorted(
    Path("/app/backend/enrichment-logs").glob("*.json"),
    key=lambda p: p.stat().st_mtime,
)
if not logs:
    print("no logs")
    raise SystemExit(0)
print("recent logs:")
for item in logs[-6:]:
    print(f"  {item.name}  {item.stat().st_size} bytes")
# Prefer the newest small LLM/dry-run log if one exists; else newest.
path = logs[-1]
for item in reversed(logs):
    if "batch-12" in item.name or item.stat().st_size < 500_000:
        path = item
        break
print(f"showing: {path}")
payload = json.loads(path.read_text())
print(
    f"applied={payload.get('applied')} selected={payload.get('selected')} "
    f"with_changes={payload.get('with_changes')} updated={payload.get('updated')}"
)
print(f"stages={payload.get('stages')}")
for entry in payload.get("entries") or []:
    notes = "; ".join(entry.get("notes") or []) or "-"
    skipped = entry.get("skipped") or ""
    changes = entry.get("changes") or []
    fields = ", ".join(c.get("field") for c in changes)
    print(f"\n# {entry.get('tool_id')} {entry.get('name')}")
    if skipped:
        print(f"  skipped: {skipped}")
    print(f"  notes: {notes}")
    print(f"  fields: {fields or '(none)'}")
    for change in changes:
        field = change.get("field")
        if field in {"short_description", "description", "tags", "use_cases", "pricing_type", "logo_url", "popularity_score", "entry_type"}:
            new = change.get("new_value")
            old = change.get("old_value")
            if isinstance(new, list):
                new = ", ".join(str(x) for x in new[:8])
            if isinstance(old, list):
                old = ", ".join(str(x) for x in old[:4])
            text = str(new or "")
            if len(text) > 220:
                text = text[:217] + "..."
            print(f"  {field}: {text}")
PY
    ;;
  delete-gpt-dry|purge-gpt-dry)
    echo "===== PURGE GPT-STORE (DRY RUN) ====="
    docker compose exec -T web python manage.py purge_gpt_store || purge_gpt_inline 0
    ;;
  delete-gpt|purge-gpt)
    echo "===== PURGE GPT-STORE (APPLY) ====="
    docker compose exec -T web python manage.py purge_gpt_store --apply || purge_gpt_inline 1
    echo "===== REBUILD FAISS ====="
    docker compose exec --detach -T web python manage.py build_faiss_index
    ;;
  rebuild-faiss)
    echo "===== REBUILD FAISS (publishable tools only) ====="
    docker compose exec -T web python manage.py build_faiss_index
    ;;
  *)
    echo "Unknown HYGIENE_ACTION=${ACTION}" >&2
    exit 1
    ;;
esac
