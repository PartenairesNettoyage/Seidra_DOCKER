# Rapport de déploiement – Staging

## Résumé opérationnel

- **Pipeline images** : utilisation des artefacts `ghcr.io/seidra/ultimate-backend`, `ultimate-frontend` et `ultimate-worker` tagués `v1.4.2` (release GHCR).
- **Chart Helm** : `deploy/helm` version `0.1.0` déployée via `helm upgrade --install`.
- **Namespace** : `seidra-staging` (créé automatiquement si absent).
- **Secrets** : `seidra-ghcr` (image pull), `seidra-db` (connexion PostgreSQL), `seidra-minio`, `seidra-redis`.
- **Vérifications post-déploiement** : status des déploiements (`seidra-backend`, `seidra-frontend`, `seidra-worker`), exécution des migrations Alembic (`ultimate-migrate`), test d'API `/api/health` et `/api/generation/health`.

## Matrice de compatibilité OS / GPU

| OS / Distribution | GPU & Drivers | Status | Notes |
|-------------------|--------------|--------|-------|
| Ubuntu 22.04 LTS (kOps) | NVIDIA A10G / Driver 535, CUDA 12.2 | ✅ Supporté | Workloads Celery + backend compatibles, tests charge réalisés avec Helm chart 0.1.0.
| Ubuntu 20.04 LTS (AKS) | NVIDIA T4 / Driver 525, CUDA 12.1 | ✅ Supporté | Ajuster `nvidia.com/gpu: 1` dans les values workers pour la production.
| Debian 12 (Kubeadm) | NVIDIA L40S / Driver 550, CUDA 12.4 | ⚠️ Recommandé | Nécessite `RuntimeClass` `nvidia` et tuning `NO_PROXY` pour MinIO.
| Rocky Linux 9 (RKE2) | AMD MI210 / ROCm 6.1 | ⚠️ Expérimental | Pipeline vidéo indisponible, fallback CPU activé, surveiller la VRAM via Prometheus.
| Windows Server 2022 (AKS) | NVIDIA RTX 6000 Ada / Driver 552, CUDA 12.4 | ❌ Non supporté | Pas de support officiel Kubernetes Windows pour Celery workers GPU.

## Actions de suivi

1. Industrialiser la collecte des métriques GPU (Exporter DaemonSet à déployer).
2. Ajouter des tests de non-régression contractuelle (OpenAPI ↔ clients) avant promotion en production.
3. Documenter la procédure DRP (sauvegarde base + MinIO) et la restauration contrôlée.
