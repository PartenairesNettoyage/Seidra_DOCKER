# Dry-run Helm & Build GHCR

Ce guide décrit comment exécuter un dry-run complet de la livraison SEIDRA Ultimate : construction des images destinées à GHCR sans publication effective, puis rendu du chart Helm `deploy/helm` pour valider le manifeste avant déploiement.

## 1. Préparer l’environnement Docker Buildx

1. Créez un builder isolé et sélectionnez-le par défaut :
   ```bash
   docker buildx create --name seidra-dryrun --use
   ```
2. Définissez les variables utilisées pour taguer les images (remplacez `ORG/REPO` et `TAG`) :
   ```bash
   export SEIDRA_REGISTRY="ghcr.io/ORG/REPO"
   export SEIDRA_TAG="vX.Y.Z-dryrun"
   ```

## 2. Simuler la publication GHCR

Les commandes suivantes construisent les images backend et frontend avec les mêmes Dockerfile que le workflow `Ultimate Release`, mais désactivent le push grâce à l’output explicite `push=false`.

```bash
# Backend
docker buildx build backend \
  --file backend/Dockerfile \
  --tag "${SEIDRA_REGISTRY}/ultimate-backend:${SEIDRA_TAG}" \
  --tag "${SEIDRA_REGISTRY}/ultimate-backend:latest" \
  --output=type=image,name="${SEIDRA_REGISTRY}/ultimate-backend:${SEIDRA_TAG}",push=false

# Frontend
docker buildx build frontend \
  --file frontend/Dockerfile \
  --tag "${SEIDRA_REGISTRY}/ultimate-frontend:${SEIDRA_TAG}" \
  --tag "${SEIDRA_REGISTRY}/ultimate-frontend:latest" \
  --output=type=image,name="${SEIDRA_REGISTRY}/ultimate-frontend:${SEIDRA_TAG}",push=false
```

- Utilisez `--progress=plain` pour analyser les couches construites.
- Ajoutez `--load` si vous souhaitez charger l’image finale dans le daemon Docker local.
- Supprimez le builder une fois le test terminé : `docker buildx rm seidra-dryrun`.

## 3. Dry-run Helm sur le chart `deploy/helm`

1. Positionnez-vous à la racine du dépôt.
2. Mettez à jour les dépendances (si des charts parents sont déclarés) :
   ```bash
   helm dependency update deploy/helm
   ```
3. Vérifiez la cohérence du chart :
   ```bash
   helm lint deploy/helm \
     --values deploy/helm/values.yaml
   ```
4. Générez le manifeste rendu sans l’appliquer à un cluster :
   ```bash
   helm template seidra-ultimate deploy/helm \
     --namespace seidra-dryrun \
     --values deploy/helm/values.yaml \
     --set image.repository="${SEIDRA_REGISTRY}" \
     --set image.tag="${SEIDRA_TAG}" \
     > ./deploy/helm/rendered-manifest.yaml
   ```
5. Examinez le fichier `deploy/helm/rendered-manifest.yaml` pour confirmer la création des ressources (`Deployments`, `Jobs` Alembic, `Services`, `Ingress`) attendues par le chart.

## 4. Vérifications optionnelles

- Validez les manifests générés avec `kubeconform` ou `kubectl apply --dry-run=client` si un cluster de test est disponible.
- Conservez les artefacts (`rendered-manifest.yaml`, logs `buildx`) en tant que preuves du dry-run dans vos pipelines CI/CD.

En suivant ces étapes, vous obtenez la même couverture qu’un pipeline de release GHCR + Helm, sans modifier les registres ni les clusters existants.
