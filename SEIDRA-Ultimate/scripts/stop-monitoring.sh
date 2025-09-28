#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
COMPOSE_FILE=${COMPOSE_FILE:-$ROOT_DIR/docker-compose.dev.yml}
SERVICES=(prometheus grafana loki tempo promtail)

cd "$ROOT_DIR"

echo "[monitoring] Arrêt de la stack d'observabilité (${SERVICES[*]})..."
docker compose -f "$COMPOSE_FILE" stop "${SERVICES[@]}"
docker compose -f "$COMPOSE_FILE" rm -f "${SERVICES[@]}" >/dev/null

echo "[monitoring] Stack arrêtée. Les volumes persistants sont conservés."
