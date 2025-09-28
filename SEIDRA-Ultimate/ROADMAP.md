# Feuille de route « SEIDRA Ultimate »

> Dernière mise à jour : 2025-09-26
>
> Cette version reflète l’état réel du dépôt `SEIDRA-Ultimate` après revue complète des services backend, du frontend Next.js, des scripts d’installation et des artefacts d’exploitation. L’objectif principal est désormais la livraison d’un studio vidéo IA de nouvelle génération, supérieur à invideo.ai, orchestrant génération, montage timeline et prévisualisation temps réel. Chaque chantier indique les acquis observés dans le code ainsi que les actions restantes pour atteindre un niveau prêt pour une release commerciale.

## Synthèse de l’avancement

| Domaine | Statut | Constats clés | Points d’attention |
| --- | --- | --- | --- |
| Fondations backend | 90 % | Configuration centralisée (`core/config.py`), initialisation DB + seeds automatiques (`services/database.py`), lifecyle FastAPI complet (`main.py`). | Durcir la sécurité (hash du compte démo, secrets production) et fiabiliser la rotation des migrations. |
| API FastAPI | 95 % | Routers génération/personas/médias/jobs/modèles/paramètres/système opérationnels, validations Pydantic complètes. | Ajouter des limites de taux et tests de charge, finaliser la documentation OpenAPI utilisateur. |
| Orchestration IA & tâches asynchrones | 80 % | `GenerationService` orchestre la progression temps réel, Celery couvre image/vidéo/batch/cleanup et `ModelManager` délègue désormais aux endpoints ComfyUI & SadTalker (upload audio, téléchargement médias) pour des rendus réels.【F:SEIDRA-Ultimate/backend/services/model_manager.py†L358-L688】【F:SEIDRA-Ultimate/backend/api/generation.py†L274-L370】 | Sécuriser la tolérance aux pannes (timeouts, retries, file d’attente locale) et enrichir la métrologie GPU/remote (latence, VRAM, taux d’erreur) pour préparer la montée en charge. |
| Temps réel & supervision | 85 % | WebSocket manager multi-canaux, service de télémétrie (GPU, jobs, médias, système) et notifications centralisées. | Déployer alerting production (Prometheus/Loki) et historisation longue durée des métriques. |
| Frontend Ultimate | 80 % | L’interface Génération combine formulaire image et panneau vidéo (upload audio, référence) et un studio vidéo dédié (timeline multi-pistes, assets, prévisualisation frame-by-frame, suivi des jobs).【F:SEIDRA-Ultimate/frontend/src/components/generation/generation-interface.tsx†L640-L784】【F:SEIDRA-Ultimate/frontend/src/components/video-studio/video-studio.tsx†L1-L66】【F:SEIDRA-Ultimate/frontend/src/components/video-studio/store.ts†L1-L220】 | Affiner la collaboration temps réel (prévisualisation proxy, rendu basse résolution) et l’accessibilité (contrastes, clavier, ARIA), et relier la timeline aux métriques audio/vidéo générées. |
| Expérience développeur & QA | 75 % | Scripts d’installation cross-OS, docker-compose dev, suites de tests backend/frontend, et `ci-report.sh` exécute `make check` + coverage Pytest/Vitest dans la CI avec artefacts publiés.【F:SEIDRA-Ultimate/scripts/ci-report.sh†L1-L60】【F:SEIDRA-Ultimate/.github/workflows/ultimate-ci.yml†L17-L76】 | Étendre les rapports (perf/loadtest automatiques), documenter la rotation des secrets et intégrer des matrices GPU/OS dans la doc QA. |
| Déploiement & compatibilité | 75 % | Workflows CI/CD présents, manifestes Docker/Helm, monitoring Grafana/Prometheus. | Tester intégration bout-en-bout (release GHCR + chart Helm), ajouter scénarios de rollback et matrices de compatibilité OS/GPU.

---

## 1. Consolidation des fondations backend (90 %)

**Acquis vérifiés**

- Paramétrage unique via Pydantic Settings : chemins runtime, Redis, MinIO, ComfyUI/SadTalker et jeton WebSocket sont fournis par `core/config.py`, avec création automatique des répertoires médias/modèles/tmp.【F:workspace/SEIDRA-Ultimate/backend/core/config.py†L19-L99】
- Cycle de vie FastAPI complet (`lifespan`) : migrations Alembic + seeds, initialisation du `ModelManager`, démarrage du monitoring GPU et de la télémétrie, montage des routers et du répertoire `/media` dans `main.py`.【F:workspace/SEIDRA-Ultimate/backend/main.py†L31-L152】
- Base de données SQLAlchemy couverte (utilisateurs, personas, jobs, médias, LoRA, réglages NSFW) + seeds idempotents (`init_database`).【F:workspace/SEIDRA-Ultimate/backend/services/database.py†L230-L360】

