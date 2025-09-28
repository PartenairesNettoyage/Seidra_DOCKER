# Audit de cohérence du backend SEIDRA Ultimate

## Méthodologie

* Installation des dépendances déclarées dans `pyproject.toml` via `pip install -e .`.
* Exécution de la batterie de tests `pytest` afin de détecter les incohérences fonctionnelles et les manques de dépendances.
* Analyse ciblée des traces d'erreur pour proposer des actions correctives concrètes.

## Résultats de l'exécution des tests

La commande `pytest` aboutit actuellement à **14 échecs et 17 erreurs** après installation des dépendances principales. Les catégories de problèmes identifiées sont détaillées ci-dessous, avec pour chacune les actions correctrices proposées.

## Problèmes et recommandations

### 1. Dépendances manquantes pour la gestion de formulaires
* **Symptôme :** plusieurs tests API (`test_video_timeline.py`, `test_media_api.py`, `test_generation_video.py`, `test_jobs_api.py`) échouent avec `RuntimeError: Form data requires "python-multipart" to be installed.`
* **Analyse :** la dépendance `python-multipart` est utilisée par FastAPI pour parser les formulaires, mais elle n'était déclarée que dans `backend/requirements.txt`.
* **Correctif recommandé :** ajouter `python-multipart>=0.0.6` aux dépendances de base (`pyproject.toml`) afin d'assurer son installation dans tous les environnements.

### 2. Compatibilité limitée avec les stubs de tests Pydantic
* **Symptôme :** les tests de résilience du `ModelManager` échouent lorsque les suites de tests injectent un stub minimal de Pydantic qui ne fournit pas `BaseSettings`.
* **Analyse :** `backend/core/config.py` importait `BaseSettings` directement depuis `pydantic`, ce qui échouait lorsque seul le stub minimal était disponible.
* **Correctif recommandé :** renforcer la logique d'import pour accepter à la fois Pydantic, `pydantic-settings`, ou un stub minimal. Le module doit fournir un fallback explicite lorsque `BaseSettings` est absent.

### 3. Initialisation incomplète de la base de données dans les tests
* **Symptôme :** plusieurs tests (`test_personas_api.py`, `test_notification_persistence.py`, etc.) échouent avec `sqlite3.OperationalError: no such table`.
* **Analyse :** les tests utilisent des bases en mémoire et s'attendent à ce que les tables soient créées automatiquement. L'appel à `ensure_schema()` ou aux migrations Alembic n'est pas déclenché dans les fixtures.
* **Correctifs recommandés :**
  - Garantir que `services.database.ensure_schema()` soit invoqué lors de l'initialisation des services concernés (API, services de notifications, etc.).
  - Offrir un hook de configuration de tests permettant de forcer la création du schéma lorsque l'on utilise un `SessionLocal` de substitution.

### 4. Gestion des utilisateurs par défaut et hachage des mots de passe
* **Symptôme :** les tests de sécurité de la base (`test_database_security.py`) échouent car `services.database` n'expose pas `_hash_password` lorsque des stubs partiels sont injectés.
* **Analyse :** le module importe `get_password_hash` depuis `api.auth`. Lorsque les tests injectent un module minimal, la fonction n'est pas présente et `_hash_password` n'est pas défini.
* **Correctifs recommandés :**
  - Fournir un fallback explicite pour `_hash_password` lorsque `api.auth.get_password_hash` n'est pas disponible (ex. lever une erreur claire ou injecter une implémentation de secours).
  - Documenter l'API attendue pour les stubs afin d'éviter des AttributeError silencieux.

### 5. Initialisation de `DatabaseService` dans les tests asynchrones
* **Symptôme :** dans `test_generation_fallback.py`, des `AttributeError` indiquent que le `DatabaseService` utilisé est un placeholder dépourvu de méthodes (`create_job`, `_jobs`).
* **Analyse :** les tests substituent le module `services.database` par un stub minimal pour isoler le service. Notre code doit détecter ce contexte et refuser de fonctionner avec le placeholder, ou bien exposer une API de stub compatible.
* **Correctifs recommandés :**
  - Ajouter des vérifications dans `GenerationService` pour s'assurer que le `DatabaseService` injecté implémente bien les méthodes critiques, avec un message d'erreur explicite.
  - Offrir un stub de base cohérent dans `services.database` pour les scénarios hors production (ex. classe interne utilisée dans les tests).

### 6. Collisions d'utilisateurs lors des tests Celery
* **Symptôme :** `test_celery_remote_integration.py::test_celery_remote_video_generation` échoue avec `IntegrityError` sur `users.username`.
* **Analyse :** les tests insèrent plusieurs fois l'utilisateur démo sans réinitialiser l'état entre les scénarios.
* **Correctifs recommandés :**
  - Réinitialiser la base via une fixture dédiée ou isoler chaque test dans une transaction rollback.
  - Adapter `seed_default_user()` pour effectuer un `upsert` atomique garantissant l'idempotence dans les contextes de tests.

### 7. Support partiel des API FastAPI lors de l'exécution hors ligne
* **Symptôme :** le test `test_schedule_local_job.py` échoue lorsque FastAPI est remplacé par un stub minimal dépourvu de `Form`.
* **Analyse :** nos modules API importent `Form` directement, ce qui échoue si l'attribut n'est pas présent.
* **Correctifs recommandés :**
  - Ajouter un import conditionnel avec fallback (ex. définir un wrapper `def Form(*args, **kwargs): return args[0]` lorsque FastAPI n'est pas complet).
  - Documenter les dépendances minimales requises pour les stubs de tests.

### 8. Tâches asynchrones dans `NotificationService`
* **Symptôme :** `test_notification_persistence.py::test_emit_error_persists_without_service` échoue avec `Failed: async def functions are not natively supported.`
* **Analyse :** le service expose des fonctions `async` mais les tests les invoquent dans un contexte synchrone.
* **Correctifs recommandés :**
  - Fournir des wrappers synchrones pour les tests ou assurer que les coroutines soient exécutées via `asyncio.run` dans le code de production.
  - Mettre à jour les tests/fixtures pour utiliser un event loop dédié.

## Synthèse

La majorité des erreurs proviennent de dépendances manquantes, d'importations non résilientes face aux stubs de tests et d'initialisations incomplètes des services (base de données, notifications). Les correctifs ci-dessus visent à rendre le backend plus robuste, à réduire la fragilité face aux environnements de tests allégés et à garantir une expérience de développement cohérente.

