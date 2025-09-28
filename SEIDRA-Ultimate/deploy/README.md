# Déploiement SEIDRA Ultimate

Ce répertoire contient les manifestes Helm et les outils nécessaires pour déployer la plateforme sur un cluster Kubernetes de staging ou de production. Les images utilisées proviennent des releases officielles publiées sur le registre `ghcr.io/seidra`.

## Pré-requis

- Un cluster Kubernetes accessible (kubeconfig configuré) et un namespace dédié (`seidra-staging` conseillé).
- Helm 3.11+ installé localement.
- Accès en lecture au registre GitHub Container Registry (GHCR) et variables d'environnement `GHCR_TOKEN`/`GHCR_USERNAME` si l'espace est privé.
- Secrets Kubernetes déjà créés pour les mots de passe (PostgreSQL, Redis, MinIO, etc.).
- Base de données PostgreSQL provisionnée (gérée via `helm install postgresql` ou service managé) et migrations Alembic appliquées.

## Validation continue : job `helm-dry-run`

Le workflow GitHub Actions `Ultimate CI` embarque un job `helm-dry-run` qui valide automatiquement le chart Helm avant chaque push/PR :

1. Construction des images Docker backend et frontend avec `docker buildx` et tag GHCR `ghcr.io/<organisation>/ultimate-*-:${GITHUB_SHA}` (push désactivé, les images sont chargées localement pour Kind).
2. Création d'un cluster éphémère `kind` (`seidra-ci`) et import des deux images avec `kind load docker-image`.
3. Exécution de `helm dependency update`, `helm lint` puis `helm upgrade --install --dry-run --debug deploy/helm` afin de générer les manifests complets.
4. Vérification automatique que les ressources critiques (ConfigMap `seidra-config` et Secret `seidra-secrets`) sont présentes dans le rendu.
5. Publication des journaux (`backend-build.log`, `frontend-build.log`, `helm-dry-run.log`) dans l'artefact CI `helm-dry-run-logs` pour audit.

> ℹ️ Les paramètres Helm injectés dans le job positionnent `image.repository` sur `ghcr.io/<organisation>` et `image.tag` sur le SHA Git en cours, garantissant que les manifests référencent les images fraîchement construites.

### Dry-run manuel

Pour reproduire localement la vérification CI :

```bash
export SEIDRA_REGISTRY="ghcr.io/<organisation>/<repo>"
export SEIDRA_TAG="dryrun-$(date +%s)"

# Construire et charger les images dans Docker
docker buildx build . \
  --file backend/Dockerfile \
  --platform linux/amd64 \
  --tag "${SEIDRA_REGISTRY}/ultimate-backend:${SEIDRA_TAG}" \
  --load

docker buildx build frontend \
  --file frontend/Dockerfile \
  --platform linux/amd64 \
  --tag "${SEIDRA_REGISTRY}/ultimate-frontend:${SEIDRA_TAG}" \
  --load

# Créer un cluster Kind éphémère et lui injecter les images
kind create cluster --name seidra-ci --wait 120s
kind load docker-image --name seidra-ci "${SEIDRA_REGISTRY}/ultimate-backend:${SEIDRA_TAG}"
kind load docker-image --name seidra-ci "${SEIDRA_REGISTRY}/ultimate-frontend:${SEIDRA_TAG}"

# Vérifier le chart Helm en mode dry-run + debug
helm dependency update deploy/helm
helm lint deploy/helm
helm upgrade --install seidra-ultimate deploy/helm \
  --namespace seidra-dryrun \
  --create-namespace \
  --set image.repository="${SEIDRA_REGISTRY}" \
  --set image.tag="${SEIDRA_TAG}" \
  --dry-run --debug | tee deploy/helm/helm-dry-run.log

# Nettoyer le cluster de test
kind delete cluster --name seidra-ci
```

Le fichier `deploy/helm/helm-dry-run.log` permet ensuite de vérifier la présence des ressources attendues (`ConfigMap`, `Secret`, `Deployments`, etc.).

## Déploiement staging (bout-en-bout)

1. Authentifier Helm/Kubernetes sur le cluster de staging.
2. Exécuter le script [`scripts/deploy-staging.sh`](../scripts/deploy-staging.sh) afin de préparer les valeurs et lancer `helm upgrade --install` avec les images GHCR de la dernière release.
3. Vérifier les pods et l'exposition HTTP via `kubectl get pods -n seidra-staging` et `kubectl get ing -n seidra-staging`.
4. Déclencher la génération initiale d'assets via l'API (`/api/generation/health`) pour s'assurer que les workers Celery s'enregistrent correctement.

Exemple d'exécution manuelle sans script :

```bash
helm upgrade --install seidra-ultimate ./helm \
  --namespace seidra-staging --create-namespace \
  --set image.tag=v1.4.2 \
  --set backend.replicaCount=2 \
  --set worker.replicaCount=2 \
  --set env.SEIDRA_DATABASE_URL="postgresql+asyncpg://user:pass@postgres:5432/seidra"
```