**Prochaines priorités**

- Mutualiser la gestion des secrets (Vault/SSM) et documenter la procédure `scripts/rotate-default-user.py` pour la rotation automatique du compte démo.【F:SEIDRA-Ultimate/backend/services/database.py†L286-L360】【F:SEIDRA-Ultimate/scripts/rotate-default-user.py†L1-L140】
- Ajouter une checklist migration (rolling upgrade, sauvegarde) dans `SETUP.md` et automatiser la vérification de version Alembic.

## 2. Parité fonctionnelle des API FastAPI (95 %)

**Acquis vérifiés**

- Router génération : validations avancées, fusion persona, persistance et dispatch Celery optionnel.【F:workspace/SEIDRA-Ultimate/backend/api/generation.py†L23-L200】
- CRUD complets pour personas, médias, jobs, paramètres et modèles, avec pagination, filtres NSFW, favoris et gestion des LoRA côté API.【F:workspace/SEIDRA-Ultimate/backend/api/personas.py†L19-L200】【F:workspace/SEIDRA-Ultimate/backend/api/media.py†L21-L210】
- Endpoints système (health, télémétrie, GPU) exposés pour l’UI et l’observabilité.【F:workspace/SEIDRA-Ultimate/backend/main.py†L143-L205】

**Prochaines priorités**

- Ajouter du throttling (FastAPI-limiter ou équivalent) et des quotas par utilisateur pour préparer l’ouverture publique.
- Documenter les exemples d’appels (curl/Postman) dans le futur portail utilisateurs et enrichir le bundle OpenAPI.

## 3. Orchestration IA & tâches asynchrones (80 %)

**Acquis vérifiés**

- `GenerationService` orchestre la progression, sauvegarde les médias, notifie WebSocket + NotificationService, et gère les erreurs avec requeue.【F:backend/services/generation_service.py†L22-L200】
- Les workers Celery couvrent les jobs image/batch/vidéo/maintenance et centralisent la logique autour du service de génération.【F:backend/workers/generation_worker.py†L16-L90】【F:backend/workers/video_worker.py†L16-L64】

**Constats limitants**

- Les intégrations ComfyUI/SadTalker reposent sur des services distants : il faut fiabiliser la résilience (timeouts, retries, reprise sur erreur) et mieux tracer les temps de génération pour anticiper la scalabilité.【F:SEIDRA-Ultimate/backend/services/model_manager.py†L386-L688】
- Les jobs vidéo timeline restent séquentiels ; il manque encore un plan de priorisation/quotas et une stratégie de fallback local en cas d’indisponibilité des endpoints distants.【F:SEIDRA-Ultimate/backend/api/generation.py†L443-L480】

**Prochaines priorités**

- Renforcer l’observabilité (dashboards VRAM/latence, journalisation des retries) et ajouter des tests de charge ciblant les flux vidéo/audio.
- Définir un orchestrateur de priorités (temps réel vs batch) et une stratégie de dégradation contrôlée si les services ComfyUI/SadTalker deviennent indisponibles.

## 4. Temps réel, supervision & notifications (85 %)

**Acquis vérifiés**

- WebSocket manager authentifié par token, multi-canaux et gestion fine des messages clients/serveur.【F:workspace/SEIDRA-Ultimate/backend/main.py†L154-L205】
- Service de télémétrie diffusant snapshots (GPU, jobs, médias, système) et historique en mémoire, avec alertes basées sur seuils.【F:workspace/SEIDRA-Ultimate/backend/services/telemetry_service.py†L30-L190】
- NotificationService relié aux jobs (succès/erreurs) et aux alertes système, consommé côté frontend via le WebSocket context.【F:workspace/SEIDRA-Ultimate/backend/services/generation_service.py†L168-L199】【F:workspace/SEIDRA-Ultimate/frontend/src/lib/websocket-context.tsx†L1-L200】

**Prochaines priorités**

- Déployer la collecte Prometheus/Grafana fournie dans `monitoring/` et connecter Loki/Tempo pour la traçabilité temps réel.
- Ajouter une persistance des notifications critiques (PostgreSQL ou MinIO) afin d’éviter leur perte lors d’un redémarrage.

## 5. Frontend Ultimate (80 %)

**Acquis vérifiés**

