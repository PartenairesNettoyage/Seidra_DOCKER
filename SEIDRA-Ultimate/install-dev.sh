#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="SEIDRA Ultimate"

function info() {
    printf '\033[1;34m[setup]\033[0m %s\n' "$1"
}

function warn() {
    printf '\033[1;33m[setup]\033[0m %s\n' "$1"
}

function ensure_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        warn "La commande '$1' est requise mais introuvable. Veuillez l'installer puis relancer le script."
        exit 1
    fi
}

function detect_shell_rc() {
    if [[ -n "${ZSH_VERSION:-}" ]]; then
        echo "$HOME/.zshrc"
    elif [[ -n "${BASH_VERSION:-}" ]]; then
        echo "$HOME/.bashrc"
    else
        echo "$HOME/.profile"
    fi
}

WITH_ML=0
START_SERVICES=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-ml)
            WITH_ML=1
            shift
            ;;
        --start)
            START_SERVICES=1
            shift
            ;;
        *)
            warn "Option inconnue: $1"
            exit 1
            ;;
    esac
done

info "Initialisation de l'environnement ${PROJECT_NAME} (mode développement)"

ensure_command python3
ensure_command node
ensure_command npm
ensure_command docker
if ! docker compose version >/dev/null 2>&1; then
    ensure_command docker-compose
fi

PYTHON_VERSION_RAW=$(python3 --version 2>&1 | awk '{print $2}')
PY_MAJOR=$(echo "$PYTHON_VERSION_RAW" | cut -d. -f1)
PY_MINOR=$(echo "$PYTHON_VERSION_RAW" | cut -d. -f2)
if [[ -z "$PY_MAJOR" || -z "$PY_MINOR" ]]; then
    warn "Version de Python introuvable (détecté: $PYTHON_VERSION_RAW). Assurez-vous que python3 ≥ 3.11 est installé."
    exit 1
fi
if (( PY_MAJOR < 3 || (PY_MAJOR == 3 && PY_MINOR < 11) )); then
    warn "Python 3.11+ est requis (version détectée: $PYTHON_VERSION_RAW). Veuillez mettre à jour python3." 
    exit 1
fi

cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
    if [[ -f .env.example ]]; then
        info "Création du fichier .env à partir de .env.example"
        cp .env.example .env
    else
        warn "Aucun .env.example trouvé, création d'un .env minimal"
        cat <<'ENV' > .env
SEIDRA_ENV=development
SEIDRA_DEBUG=true
SEIDRA_DATABASE_URL=sqlite:///../data/seidra.db
SEIDRA_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
SEIDRA_ALLOW_SYSTEM_FALLBACK=true
ENV
    fi
fi

VENV_PATH="$ROOT_DIR/.venv"
if [[ ! -d "$VENV_PATH" ]]; then
    info "Création d'un environnement virtuel Python (.venv)"
    python3 -m venv "$VENV_PATH"
fi

# shellcheck disable=SC1090
source "$VENV_PATH/bin/activate"

info "Mise à jour de pip"
pip install --upgrade pip setuptools wheel >/dev/null

REQ_FILE="backend/requirements-dev.txt"
if [[ -f "$REQ_FILE" ]]; then
    info "Installation des dépendances Python (requirements-dev)"
    pip install -r "$REQ_FILE"
else
    warn "Fichier $REQ_FILE introuvable, installation de requirements.txt"
    pip install -r backend/requirements.txt
fi

if [[ "$WITH_ML" -eq 1 && -f backend/requirements-ml.txt ]]; then
    info "Installation des dépendances IA (GPU) — opération longue"
    pip install -r backend/requirements-ml.txt
fi

if [[ -f "$ROOT_DIR/pre-commit-config.yaml" ]]; then
    info "Installation des hooks pre-commit"
    pre-commit install >/dev/null 2>&1 || warn "Impossible d'installer les hooks pre-commit"
fi

deactivate

info "Installation des dépendances frontend (npm ci)"
cd "$ROOT_DIR/frontend"
npm ci >/dev/null 2>&1 || npm install >/dev/null

if [[ "$START_SERVICES" -eq 1 ]]; then
    info "Préparation de l'infrastructure Docker de développement"
    cd "$ROOT_DIR"
    if docker compose version >/dev/null 2>&1; then
        docker compose -f docker-compose.dev.yml up -d
    else
        docker-compose -f docker-compose.dev.yml up -d
    fi
fi

cat <<'SUMMARY'

✅ Environnement de développement initialisé.

Commandes utiles :
  - source .venv/bin/activate   # activer l'environnement Python
  - make dev-backend            # lancer l'API avec hot reload
  - make dev-frontend           # lancer le frontend Next.js
  - make check                  # exécuter l'ensemble des contrôles QA
SUMMARY

RC_FILE="$(detect_shell_rc)"
warn "Pensez à ajouter 'source $VENV_PATH/bin/activate' à $RC_FILE si nécessaire."

info "Setup terminé."
