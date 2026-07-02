#!/usr/bin/env bash
# 3D Medical CLIP — one-command local bring-up (P1 exit gate).
# Builds and starts the full stack (datastores + backend + frontend), waits for
# health, and prints the service URLs.
#
#   bash scripts/dev_up.sh          # up
#   bash scripts/dev_up.sh down     # stop and remove containers (keeps volumes)
#   bash scripts/dev_up.sh nuke     # stop and remove containers AND volumes
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Function (not a string var) so paths containing spaces are handled correctly.
compose() { docker compose -f "$ROOT/infra/docker-compose.yml" "$@"; }

case "${1:-up}" in
  down) compose down; exit $? ;;
  nuke) compose down -v; exit $? ;;
esac

# Preflight (non-fatal warnings allowed; hard failures stop us).
bash "$ROOT/scripts/env_check.sh" || { echo "Preflight failed; aborting."; exit 1; }

# Ensure a local env file exists (never committed).
if [ ! -f "$ROOT/infra/.env" ]; then
  cp "$ROOT/infra/.env.example" "$ROOT/infra/.env"
  echo "Created infra/.env from template (edit to customize)."
fi

echo "Building and starting the stack..."
compose up -d --build

echo "Waiting for all services to become healthy..."
deadline=$(( $(date +%s) + 180 ))
while :; do
  unhealthy=$(compose ps --format '{{.Health}}' | grep -vcE '^healthy$' || true)
  [ "${unhealthy:-1}" = "0" ] && break
  [ "$(date +%s)" -ge "$deadline" ] && { echo "Timed out waiting for health:"; compose ps; exit 1; }
  sleep 3
done

echo ""
echo "Stack is up:"
echo "  Frontend : http://127.0.0.1:${FRONTEND_PORT:-5173}"
echo "  Backend  : http://127.0.0.1:${BACKEND_PORT:-8000}  (/health, /health/ready, /docs)"
echo "  Postgres : 127.0.0.1:${POSTGRES_PORT:-5432}"
echo "  Redis    : 127.0.0.1:${REDIS_PORT:-6379}"
echo "  Qdrant   : http://127.0.0.1:${QDRANT_HTTP_PORT:-6333}"
compose ps --format '{{.Service}}: {{.Status}}'
