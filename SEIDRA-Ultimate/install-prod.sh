#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_NAME="seidra-ultimate"
COMPOSE_FILE="$ROOT_DIR/deploy/docker/production.yml"

printf '\033[1;34m[deploy]\033[0m Préparation du déploiement %s\n' "$STACK_NAME"

if ! command -v docker >/dev/null 2>&1; then
    printf '\033[1;31m[deploy]\033[0m Docker est requis pour ce script.\n' >&2
    exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
    printf '\033[1;33m[deploy]\033[0m Fichier %s introuvable, création de l'ossature par défaut.\n' "$COMPOSE_FILE"
    mkdir -p "$(dirname "$COMPOSE_FILE")"
    cat <<'YML' > "$COMPOSE_FILE"
version: "3.9"
services:
  backend:
    image: ghcr.io/seidra/ultimate-backend:latest
    env_file: ../../.env
    restart: unless-stopped
    ports:
      - "8000:8000"
    depends_on:
      - redis
      - minio
  frontend:
    image: ghcr.io/seidra/ultimate-frontend:latest
    restart: unless-stopped
    environment:
      - NEXT_PUBLIC_API_URL=/api
    ports:
      - "3000:3000"
    depends_on:
      - backend
  redis:
    image: redis:7-alpine
    restart: unless-stopped
  minio:
    image: minio/minio:RELEASE.2023-11-20T22-40-07Z
    command: server /data --console-address :9001
    environment:
      MINIO_ROOT_USER: admin
      MINIO_ROOT_PASSWORD: password
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio-data:/data
volumes:
  minio-data:
YML
fi

if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

$DOCKER_COMPOSE -f "$COMPOSE_FILE" pull
$DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d

printf '\033[1;34m[deploy]\033[0m Déploiement initialisé. API disponible sur http://localhost:8000, frontend sur http://localhost:3000\n'
