#!/usr/bin/env bash
# Deploy/refresh the LexPar AI production stack on the droplet (ARCHITECTURE §10).
# Idempotent thin wrapper: builds what changed, (re)starts what changed, leaves the rest running.
# Expects a filled-in .env.prod at the repo root (see .env.prod.example).
#
# Usage (from anywhere):  ./infra/deploy.sh            # full stack
#                         ./infra/deploy.sh backend    # one service
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env.prod ]]; then
  echo "ERROR: .env.prod not found at the repo root. Copy .env.prod.example and fill it in." >&2
  exit 1
fi

docker compose --env-file .env.prod -f infra/docker-compose.prod.yml up -d --build "$@"

echo
docker compose --env-file .env.prod -f infra/docker-compose.prod.yml ps
