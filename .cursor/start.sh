#!/usr/bin/env bash
# Per-boot service reconciliation: bring up PostgreSQL + Redis, ensure the
# database/role/extension exist, and apply migrations. Idempotent and safe to
# re-run. Long-running dev servers live in `terminals`, not here.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
cd "$BACKEND_DIR"

echo "==> Starting PostgreSQL"
if command -v pg_lsclusters >/dev/null 2>&1; then
  if ! pg_lsclusters -h 2>/dev/null | awk '{print $4}' | grep -q online; then
    sudo pg_ctlcluster 16 main start || true
  fi
fi

echo "==> Waiting for PostgreSQL to accept connections"
for _ in $(seq 1 30); do
  if sudo -u postgres pg_isready -q 2>/dev/null; then break; fi
  sleep 1
done

echo "==> Ensuring role, database, and pgvector extension"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='one9user') THEN
    CREATE ROLE one9user LOGIN PASSWORD 'one9pass' SUPERUSER;
  END IF;
END $$;
SQL
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='one9data'" \
  | grep -q 1 || sudo -u postgres createdb -O one9user one9data
sudo -u postgres psql -d one9data -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "==> Starting Redis"
if ! redis-cli ping >/dev/null 2>&1; then
  sudo redis-server /etc/redis/redis.conf --daemonize yes \
    || redis-server --daemonize yes
fi

echo "==> Applying Django migrations"
export PATH="$HOME/.local/bin:$PATH"
# shellcheck disable=SC1091
source venv/bin/activate
python manage.py migrate --noinput

echo "==> start.sh complete"
