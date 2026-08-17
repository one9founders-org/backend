#!/bin/bash
set -euo pipefail
cd /var/www/one9founders

echo "===== FETCH SCRAPER FROM origin/main ====="
git fetch origin main
git checkout origin/main -- \
  agents/discovery \
  agents/management/commands/scrape_agents.py \
  agents/management/commands/import_agents.py

WEB_ID="$(docker compose ps -q web)"
if [ -z "$WEB_ID" ]; then
  echo "web container is not running"
  docker compose ps
  exit 1
fi

echo "===== COPY SCRAPER INTO WEB CONTAINER ====="
docker exec "$WEB_ID" mkdir -p \
  /app/backend/agents/discovery \
  /app/backend/agents/management/commands

docker cp agents/discovery/. "$WEB_ID":/app/backend/agents/discovery/
docker cp agents/management/commands/scrape_agents.py \
  "$WEB_ID":/app/backend/agents/management/commands/scrape_agents.py
docker cp agents/management/commands/import_agents.py \
  "$WEB_ID":/app/backend/agents/management/commands/import_agents.py

echo "===== BEFORE ====="
docker compose exec -T web python manage.py shell -c \
  'from agents.models import AIAgent, AgentCategory; print("agents", AIAgent.objects.count()); print("categories", AgentCategory.objects.count())'

echo "===== SCRAPE ====="
docker compose exec -T web python manage.py scrape_agents

echo "===== AFTER ====="
docker compose exec -T web python manage.py shell -c \
  'from agents.models import AIAgent, AgentCategory; print("agents", AIAgent.objects.count()); print("categories", AgentCategory.objects.count())'

if ! crontab -l 2>/dev/null | grep -q 'scrape_agents'; then
  (
    crontab -l 2>/dev/null || true
    echo '30 4 * * 1 cd /var/www/one9founders && docker compose exec -T web python manage.py scrape_agents >> /var/log/agent-scrape.log 2>&1'
  ) | crontab -
  echo "Installed weekly scrape_agents cron."
fi

echo "Agent scrape complete."
