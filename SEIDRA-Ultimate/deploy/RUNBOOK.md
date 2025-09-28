# SEIDRA Ultimate – Runbook d'exploitation

Ce document décrit les opérations courantes et les procédures de gestion des incidents pour l'infrastructure de génération (temps réel et batch) après l'introduction des files de priorité et du mode dégradé GPU.

## 1. Files de tâches Celery

| File | Usage | Priorité par défaut |
| --- | --- | --- |
| `generation.realtime` | Jobs interactifs (API `/generation/single`, relances utilisateur) | 0–4 selon la requête |
| `generation.batch` | Lots programmés (API `/generation/batch`, maintenance) | 8 |

> ⚙️ **File interne `asyncio`** : le `GenerationService` maintient également deux files locales (`realtime` et `batch`) avec priorité explicite. Les jobs "temps réel" reprennent automatiquement la main lorsqu'ils arrivent, même si des lots sont déjà programmés.

Les workers sont lancés avec `celery -A workers.celery_app worker -Q generation.realtime,generation.batch,...`. Les jobs peuvent être redirigés manuellement avec:

```bash
celery -A workers.celery_app control cancel_consumer generation.batch
celery -A workers.celery_app control add_consumer generation.realtime -d <worker-name>
```

## 2. Supervision GPU et mode dégradé

- Les timeouts d'inférence (`GPU inference timeout`) ou un statut `ModelManager` indiquant `mode`∈{`degraded`, `maintenance`, `offline`} ou `health`∈{`degraded`, `unhealthy`} déclenchent un report automatique des jobs.
- Les jobs replanifiés repassent en statut `pending` avec métadonnée `metadata.degraded.retry_after_seconds`.
- Une notification utilisateur de niveau `warning` est envoyée, et un log `Delaying job ... due to GPU unavailability` est produit.

### Vérification rapide

```sql
SELECT id, status, metadata->'degraded' AS degraded_info
FROM generation_jobs
WHERE status = 'pending' AND metadata->'degraded' IS NOT NULL
ORDER BY updated_at DESC
LIMIT 10;
```

## 3. Procédures de reprise

1. **Identifier l'incident** : consulter les journaux (`backend/services/generation_service.py`) et `celery -A workers.celery_app inspect active`.
2. **Forcer le mode mock** (en dernier recours) : définir `SEIDRA_FORCE_MOCK=1` et redémarrer les workers pour basculer sur CPU.
3. **Relancer les jobs différés** :
   - via API `POST /jobs/{job_id}/retry` (priorité temps réel),
   - ou manuellement `python -m workers.generation_worker submit_generation_job <job_id>` (optionnellement avec `--countdown`).
4. **Retour à la normale** : surveiller que `ModelManager.get_status_snapshot()` retourne `health=healthy` et `mode=cuda`. Les jobs en attente se videront automatiquement.

## 4. Tests de diagnostic

Dans l'environnement applicatif :

```bash
pytest backend/tests/test_generation_fallback.py
```

- `test_gpu_timeout_triggers_degraded_mode` : détection d'indisponibilité et notifications.
- `test_priority_queue_requeues_after_gpu_unavailability` : re-planification après panne GPU.
- `test_realtime_jobs_take_precedence_over_batch_queue` : priorité stricte des jobs interactifs dans la file interne.

## 5. Notes d'exploitation

- Conserver au moins un worker abonné à `generation.realtime` pour les notifications utilisateurs.
- Les jobs batch volumineux doivent être envoyés avec `priority: "low"` afin d'éviter de saturer la file temps réel.
- Les notifications envoyées pendant un mode dégradé sont journalisées dans `notifications` (via `NotificationService`).
- Les métadonnées `metadata.degraded.history` sur les jobs fournissent l'historique des reports.
