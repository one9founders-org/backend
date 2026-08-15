#!/bin/bash
set -euo pipefail
cd /var/www/one9founders

echo "===== docker info ====="
docker info >/dev/null && echo "docker daemon ok" || echo "docker daemon NOT ok"

echo "===== compose ps (before) ====="
docker compose ps -a || true

echo "===== bring stack up without rebuild ====="
docker compose up -d --no-build || docker compose up -d

echo "===== compose ps (after) ====="
docker compose ps -a || true

echo "===== local health ====="
sleep 3
curl -sS -m 8 -A "Mozilla/5.0" "http://127.0.0.1/health/" || echo "local health failed"
echo
curl -sS -m 8 -A "Mozilla/5.0" "http://127.0.0.1:8000/health/" || echo "web:8000 health failed"
echo
echo "===== git ====="
git rev-parse --short HEAD
git log -1 --oneline