## Gestion des versions & rollback

Le chart Helm `seidra-ultimate` suit la sémantique suivante :

- `Chart.yaml` → version du chart (ex : `0.1.0`) utilisée pour tracer les changements d'infra (templates, dépendances).
- `appVersion` → version applicative alignée sur la release GHCR (ex : `1.4.2`).
- L'image Docker par défaut est `ghcr.io/seidra/ultimate-backend:<tag>` et doit être synchronisée avec `appVersion`.

### Artefacts Python packagés

- Le `pyproject.toml` embarque désormais une détection automatique des modules `backend*` via `setuptools`. Un `pip wheel .` lancé à la racine du dépôt génère donc une roue `seidra_ultimate-<version>.whl` contenant l’intégralité du backend.
- Pour les pipelines CI/CD hors connexion, conserver ce wheel (et ceux des dépendances) dans un cache d’artefacts afin de garantir la reproductibilité des déploiements.

### Stratégie de rollback Helm

1. Lister les révisions : `helm history seidra-ultimate -n seidra-staging`.
2. Sélectionner la révision souhaitée (par exemple `3`) et exécuter : `helm rollback seidra-ultimate 3 -n seidra-staging`.
3. Vérifier que les nouveaux pods sont prêts puis purger l'ancienne release si nécessaire (`helm uninstall`).

> 💡 **Astuce** : conserver les charts packagés (`helm package deploy/helm`) dans un bucket ou un artifact store pour faciliter un rollback même si le dépôt Git n'est pas accessible.

### Migrations de base de données

Les migrations Alembic sont orchestrées via le job Kubernetes `ultimate-migrate` déclenché lors du déploiement.

- Pour appliquer une migration en avant : `kubectl logs job/ultimate-migrate -n seidra-staging` doit indiquer `Upgrade successful`.
- En cas de rollback applicatif, exécuter manuellement la migration inverse :

```bash
kubectl create job --from=cronjob/ultimate-migrations ultimate-migrate-rollback \
  -n seidra-staging --env="ALEMBIC_COMMAND=downgrade -1"
```

- Documenter le numéro de révision Alembic (`alembic_version` dans PostgreSQL) après chaque déploiement pour savoir jusqu'où revenir.

### Synchronisation chart ↔ migrations

- Toujours taguer le chart Helm avec un numéro de version incrémental à chaque modification de templates.
- Associer la révision Alembic cible (`backend/alembic/versions/<timestamp>_*.py`) à la release GHCR dans les notes de version.
- Les releases d'urgence doivent respecter la séquence : rollback Helm → rollback migrations (si nécessaire) → vérification de l'état (`/api/system/health`).

## Surveillances post-déploiement

- `kubectl get events -n seidra-staging --sort-by=.metadata.creationTimestamp`
- Tableaux de bord Grafana (`monitoring/grafana`) pour la consommation GPU, CPU et les files Celery.
- Alertes Prometheus sur les pods `backend`, `worker` et `frontend`.
- Pile d'observabilité autonome décrite ci-dessous.

### Stack Prometheus / Grafana / Loki

Une stack complète est fournie pour la supervision temps réel :

- **Docker Compose** : le fichier [`deploy/docker/monitoring.yml`](docker/monitoring.yml) installe Prometheus, Grafana, Loki et Promtail configurés avec les tableaux de bord du dépôt. Démarrer l'ensemble via :

  ```bash
  docker compose -f deploy/docker/monitoring.yml up -d
  ```

  Les volumes persistants (`prometheus-data`, `grafana-data`, `loki-data`) assurent la conservation des métriques et journaux. Les paramètres Grafana (`GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`) peuvent être surchargés via l'environnement.

- **Kubernetes** : le répertoire [`deploy/k8s/monitoring`](k8s/monitoring) fournit des valeurs Helm prêtes à l'emploi pour Prometheus, Grafana et Loki. Elles réutilisent la configuration de `monitoring/` (alerting, dashboards) via des ConfigMaps. Exemple d'installation :

  ```bash
  # Namespace dédié
  kubectl create namespace observability

  # Prometheus
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
  helm upgrade --install prometheus prometheus-community/prometheus \
    --namespace observability \
    -f deploy/k8s/monitoring/values-prometheus.yaml

  # Loki
  helm repo add grafana https://grafana.github.io/helm-charts
  helm upgrade --install loki grafana/loki-stack \
    --namespace observability \
    -f deploy/k8s/monitoring/values-loki.yaml

  # Grafana (dashboards & alerting pré-chargés)
  helm upgrade --install grafana grafana/grafana \
    --namespace observability \
    -f deploy/k8s/monitoring/values-grafana.yaml
  ```

Consultez `monitoring/README.md` pour l'inventaire des métriques, des alertes unifiées et des points d'accès.

## Références

- [Helm documentation](https://helm.sh/docs/)
- [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