- Shell App Router avec provider WebSocket, header mystique, sidebar à onglets et toasts personnalisées.【F:frontend/src/app/page.tsx†L15-L75】
- Interfaces Personas, Media, Models, Jobs et Settings riches en filtres/actions (duplication, favoris, cache, NSFW, télémétrie).【F:frontend/src/components/personas/persona-manager.tsx†L36-L200】【F:frontend/src/components/media/media-gallery.tsx†L19-L200】【F:frontend/src/components/models/model-manager.tsx†L8-L190】【F:frontend/src/components/jobs/job-monitor.tsx†L12-L200】【F:frontend/src/components/settings/settings-panel.tsx†L19-L200】

**Constats limitants**

- La prévisualisation reste statique (pas de rendu proxy temps réel ni waveform audio réel) et les assets générés ne sont pas encore annotés par métadonnées (fps, codec) pour guider le montage.【F:SEIDRA-Ultimate/frontend/src/components/video-studio/frame-preview.tsx†L1-L80】【F:SEIDRA-Ultimate/frontend/src/components/video-studio/store.ts†L120-L220】
- L’onboarding vidéo (tutoriels, scénarios guidés, accessibilité clavier) reste à compléter pour fluidifier l’adoption et préparer la commercialisation.

**Prochaines priorités**

- Ajouter des prévisualisations proxy (gif/webm basse résolution) et récupérer les waveforms/audio-peaks depuis le backend pour un montage précis.
- Finaliser l’onboarding (tours guidés, empty states), renforcer l’accessibilité (navigation clavier, ARIA) et couvrir le studio vidéo avec Vitest/Playwright.

## 6. Expérience développeur & QA (75 %)

**Acquis vérifiés**

- Scripts d’installation Linux/Windows et `start-seidra.sh` couvrant prérequis, dépendances IA et démarrage combiné.【F:SEIDRA-Ultimate/GETTING_STARTED.md†L31-L121】
- Scripts développeur (`scripts/dev-backend.sh`, `scripts/dev-frontend.sh`) et docker-compose dev pour lancer Redis/MinIO/ComfyUI mocks configurables.【F:SEIDRA-Ultimate/scripts/dev-backend.sh†L1-L120】【F:SEIDRA-Ultimate/docker-compose.dev.yml†L1-L63】
- Suite QA automatisée : `ci-report.sh` exécute `make check`, Pytest (coverage) et Vitest avec publication des artefacts dans GitHub Actions.【F:SEIDRA-Ultimate/scripts/ci-report.sh†L1-L80】【F:SEIDRA-Ultimate/.github/workflows/ultimate-ci.yml†L17-L76】

**Prochaines priorités**

- Enrichir la documentation QA (`TESTING.md`, `Ultimate_UPGRADE.md`) avec scénarios E2E reproductibles et matrices GPU/OS.
- Publier automatiquement les rapports de charge (`make loadtest`) et documenter la rotation des secrets/outils support (Vault, clés GPU).

## 7. Déploiement, CI/CD & compatibilité (75 %)

**Acquis vérifiés**

- Workflows GitHub Actions pour CI (lint/tests/Playwright) et release (build & push images Docker, scan de sécurité).【F:workspace/SEIDRA-Ultimate/.github/workflows/ultimate-ci.yml†L1-L210】【F:workspace/SEIDRA-Ultimate/.github/workflows/ultimate-release.yml†L1-L170】
- Stack de déploiement : docker-compose production, charts Helm, Nginx, monitoring Grafana/Prometheus/Loki documentés.【F:workspace/SEIDRA-Ultimate/deploy/docker/production.yml†L1-L79】【F:workspace/SEIDRA-Ultimate/monitoring/grafana/ultimate-dashboard.json†L1-L200】
- Catalogue OpenAPI versionné (`openapi/ultimate.json`) pour garantir la compatibilité contractuelle.【F:workspace/SEIDRA-Ultimate/openapi/ultimate.json†L1-L200】

**Prochaines priorités**

- Réaliser un dry-run complet (build GHCR → déploiement Helm) et documenter le rollback, y compris la migration des données.
- Ajouter des tests contractuels automatisés (comparaison `classic.json` vs `ultimate.json`) dans la CI et générer un changelog API.

---

### Utilisation de la feuille de route

1. **Sprint planning** : utiliser la synthèse pour prioriser les gaps critiques (sécurité backend, pipelines IA réels, QA).
2. **Suivi** : mettre à jour les pourcentages et constats à chaque itération majeure, en alignement avec `ROADMAP_PROGRESS.md`.
3. **Communication** : partager cette feuille de route avec les parties prenantes produit/ops pour valider la trajectoire vers la release commerciale.
