# Runbook d'incident - SEIDRA Ultimate

## Stack d'observabilité

- **Démarrage / arrêt** :
  - `./scripts/start-monitoring.sh` pour lancer Prometheus, Grafana, Loki, Tempo et Promtail.
  - `./scripts/stop-monitoring.sh` pour arrêter proprement la stack (volumes conservés).
- **Points d'accès** : Prometheus `http://localhost:9090`, Grafana `http://localhost:3001` (admin/admin), Loki `http://localhost:3100`, Tempo `http://localhost:3200` (OTLP gRPC 4317 / HTTP 4318).
- **Alerting** : règles unifiées Grafana (CPU > 90 %, température GPU ≥ 85 °C, latence p95 > 30 s) visibles dans `Alerting > Alerts`.
- **Dashboard clé** : `SEIDRA Ultimate - Observabilité` (onglets GPU, Jobs, Notifications) pré-provisionné dans Grafana.

## Symptôme : API indisponible
1. Vérifier l'alerte `BackendDown` dans le panneau « Alertes actives » du dashboard Grafana.
2. Lancer `docker compose ps backend` ou `kubectl get pods -l app=seidra-backend` selon l'environnement.
3. Ouvrir les logs Loki : requête `{compose_service="backend"}` via Grafana ou `docker compose logs backend --tail 200`.
4. Relancer le déploiement (`docker compose restart backend` ou `kubectl rollout restart deployment/seidra-backend`).

## Symptôme : Latence élevée sur les jobs IA
1. Sur Grafana, onglet « Jobs » : vérifier "Jobs Celery actifs" et "Durée p95 des jobs".
2. Corréler avec Flower (`http://localhost:5555`) pour identifier les workers saturés.
3. Regarder la température GPU dans l'onglet « GPU » (panel "Température GPU (°C)").
4. Ajuster l'infrastructure (ajout d'un worker : `kubectl scale deployment seidra-worker --replicas=3`).

## Symptôme : Débordement du stockage MinIO
1. Sur Grafana, vérifier les alertes liées au stockage (panel « Alertes actives »).
2. Consulter les logs Loki `{compose_service="minio"}` pour détecter les erreurs `disk quota`.
3. Lancer `scripts/sync-minio.sh --cleanup --days 30` pour archiver les médias anciens.
4. Adapter la politique de lifecycle dans MinIO si besoin.

## Symptôme : Absence de traces Tempo
1. Confirmer que les services instrumentés envoient bien du trafic OTLP (ports 4317/4318 ouverts).
2. Vérifier `docker compose logs tempo` pour détecter une erreur de configuration.
3. Contrôler le panneau "Requêtes récentes" dans Grafana ; en cas de vide, lancer un job pour générer du trafic.

## Escalade
- Contacter l'équipe SRE via Slack `#seidra-ultimate`.
- Fournir : horodatage, impact utilisateur, actions entreprises, captures Grafana, identifiant de trace Tempo si disponible.
