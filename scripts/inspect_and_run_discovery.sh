#!/bin/bash
set -euo pipefail
cd /var/www/one9founders

echo "===== START CONTAINERS ====="
docker compose up -d
sleep 8

echo "===== CONTAINERS ====="
docker compose ps

echo "===== ENV PRESENT (names only) ====="
python3 -c "
from pathlib import Path
text = Path('.env').read_text()
for key in ('OPENAI_API_KEY', 'GITHUB_TOKEN', 'DISCOVERY_TRIGGER_SECRET'):
    present = any(
        line.startswith(key + '=') and line.split('=', 1)[1].strip()
        for line in text.splitlines()
    )
    print(key, 'yes' if present else 'NO')
"

echo "===== OPENAI KEY CHECK ====="
python3 -c "
from pathlib import Path
text = Path('.env').read_text()
key = ''
for line in text.splitlines():
    if line.startswith('OPENAI_API_KEY='):
        key = line.split('=', 1)[1].strip().strip('\"').strip(\"'\")
        break
print('present', bool(key))
print('prefix', (key[:8] + '...') if key else 'missing')
print('suffix', ('...' + key[-4:]) if len(key) >= 4 else 'missing')
print('length', len(key))
print('kind', 'project' if key.startswith('sk-proj-') else 'legacy' if key.startswith('sk-') else 'unknown')
"

echo "===== OPENAI LIVE PING ====="
docker compose exec -T web python -c '
from django.conf import settings
from openai import OpenAI
key = settings.OPENAI_API_KEY or ""
print("django_key_suffix", ("..." + key[-4:]) if len(key) >= 4 else "missing")
client = OpenAI(api_key=key)
try:
    resp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Reply with the single word pong"}],
        max_tokens=5,
    )
    print("chat_ok", (resp.choices[0].message.content or "").strip())
except Exception as exc:
    print("chat_error", type(exc).__name__)
    print(str(exc)[:500])
'

crontab -l 2>/dev/null | grep -n discover || echo "no discovery cron"

echo "===== RUNNING DISCOVERY ====="
docker compose exec -T web ps aux | grep -E 'run_tool_discovery|discover' | grep -v grep || echo "no discovery process"

echo "===== FIX ORPHAN NOT NULL ====="
docker compose exec -T web python manage.py shell -c '
from django.db import connection
from api.models import Tool

model_cols = {field.column for field in Tool._meta.local_fields}
qn = connection.ops.quote_name
with connection.cursor() as cursor:
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
          AND is_nullable = %s
          AND column_default IS NULL
        ORDER BY column_name
        """,
        ["public", "tools", "NO"],
    )
    orphans = [name for (name,) in cursor.fetchall() if name not in model_cols]
    if not orphans:
        print("no_orphan_not_null")
    for name in orphans:
        cursor.execute(
            "ALTER TABLE %s ALTER COLUMN %s DROP NOT NULL"
            % (qn("tools"), qn(name))
        )
        print("dropped_not_null", name)
    cursor.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
          AND is_nullable = %s
          AND column_default IS NULL
        ORDER BY column_name
        """,
        ["public", "tools", "NO"],
    )
    print("remaining_not_null_no_default")
    for name, dtype in cursor.fetchall():
        print(name, dtype)
'

echo "===== DISCOVERY DB ====="
docker compose exec -T web python manage.py shell -c '
from django.db.models import Count
from api.models import DiscoveryRun, Tool
print("tools", Tool.objects.count())
print("active", Tool.objects.filter(is_active=True).count())
print("auto_tag", Tool.objects.filter(tags__contains=["auto-discovery"]).count())
print("by_status", list(DiscoveryRun.objects.values("status").annotate(n=Count("id"))))
print("by_type", list(DiscoveryRun.objects.values("run_type").annotate(n=Count("id"))))
for row in DiscoveryRun.objects.order_by("-id")[:20]:
    print(row.created_at, row.run_type, row.status, row.tool_name, (row.reasons or "")[:180])
'

echo "===== CANDIDATES (dry) ====="
docker compose exec -T web python manage.py discover_candidates

if [ "${DISCOVERY_ACTION:-inspect-and-run}" = "inspect-and-run" ]; then
  echo "===== START RUN ====="
  docker compose exec -T web bash -lc '
    for pat in run_tool_discovery discover_india; do
      pids=$(ps aux | grep "$pat" | grep -v grep | awk "{print \$2}")
      if [ -n "$pids" ]; then
        echo "killing $pat: $pids"
        kill $pids 2>/dev/null || true
      else
        echo "no $pat process"
      fi
    done
  '

  docker compose exec -d web python manage.py run_tool_discovery
  sleep 5
  docker compose exec -T web ps aux | grep run_tool_discovery | grep -v grep || echo "process not visible yet"
  echo "Started detached run_tool_discovery"
fi
