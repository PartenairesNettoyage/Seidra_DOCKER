# Observabilité SEIDRA Ultimate

Ce répertoire centralise la stack Prometheus / Grafana / Loki / Tempo utilisée pour superviser la plateforme en développement, staging et production. Les fichiers sont pensés pour être consommés aussi bien par `docker compose` que par les manifests Helm fournis dans `deploy/`.

## Structure

- `prometheus/` : configuration de scrape (`prometheus.yml`) + règles d'alerting.
- `grafana/` : provisioning des datasources, tableaux de bord (`ultimate-dashboard.json`) et alerting unifié (`provisioning/alerting`).
- `loki/`, `promtail/`, `tempo/` : configuration logging/tracing prête à l'emploi.
- `runbook.md` : procédures d'investigation et gestes opérationnels.

## Lancer la stack en local

```bash
make observability-up            # démarre Prometheus, Grafana, Loki, Tempo
make observability-down          # stoppe et nettoie les conteneurs
```

Les cibles Make s'appuient sur `docker-compose.dev.yml`. Pour un démarrage ciblé sans Make :

```bash
docker compose -f deploy/docker/monitoring.yml up -d
```

Points d'accès par défaut :

| Service    | URL locale | Service Kubernetes |
|------------|------------|--------------------|
| Prometheus | http://localhost:9090 | `prometheus-server` (port 80) |
| Grafana    | http://localhost:3001 | `grafana` (port 80) |
| Loki       | http://localhost:3100 | `loki` (port 3100) |
| Tempo      | http://localhost:3200 | `tempo` (port 3200) |

Identifiants Grafana par défaut : `admin` / `admin` (à personnaliser via variables d'environnement ou `values-grafana.yaml`).

## Alertes unifiées

Les seuils critiques sont définis dans [`grafana/provisioning/alerting/rules.yml`](grafana/provisioning/alerting/rules.yml) et s'alignent sur `settings.notification_thresholds` :

- **CPU saturé** (`> 90 %` sur 5 minutes) : surveille les workloads `backend`/`worker`.
- **Température GPU critique** (`≥ 85 °C`) : déclenche une alerte `error`.
- **Latence de génération** (`p95 > 30 s` sur les tâches Celery) : détecte les dérives sur la génération IA.

Les alertes sont visibles dans Grafana (`Alerting > Alerts`) et se synchronisent avec Prometheus grâce aux mêmes expressions.

## Validation automatique

La cible `make monitoring-validate` s'appuie sur `scripts/monitoring/check_dashboards.py` pour vérifier que :

- chaque dashboard Grafana référencé dans [`monitoring/grafana`](grafana) possède des datasources valides ;
- les endpoints HTTP de Prometheus et Grafana répondent quand la stack est levée.

```bash
make monitoring-validate
```

La commande démarre temporairement Prometheus/Grafana via `docker compose`, exécute les vérifications puis supprime les conteneurs.

### Résultats attendus

- Chaque fichier `*.json` doit afficher `✅ ... -> datasources détectées: ...`.
- Les messages finaux doivent indiquer `Endpoint Prometheus joignable` et `Endpoint Grafana joignable`.

### Dépannage

| Problème détecté | Actions recommandées |
|------------------|----------------------|
| `datasource inconnue` | Vérifier que l'UID ou le nom référencé dans le dashboard correspond à `grafana/provisioning/datasources/datasources.yml`. |
| `datasource manquante` ou `aucune datasource référencée` | Compléter le panel/target concerné dans Grafana et réexporter le JSON avec la datasource appropriée. |
| `Endpoint ... injoignable` | Lancer manuellement `docker compose -f deploy/docker/monitoring.yml up -d` et contrôler les ports 9090/3001. Consulter `docker compose logs <service>`. |
| `Endpoint ... ignoré` | La stack n'était pas démarrée pendant la vérification : relancer après avoir démarré Prometheus/Grafana. |

## Déploiement Kubernetes

Consultez [`deploy/k8s/monitoring`](../deploy/k8s/monitoring) pour les valeurs Helm, la génération des ConfigMaps et les commandes d'installation qui reprennent ces mêmes dashboards/alertes.

## Exploitation quotidienne

- Surveiller le tableau de bord « SEIDRA Ultimate - Observabilité » pour CPU, GPU et files Celery.
- Utiliser l'explorateur Loki (`Explore > Logs`) pour corréler les erreurs applicatives.
- Suivre `Tempo` pour les traces distribuées (FastAPI ↔ workers) lorsque l'option est activée dans le backend.
- Se référer au runbook (`monitoring/runbook.md`) et au guide opérationnel (`doc/guide_exploitation_observabilite.md`) pour les scénarios d'incident.
