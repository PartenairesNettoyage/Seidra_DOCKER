#!/usr/bin/env bash
set -euo pipefail

ACTION=""
SOURCE=""
TARGET=""
CLEANUP_DAYS=0

function usage() {
    cat <<'USAGE'
Synchronisation des médias MinIO entre SEIDRA Classic et Ultimate.

Usage:
  sync-minio.sh --export --source http://classic:9000 --target http://backup:9000
  sync-minio.sh --import --source http://classic:9000 --target http://ultimate:9000
  sync-minio.sh --cleanup --target http://ultimate:9000 --days 30

Options:
  --source URL     Endpoint MinIO source
  --target URL     Endpoint MinIO cible
  --access KEY     Identifiant d'accès (sinon variables d'environnement)
  --secret KEY     Clé secrète (sinon variables d'environnement)
  --bucket NAME    Nom du bucket (par défaut seidra-media)
  --days N         Nombre de jours à conserver pour --cleanup
USAGE
}

BUCKET="seidra-media"
ACCESS_KEY="${SEIDRA_MINIO_ACCESS_KEY:-admin}"
SECRET_KEY="${SEIDRA_MINIO_SECRET_KEY:-password}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --export|--import|--cleanup)
            ACTION="$1"
            shift
            ;;
        --source)
            SOURCE="$2"
            shift 2
            ;;
        --target)
            TARGET="$2"
            shift 2
            ;;
        --bucket)
            BUCKET="$2"
            shift 2
            ;;
        --access)
            ACCESS_KEY="$2"
            shift 2
            ;;
        --secret)
            SECRET_KEY="$2"
            shift 2
            ;;
        --days)
            CLEANUP_DAYS="$2"
            shift 2
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

if [[ -z "$ACTION" ]]; then
    echo "Aucune action (--export, --import ou --cleanup)" >&2
    usage
    exit 1
fi

if ! command -v mc >/dev/null 2>&1; then
    echo "Le client MinIO 'mc' est requis pour ce script." >&2
    exit 1
fi

if [[ -z "$SOURCE" && "$ACTION" != "--cleanup" ]]; then
    echo "--source est requis pour $ACTION" >&2
    exit 1
fi

if [[ -z "$TARGET" ]]; then
    echo "--target est requis" >&2
    exit 1
fi

mc alias set classic "$SOURCE" "$ACCESS_KEY" "$SECRET_KEY" >/dev/null 2>&1 || true
mc alias set ultimate "$TARGET" "$ACCESS_KEY" "$SECRET_KEY" >/dev/null 2>&1 || true

case "$ACTION" in
    --export)
        mc mirror --overwrite classic/$BUCKET ./uploads/$BUCKET
        ;;
    --import)
        mc mirror --overwrite ./uploads/$BUCKET ultimate/$BUCKET
        ;;
    --cleanup)
        if [[ "$CLEANUP_DAYS" -le 0 ]]; then
            echo "--cleanup nécessite --days" >&2
            exit 1
        fi
        mc ilm rule add ultimate/$BUCKET --expire-days "$CLEANUP_DAYS" --id cleanup-ultimate >/dev/null
        echo "Politique de rétention configurée sur $CLEANUP_DAYS jours pour $BUCKET"
        ;;
esac
