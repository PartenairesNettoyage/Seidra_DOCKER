# Procédure d'observabilité des générations

Cette procédure décrit la chaîne de collecte et de visualisation des métriques d'inférence SEIDRA Ultimate.

## Collecte côté backend

1. **ModelManager** mesure systématiquement chaque génération d'image et de vidéo :
   - durée d'inférence réelle (chronométrage haute résolution) ;
   - occupation VRAM (allocation instantanée, mémoire réservée, pic et delta) ;
   - débit de production (`outputs / durée`).
2. Les métriques calculées sont exposées au **GenerationService** qui les enrichit avec le contexte du job (job ID, utilisateur, persona, paramètres de requête).
3. Le **TelemetryService** persiste ensuite les données dans la table `generation_metrics` et envoie un évènement temps-réel sur le canal WebSocket `system`.

## Stockage & schéma

- Table Alembic : `generation_metrics` (voir migration `20241003_0002`).
- Colonnes clés :
  - `job_id`, `user_id`, `persona_id` pour rattacher la mesure ;
  - `media_type`, `model_name`, `prompt`, `outputs` ;
  - `duration_seconds`, `throughput`, `vram_*` ;
  - `extra` (JSON) pour les paramètres spécifiques (résolution, LoRA, scheduler, etc.).
- Rétention : la table est append-only et peut être purgée via un simple `DELETE` sur une fenêtre temporelle (`created_at`).

## API d'observabilité

- Endpoint FastAPI : `GET /api/system/telemetry/generation`
  - Paramètres : `limit` (par défaut 50), `minutes` (fenêtre temporelle), `media_type` (filtre image/vidéo).
  - Réponse :
    - `items` : liste détaillée des générations (triées par date décroissante) ;
    - `summary` : agrégats (total, moyenne de durée/débit, VRAM moyenne) ;
    - `recent` : tampon des derniers évènements pour le temps réel.
- Authentification : même jeton JWT que le reste des routes `/api/system`.

## Dashboards Grafana

- Fichier : `monitoring/grafana/ultimate-dashboard.json`.
- Nouveaux panels :
  - **Stat** « Temps moyen d'inférence (60 min) » via datasource Infinity `SEIDRA_API` -> `/api/system/telemetry/generation?minutes=60`.
  - **Table** « Dernières générations » listant horodatage, type, modèle, durée, débit et pic VRAM.
- Pré-requis : datasource Grafana de type *Infinity* (ou équivalent JSON) pointant vers l'API backend.
- Rafraîchissement conseillé : 30s pour le panel table, 1 min pour la stat.

## Exploitation & alerting

1. Configurer un alert rule Grafana sur la stat d'inférence avec un seuil (ex. > 15s pendant 5 min) pour détecter les régressions.
2. Pour les analyses ponctuelles, exécuter une requête SQL :
   ```sql
   SELECT model_name, avg(duration_seconds) AS avg_s, avg(vram_peak_mb) AS avg_vram
   FROM generation_metrics
   WHERE created_at >= datetime('now', '-1 day')
   GROUP BY model_name;
   ```
3. Les évènements temps réel sont disponibles sur le WebSocket `system` (type `telemetry.generation`).

## Maintenance

- Sur croissance importante de la table : prévoir un job de purge (`DELETE FROM generation_metrics WHERE created_at < datetime('now', '-30 day')`).
- Si la datasource Infinity change d'UID, mettre à jour le JSON Grafana en conséquence.
- Les migrations doivent être appliquées (`alembic upgrade head`) lors du déploiement pour créer la table.
