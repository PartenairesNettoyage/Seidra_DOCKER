# Guide de migration vers SEIDRA Ultimate

Ce document décrit la procédure recommandée pour faire évoluer une instance SEIDRA "classique" vers **SEIDRA Ultimate** tout en garantissant la continuité de service.

## 1. Préparation
- Sauvegarder la base de données (`pg_dump` ou export SQLite).
- Exporter les médias présents dans MinIO via `scripts/sync-minio.sh --export`.
- Vérifier la version de schéma courante grâce au script `alembic current`.

## 2. Mise à niveau des services
1. Cloner le dépôt Ultimate et exécuter `./install-dev.sh --with-ml` sur un environnement de staging.
2. Lancer l'infrastructure de recette avec `docker compose -f docker-compose.dev.yml up -d`.
3. Exécuter `scripts/migrate-from-classic.py --database postgresql://...` pour appliquer les migrations additionnelles (personas enrichis, paramètres NSFW étendus, historique des jobs).
4. Synchroniser les médias existants :
   ```bash
   scripts/sync-minio.sh --import --source http://classic-minio:9000 --target http://ultimate-minio:9000
   ```

## 3. Validation QA
- `./scripts/ci-report.sh` pour lancer la batterie complète (`make check` + couvertures) et peupler `reports/qa/`.
- Vérifier que la couverture backend reste ≥ 85 % (rapport `reports/qa/backend/html/index.html`).
- Vérifier que la couverture frontend reste ≥ 80 % (rapport `reports/qa/frontend/coverage/index.html`).
- `npm run test --prefix frontend -- --headed --reporter=html` pour générer les traces Playwright optionnelles.

## 4. Bascule production
1. Préparer les secrets (GitHub Environments ou Vault) : clés JWT, MinIO, Redis, ComfyUI.
2. Déployer les workflows GitHub `ultimate-ci.yml` et `ultimate-release.yml` pour automatiser la livraison.
3. Lancer `./install-prod.sh` sur l'environnement cible puis vérifier la santé via `curl http://localhost:8000/api/health`.
4. Mettre à jour le DNS/Load Balancer pour pointer vers la nouvelle pile. Une fois la supervision Grafana/Prometheus validée, libérer l'ancienne infrastructure.
5. Programmer immédiatement la rotation du compte démo via `make rotate-demo-user` puis propager le nouveau secret dans votre coffre-fort (`SEIDRA_DEFAULT_USER_PASSWORD`).

## 5. Checklist finale
- [ ] Tests unitaires backend & frontend au vert.
- [ ] Tests Playwright E2E (onboarding, génération d'avatar, téléchargement média).
- [ ] Dashboards Grafana synchronisés (`monitoring/grafana/ultimate.json`).
- [ ] Alertes Prometheus actives (`monitoring/prometheus/alerts.yml`).
- [ ] Runbook d'incident revu avec l'équipe support.
- [ ] Rotation du compte démo effectuée et nouveau secret distribué (`make rotate-demo-user`).

> 💡 Conservez ce guide avec le rapport de migration signé par l'équipe QA pour tracer la mise en production Ultimate.
