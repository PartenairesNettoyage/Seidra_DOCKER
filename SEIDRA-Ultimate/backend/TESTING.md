# Vérification rapide du pipeline de génération (mode mock)

Ce guide décrit une procédure express pour confirmer que l'API `/api/generate`
fonctionne de bout en bout en environnement local sans GPU. La séquence utilise
la pipeline mock intégrée à `ModelManager`, ce qui permet de valider le cycle
"création ➜ traitement ➜ consultation" d'un job.

## Préparation

1. Installez les dépendances Python :
   ```bash
   cd backend
   pip install -r requirements.txt
   ```
2. Initialisez la base de données et les répertoires runtime :
   ```bash
   python -c "from core.config import settings, ensure_runtime_directories; ensure_runtime_directories(settings)"
   alembic -c alembic.ini upgrade head
   ```
3. Lancez l'API FastAPI (le mode mock est sélectionné automatiquement en
   l'absence de CUDA) :
   ```bash
   uvicorn main:app --reload
   ```

## Scénario de test

> ℹ️ Tous les endpoints `/api/generate` sont désormais protégés par un jeton JWT.
> Ajoutez l'en-tête `Authorization: Bearer <TOKEN>` dans chaque requête ci-dessous.

1. **Soumettre un job** via l'endpoint `POST /api/generate/single` :
   ```bash
   curl -X POST "http://localhost:8000/api/generate/single" \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer <TOKEN>" \
     -d '{
       "prompt": "mock dragon portrait",
       "negative_prompt": "blurry",
       "width": 512,
       "height": 512,
       "num_images": 1
     }'
   ```
   La réponse inclut `job_id` et `status="queued"`.

2. **Poller l'état** du job jusqu'à complétion :
   ```bash
   curl "http://localhost:8000/api/generate/status/<JOB_ID>" \
     -H "Authorization: Bearer <TOKEN>"
   ```
   Tant que la génération n'est pas terminée, `status` vaut `processing` ou
   `queued`.

3. **Valider le résultat final** : dès que le pipeline mock termine, la réponse
   de l'endpoint `/status` ressemble à ceci :
   ```json
   {
     "job_id": "a3d4...",
     "status": "completed",
     "progress": 1.0,
     "result_images": ["/absolute/path/to/media/mock_20241010-101500.png"],
     "error_message": null,
     "created_at": "2024-10-10T10:14:55.123456",
     "completed_at": "2024-10-10T10:14:58.654321"
   }
   ```

   Vérifiez explicitement que :
   - `status` vaut `"completed"` ;
   - `result_images` est une liste non vide de chemins d'images générées.

Ce test confirme que la valeur retournée par `GenerationService.process_job`
est bien exposée par l'API et que le pipeline mock enregistre les assets dans la
base de données.
