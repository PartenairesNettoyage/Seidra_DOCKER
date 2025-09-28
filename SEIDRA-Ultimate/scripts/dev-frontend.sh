#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

cd "$FRONTEND_DIR"

if command -v npm >/dev/null 2>&1; then
    npm run dev
else
    echo "npm est requis pour lancer le frontend" >&2
    exit 1
fi
