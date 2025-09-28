# Gestion de la rotation des secrets et outils support

Ce guide SRE décrit la procédure de rotation des secrets applicatifs et les actions de maintien en condition opérationnelle des outils de support (observabilité, stockage, comptes techniques). Il est aligné sur les scripts fournis dans le dépôt.

## 1. Vue d'ensemble des secrets

| Secret / Compte | Localisation | Fréquence de rotation | Script / Commande | Notes |
|-----------------|--------------|-----------------------|-------------------|-------|
| Mot de passe compte démo | Base SEIDRA (`User.id=1`) | 90 jours (configurable via `SEIDRA_DEFAULT_USER_ROTATION_DAYS`) | `make rotate-demo-user` | Génère un mot de passe robuste et met à jour le hash |
| `SECRET_KEY` (JWT) | Variable d'environnement backend | 180 jours ou incident de sécurité | Mise à jour manuelle + redéploiement backend | Nécessite l'invalidation des tokens actifs |
| Accès ComfyUI / SadTalker | Gestionnaire de secrets / `.env` | 90 jours ou changement d'équipe | Mise à jour `.env` + redémarrage backend | Contrôler la santé via `/health` |
| Accès MinIO (API + console) | `MINIO_ROOT_USER/MINIO_ROOT_PASSWORD` | 90 jours | Rotation manuelle via console + `scripts/sync-minio.sh --cleanup` | Synchroniser avec l'équipe stockage |
| Admin Grafana | `docker-compose.dev.yml` (`GF_SECURITY_ADMIN_*`) | 30 jours | Modifier le fichier + `./scripts/start-monitoring.sh` (recréation) | Conserver un accès d'urgence hors repo |

## 2. Procédure – rotation du compte démo

1. Planifier une fenêtre courte (5 minutes) pour prévenir les utilisateurs d'une déconnexion possible.
2. Sur l'hôte applicatif :
   ```bash
   make rotate-demo-user
   ```
3. Copier le mot de passe affiché dans le coffre-fort d'équipe et mettre à jour la variable `SEIDRA_DEFAULT_USER_PASSWORD` dans :
   - les fichiers `.env` (backend, workers) ;
   - les secrets Kubernetes (`kubectl edit secret seidra-backend-env`).
4. Redémarrer le backend (`docker compose restart backend` ou pipeline CD).
5. Vérifier la connexion avec le nouveau mot de passe et archiver le hash dans le ticket de change.

> Le script `scripts/rotate-default-user.py` accepte `--length` pour personnaliser la longueur et `--verbose` pour un audit détaillé (logs horodatés).

## 3. Rotation de `SECRET_KEY`

1. Générer une valeur aléatoire :
   ```bash
   openssl rand -base64 48
   ```
2. Mettre à jour `SECRET_KEY` dans le coffre-fort, puis dans les manifestes (`.env`, `values.yaml`, variables CI/CD).
3. Déployer la configuration et invalider manuellement les tokens (purge Redis si utilisée comme session store).
4. Informer les utilisateurs qu'une reconnexion est nécessaire.

## 4. Outils d'observabilité

- **Grafana** : modifier les variables `GF_SECURITY_ADMIN_USER`/`GF_SECURITY_ADMIN_PASSWORD` dans `docker-compose.dev.yml`, puis :
  ```bash
  ./scripts/stop-monitoring.sh
  ./scripts/start-monitoring.sh
  ```
  Vérifier la connexion et mettre à jour la documentation interne.
- **Prometheus / Loki / Tempo** : les mots de passe reposent sur les ACL locales. Si des identifiants sont exposés, relancer les conteneurs avec de nouveaux secrets via `docker compose`.
- **Dashboards** : archiver le JSON exporté (`monitoring/grafana/ultimate-dashboard.json`) avant toute modification majeure.

## 5. Stockage et artefacts

- Utiliser `scripts/sync-minio.sh --cleanup --days 30` pour purger les médias avant rotation des clés.
- Après rotation MinIO, regénérer les credentials dans les pipelines CI et mettre à jour les variables `SEIDRA_MINIO_*` côté backend.

## 6. Checklist post-rotation

- [ ] Secrets mis à jour dans Vault / gestionnaire central.
- [ ] Fichiers `.env` et manifestes synchronisés.
- [ ] Services redémarrés (`backend`, `workers`, `monitoring`).
- [ ] Vérification fonctionnelle (login, génération d'image, accès Grafana).
- [ ] Ticket de change complété avec horodatage et opérateur responsable.

