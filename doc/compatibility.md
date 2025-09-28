# Matrice de compatibilité GPU / Bare metal

Cette matrice synthétise les plateformes validées pour SEIDRA Ultimate et indique la couverture assurée par les workflows CI/CD GitHub Actions.

## Vue d’ensemble

| Plateforme | GPU / Accélération | Statut terrain | Notes opérationnelles | Couverture CI/CD |
|------------|--------------------|----------------|-----------------------|------------------|
| Bare metal (Ubuntu 22.04) | NVIDIA RTX 3090 / CUDA 12.1 | ✅ Requis | Configuration officielle pour l’installation 1‑clic et les pipelines SDXL optimisés RTX 3090.【F:workspace/SEIDRA-Ultimate/GETTING_STARTED.md†L3-L87】【F:workspace/SEIDRA-Ultimate/backend/services/model_manager.py†L1-L40】 | Tests contractuels et QA exécutés sur `ubuntu-latest` via le workflow Ultimate CI (`make check`, Pytest, Vitest).【F:.github/workflows/ultimate-ci.yml†L17-L59】【F:scripts/ci-report.sh†L13-L23】 |
| Kubernetes (kOps) | NVIDIA A10G / Driver 535 | ✅ Supporté | Déploiement validé avec le chart Helm `deploy/k8s/ultimate` (Celery GPU + backend).【F:reports/deployment.md†L5-L18】【F:deploy/k8s/ultimate/templates/backend-deployment.yaml†L1-L80】 | Images GHCR reconstruites par Ultimate Release pour rollback rapide.【F:.github/workflows/ultimate-release.yml†L24-L55】 |
| Kubernetes (AKS) | NVIDIA T4 / Driver 525 | ✅ Supporté | Ajuster `nvidia.com/gpu: 1` pour les workers ; testé lors des dry-runs Helm.【F:reports/deployment.md†L5-L19】【F:deploy/helm/README.md†L1-L55】 | Publication GHCR automatisée par Ultimate Release ; contrat API contrôlé par Ultimate CI.【F:.github/workflows/ultimate-release.yml†L24-L55】【F:.github/workflows/ultimate-ci.yml†L17-L59】 |
| Kubernetes (kubeadm) | NVIDIA L40S / Driver 550 | ⚠️ Recommandé | Requiert RuntimeClass NVIDIA et tuning réseau pour MinIO.【F:reports/deployment.md†L5-L20】 | Validé par rendu Helm (`helm template`) et comparaisons OpenAPI dans CI.【F:deploy/helm/README.md†L20-L55】【F:Makefile†L47-L59】 |
| RKE2 | AMD MI210 / ROCm 6.1 | ⚠️ Expérimental | Pipeline vidéo indisponible, fallback CPU activé à surveiller.【F:reports/deployment.md†L5-L21】【F:workspace/SEIDRA-Ultimate/backend/services/gpu_monitor.py†L360-L370】 | Couverture fonctionnelle par Ultimate CI (exécution sans GPU) qui valide les fallbacks CPU des services IA.【F:.github/workflows/ultimate-ci.yml†L17-L59】【F:scripts/ci-report.sh†L13-L23】 |
| AKS Windows Server 2022 | NVIDIA RTX 6000 Ada / Driver 552 | ❌ Non supporté | Kubernetes Windows ne supporte pas les workers Celery GPU ; usage déconseillé.【F:reports/deployment.md†L5-L22】 | Non exécuté dans la CI ; nécessite validation manuelle avant tout essai. |

## Rattachement aux workflows CI/CD

- **Ultimate CI** (`.github/workflows/ultimate-ci.yml`) tourne sur Ubuntu sans GPU et lance `scripts/ci-report.sh` → `make check`. Cela inclut le script `check-backward-compat.py` et les tests `tests/contract`, garantissant qu’un rollback ou une nouvelle plateforme respecte le contrat API Classic/Ultimate.【F:.github/workflows/ultimate-ci.yml†L17-L59】【F:scripts/ci-report.sh†L13-L23】【F:Makefile†L47-L59】【F:tests/contract/test_openapi_backward_compat.py†L1-L66】
- **Ultimate Release** (`.github/workflows/ultimate-release.yml`) reconstruit et pousse les images backend/frontend sur GHCR. Les tags produits servent de point de restauration pour les clusters GPU ci-dessus et alimentent les dry-runs décrits dans `deploy/helm/README.md`.【F:.github/workflows/ultimate-release.yml†L24-L55】【F:deploy/helm/README.md†L1-L55】
- **Dry-run Helm & Build GHCR** (`deploy/helm/README.md`) fournit la procédure de validation locale (buildx + `helm template`) utilisée avant chaque publication ou rollback d’infrastructure, garantissant que la matrice reste cohérente avec les artefacts générés par la CI.【F:deploy/helm/README.md†L1-L55】

Cette articulation permet d’identifier rapidement les plateformes supportées et les pipelines CI/CD associés pour sécuriser la promotion ou le retour arrière d’une version.
