# Initialisation de la base de données SEIDRA Ultimate

Ce guide décrit la procédure officielle pour préparer les fondations backend et appliquer les migrations de base de données.

## Prérequis
- Python 3.11+
- Dépendances installées : `pip install -r requirements.txt`
- Variables d’environnement optionnelles : `SEIDRA_DATABASE_URL` (par défaut `sqlite:///../data/seidra.db`)

## Étapes
1. **Créer les dossiers runtime** (médias, miniatures, modèles, tmp) :
   ```bash
   python -c "from core.config import settings, ensure_runtime_directories; ensure_runtime_directories(settings)"
   ```
2. **Appliquer les migrations Alembic** :
   ```bash
   alembic -c alembic.ini upgrade head
   ```
   Le fichier `alembic.ini` pointe automatiquement vers `SEIDRA_DATABASE_URL`.
3. **Seeder les données de référence** (utilisateur système + réglages NSFW par défaut) :
   ```bash
   python -c "from services.database import seed_default_user, seed_default_nsfw_settings; seed_default_user(); seed_default_nsfw_settings()"
   ```

## Exécution automatisée au démarrage
La fonction `init_database()` utilisée par l’application FastAPI exécute les étapes ci-dessus de manière idempotente :
- création du dossier `../data` si nécessaire ;
- `alembic upgrade head` pour garantir le dernier schéma ;
- seed des utilisateurs et réglages uniquement lorsqu’ils sont absents.

## Vérification
Pour confirmer l’état de la base :
```bash
python - <<'PY'
from services.database import DatabaseService
with DatabaseService() as db:
    print(db.get_platform_summary())
PY
```

Le résultat doit afficher les compteurs d’entités (`users`, `personas`, `jobs`, `media`).

## Nouvelles capacités de l’API Personas

Les routes `/api/personas` exposent désormais des paramètres de filtrage et de pagination alignés avec le frontend **Ultimate** :

- Toutes ces routes nécessitent désormais un en-tête `Authorization: Bearer <TOKEN>` afin d'appliquer correctement le contexte utilisateur authentifié.

- `limit` (1-100) et `offset` pour paginer les résultats ;
- `search` pour filtrer sur le nom, la description, le style ou les tags ;
- `is_favorite` pour ne retourner que les favoris ;
- `include_nsfw` pour inclure les personas NSFW (exclus par défaut).

Chaque élément du payload inclut également les champs `tags`, `is_favorite`, `is_nsfw` et `avatar_url`, ce qui permet au frontend de refléter les métadonnées avancées.

### Prévisualisation de style

L’endpoint `POST /api/personas/{persona_id}/preview` crée un job de génération mocké qui simule le cycle de vie complet (`queued → processing → completed`). Le job est stocké dans la table `generation_jobs` avec `job_type="persona_preview"`, ce qui permet au frontend de suivre l’état et de récupérer un aperçu immédiatement.
