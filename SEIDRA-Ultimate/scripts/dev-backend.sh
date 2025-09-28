#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_PATH="$ROOT_DIR/.venv"

if [[ -d "$VENV_PATH" ]]; then
    # shellcheck disable=SC1090
    source "$VENV_PATH/bin/activate"
fi

export PYTHONPATH="$BACKEND_DIR"
cd "$BACKEND_DIR"

if command -v alembic >/dev/null 2>&1; then
    alembic upgrade head || true
fi

uvicorn main:app --reload --host 0.0.0.0 --port 8000
