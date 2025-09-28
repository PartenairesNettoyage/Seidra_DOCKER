#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CHART_PATH="$REPO_ROOT/deploy/helm"

RELEASE_NAME="${RELEASE_NAME:-seidra-ultimate}"
NAMESPACE="${NAMESPACE:-seidra-staging}"
TAG=""
VALUES_FILES=()
EXTRA_SET_ARGS=()
DRY_RUN=false
TIMEOUT="15m"

usage() {
    cat <<'USAGE'
Déploiement staging SEIDRA Ultimate via Helm.

Usage:
  deploy-staging.sh --tag v1.4.2 [options]

Options:
  --tag TAG            Tag de l'image GHCR à déployer (obligatoire).
  --namespace NS       Namespace Kubernetes cible (par défaut: seidra-staging).
  --values FILE        Fichier values.yaml supplémentaire (multi-utilisable).
  --set KEY=VALUE      Injection ponctuelle de valeurs Helm.
  --timeout DURATION   Timeout Helm (par défaut: 15m).
  --dry-run            Exécute Helm en mode dry-run + debug.
  -h, --help           Affiche cette aide.

Variables d'environnement:
  RELEASE_NAME         Nom de la release Helm (par défaut: seidra-ultimate).
  SEIDRA_DATABASE_URL  URL complète de la base PostgreSQL (injectée si définie).
  GHCR_USERNAME/TOKEN  Utilisés pour créer ou mettre à jour le secret image-pull `seidra-ghcr`.
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --tag)
            TAG="$2"
            shift 2
            ;;
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --values)
            VALUES_FILES+=("$2")
            shift 2
            ;;
        --set)
            EXTRA_SET_ARGS+=("--set" "$2")
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Option inconnue: $1" >&2
            usage
            exit 1
            ;;
    esac
done

if [[ -z "$TAG" ]]; then
    echo "Erreur: --tag est obligatoire pour sélectionner l'image GHCR" >&2
    usage
    exit 1
fi

if ! command -v helm >/dev/null 2>&1; then
    echo "Helm n'est pas installé ou introuvable dans PATH" >&2
    exit 1
fi

if ! command -v kubectl >/dev/null 2>&1; then
    echo "kubectl n'est pas installé ou introuvable dans PATH" >&2
    exit 1
fi

if [[ ! -d "$CHART_PATH" ]]; then
    echo "Chart Helm introuvable: $CHART_PATH" >&2
    exit 1
fi

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"

if [[ -n "${GHCR_USERNAME:-}" && -n "${GHCR_TOKEN:-}" ]]; then
    kubectl create secret docker-registry seidra-ghcr \
        --docker-server=ghcr.io \
        --docker-username="$GHCR_USERNAME" \
        --docker-password="$GHCR_TOKEN" \
        --namespace "$NAMESPACE" \
        --dry-run=client -o yaml | kubectl apply -f -
    echo "Secret d'accès GHCR (seidra-ghcr) à jour dans le namespace $NAMESPACE"
fi

HELM_CMD=(helm upgrade --install "$RELEASE_NAME" "$CHART_PATH" \
    --namespace "$NAMESPACE" \
    --create-namespace \
    --atomic \
    --wait \
    --timeout "$TIMEOUT" \
    --set image.tag="$TAG")

if [[ -n "${SEIDRA_DATABASE_URL:-}" ]]; then
    HELM_CMD+=("--set" "env.SEIDRA_DATABASE_URL=${SEIDRA_DATABASE_URL}")
fi

for values in "${VALUES_FILES[@]:-}"; do
    HELM_CMD+=("-f" "$values")
done

HELM_CMD+=("${EXTRA_SET_ARGS[@]:-}")

if $DRY_RUN; then
    HELM_CMD+=(--dry-run --debug)
fi

echo "Commande Helm: ${HELM_CMD[*]}"
"${HELM_CMD[@]}"

if ! $DRY_RUN; then
    kubectl rollout status deployment/seidra-backend -n "$NAMESPACE" --timeout "$TIMEOUT"
    kubectl rollout status deployment/seidra-frontend -n "$NAMESPACE" --timeout "$TIMEOUT"
    kubectl rollout status deployment/seidra-worker -n "$NAMESPACE" --timeout "$TIMEOUT"
fi

cat <<EON
Déploiement terminé. Vérifiez les endpoints:
  kubectl get pods -n $NAMESPACE
  kubectl get ing -n $NAMESPACE
  kubectl logs deployment/seidra-backend -n $NAMESPACE -f
EON
