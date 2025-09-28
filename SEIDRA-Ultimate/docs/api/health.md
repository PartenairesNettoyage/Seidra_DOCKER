# Ressource Santé (`GET /api/health`)

Cette ressource fournit un instantané de l'état de SEIDRA Ultimate : disponibilité, GPU, modèles chargés et connexions actives.

## Exemple de requête

```bash
curl -X GET http://localhost:8000/api/health
```

## Exemple de réponse `200 OK`

```json
{
  "status": "healthy",
  "gpu": {
    "gpu_available": true,
    "gpu_name": "NVIDIA RTX 3090",
    "driver_version": "551.76",
    "cuda_version": "12.1",
    "temperature": 66,
    "utilization": 41.5,
    "memory_used": 8123,
    "memory_free": 16441,
    "memory_total": 24564,
    "memory_max_allocated": 9123,
    "inference_avg_seconds": 4.2,
    "inference_samples": 18,
    "cuda_error_count": 0,
    "cuda_errors": [],
    "power_draw": 285,
    "fan_speed": 58,
    "last_update": "2025-09-27T12:18:00.000Z"
  },
  "models_loaded": 3,
  "active_connections": 2
}
```

## Cas d'erreur possibles

| Code | Description | Exemple de charge utile |
| ---- | ----------- | ----------------------- |
| 401  | Jeton d'authentification manquant ou invalide (si la sécurité est activée). | `{ "detail": "Non authentifié." }` |
| 503  | Le service de télémétrie n'est pas initialisé ou indisponible. | `{ "detail": "Télémétrie indisponible pour le moment." }` |
| 500  | Une exception interne a été levée lors de la collecte des métriques. | `{ "detail": "Erreur interne, consultez les logs backend." }` |

> 💡 En environnement de production, surveillez particulièrement `gpu.temperature` et `active_connections` pour détecter les anomalies précocement.
