#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
COMPOSE_FILE=${COMPOSE_FILE:-$ROOT_DIR/docker-compose.dev.yml}
SERVICES=(prometheus grafana loki tempo promtail)

cd "$ROOT_DIR"

echo "[monitoring] Démarrage de la stack d'observabilité (${SERVICES[*]})..."
docker compose -f "$COMPOSE_FILE" up -d "${SERVICES[@]}"

echo "[monitoring] Services disponibles :"
echo "  - Prometheus : http://localhost:9090"
echo "  - Grafana    : http://localhost:3001"
echo "  - Loki       : http://localhost:3100"
echo "  - Tempo      : http://localhost:3200"
