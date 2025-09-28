# SEIDRA Ultimate – Guide d'expérience utilisateur

## 1. Vision et promesse produit
SEIDRA Ultimate place désormais la livraison d’un studio vidéo IA de nouvelle génération au cœur de sa proposition : un module plus abouti qu’invideo.ai, capable de transformer des scripts en scènes générées, montées et prévisualisées en temps réel dans le navigateur.【F:workspace/SEIDRA_PRD_FINAL.md†L12-L152】 Autour de cet objectif, la plateforme conserve son ADN premium « Build your own myth » mêlant esthétique violet/doré, personas persistants et installation 1‑clic optimisée pour GPU RTX 3090.【F:workspace/SEIDRA_PRD_FINAL.md†L12-L44】 Cette promesse s’adresse autant aux artistes qu’aux créateurs de contenu ou professionnels ayant besoin de batchs rapides et d’un contrôle temps réel sur la production.【F:workspace/SEIDRA_PRD_FINAL.md†L33-L44】

## 2. Pré-requis matériels et installation
Avant de lancer l’application, vérifiez que votre machine respecte les recommandations officielles : RTX 3090 (24 Go VRAM), 32 Go de RAM, 100 Go libres et CUDA 12.1.【F:workspace/SEIDRA-Ultimate/GETTING_STARTED.md†L5-L16】 L’installation est automatisée via `install-linux.sh` (ou `install-windows.bat`) qui configure Python, Node.js, Redis, télécharge les modèles SDXL/LoRA et génère les scripts de démarrage (`start-seidra.sh`).【F:workspace/SEIDRA-Ultimate/GETTING_STARTED.md†L31-L87】 Après installation, lancez `./start-seidra.sh` pour démarrer backend, frontend et WebSocket en un clic.【F:workspace/SEIDRA-Ultimate/GETTING_STARTED.md†L73-L87】

## 3. Première connexion et structure de l'interface
L’application s’ouvre sur un shell Next.js avec un provider WebSocket global, un header mystique, une sidebar à onglets (Generate, Personas, Media, Models, Jobs, Settings) et des toasts stylisées.【F:workspace/SEIDRA-Ultimate/frontend/src/app/page.tsx†L15-L75】 Chaque onglet expose un module autonome, accessible via des transitions fluides et un layout glassmorphism.

## 4. Modules fonctionnels et parcours utilisateur

### 4.1 Génération d'images
- **Interface** : le module `GenerationInterface` propose un formulaire riche (prompt, persona, LoRA, scheduler, seed, qualité) avec presets par défaut et synchronisation des paramètres persona.【F:workspace/SEIDRA-Ultimate/frontend/src/components/generation/generation-interface.tsx†L35-L200】
- **Backend** : les requêtes sont validées côté API (`/api/generate`), fusionnent les prompts persona et déclenchent une orchestration Celery/GPU ou fallback mock selon la configuration.【F:workspace/SEIDRA-Ultimate/backend/api/generation.py†L23-L200】
- **Retour temps réel** : la progression est suivie via WebSocket (statuts, pourcentage, messages) et des notifications s’affichent automatiquement selon l’état du job.【F:workspace/SEIDRA-Ultimate/frontend/src/lib/websocket-context.tsx†L16-L200】【F:workspace/SEIDRA-Ultimate/backend/services/generation_service.py†L44-L200】

### 4.2 Personas mystiques
- **Gestion côté client** : `PersonaManager` offre recherche, duplication, suppression et formulaire d’édition avec paramètres (width, height, steps, LoRA).【F:workspace/SEIDRA-Ultimate/frontend/src/components/personas/persona-manager.tsx†L36-L200】
- **Persistant côté serveur** : l’API `/api/personas` gère création, mise à jour, favoris, tags, filtres NSFW et renvoie des timestamps normalisés pour l’UI.【F:workspace/SEIDRA-Ultimate/backend/api/personas.py†L19-L200】
- **Utilisation** : sélectionner une persona dans l’onglet Generate pré-remplit prompt, LoRA et paramètres avancés pour assurer la cohérence stylistique.【F:workspace/SEIDRA-Ultimate/frontend/src/components/generation/generation-interface.tsx†L77-L137】

### 4.3 Galerie médias
- **Dashboard** : `MediaGallery` présente statistiques (total, favoris, récents) et boutons Refresh.【F:workspace/SEIDRA-Ultimate/frontend/src/components/media/media-gallery.tsx†L19-L98】
- **Filtres avancés** : recherche texte, tags multiples, persona spécifique, favoris uniquement et reset instantané.【F:workspace/SEIDRA-Ultimate/frontend/src/components/media/media-gallery.tsx†L99-L147】
- **Actions** : favoris togglables, édition des tags, suppression, téléchargement direct, affichage persona associé et preview responsive.【F:workspace/SEIDRA-Ultimate/frontend/src/components/media/media-gallery.tsx†L150-L200】 Côté backend, `/api/media` applique pagination, filtres et expose les métadonnées complètes (tags, NSFW, persona).【F:workspace/SEIDRA-Ultimate/backend/api/media.py†L21-L210】

### 4.4 Catalogue de modèles & LoRA
- **Vue runtime** : `ModelManager` affiche les pipelines chargés, LoRA disponibles, taille du cache et actions Reload/Clear cache via toasts promises.【F:workspace/SEIDRA-Ultimate/frontend/src/components/models/model-manager.tsx†L8-L88】
- **Catalogue** : listes filtrables des pipelines de base et LoRA avec actions de téléchargement/suppression et état pending.【F:workspace/SEIDRA-Ultimate/frontend/src/components/models/model-manager.tsx†L90-L190】
- **Orchestration** : côté backend, `ModelManager` prépare SDXL, gère le cache GPU, charge/décharge les LoRA et fournit des placeholders si CUDA absent.【F:workspace/SEIDRA-Ultimate/backend/services/model_manager.py†L161-L312】

### 4.5 Suivi des jobs
- **UI** : `JobMonitor` regroupe statistiques, filtres (statut, persona, recherche), boutons Refresh et cartes détaillées avec progression animée et miniatures.【F:workspace/SEIDRA-Ultimate/frontend/src/components/jobs/job-monitor.tsx†L12-L200】
- **Actions** : annulation/retry sont exposées via hooks, et les messages temps réel sont fusionnés grâce au contexte WebSocket.【F:workspace/SEIDRA-Ultimate/frontend/src/components/jobs/job-monitor.tsx†L29-L200】【F:workspace/SEIDRA-Ultimate/frontend/src/lib/websocket-context.tsx†L66-L200】
- **Server side** : `GenerationService` met à jour la base (progression, erreurs, résultats) et envoie des événements `generation_progress` / `generation_complete`.【F:workspace/SEIDRA-Ultimate/backend/services/generation_service.py†L82-L189】

### 4.6 Paramètres & santé système
- **Panneau Settings** : visualise l’état du WebSocket, les métriques GPU/CPU, les notifications récentes et permet de modifier thème, langue, notifications, opt-in télémétrie et réglages NSFW avec boutons de sauvegarde contextualisés.【F:workspace/SEIDRA-Ultimate/frontend/src/components/settings/settings-panel.tsx†L19-L200】
- **Télémétrie** : le backend agrège GPU, modèles, jobs, médias, connexions et métriques système pour alimenter cette vue et les alertes.【F:workspace/SEIDRA-Ultimate/backend/services/telemetry_service.py†L30-L190】

## 5. Notifications et temps réel
Les WebSockets (route `/ws/{client_id}`) exigent un token, gèrent l’inscription aux canaux et transmettent jobs, système et notifications sécurisées.【F:workspace/SEIDRA-Ultimate/backend/main.py†L154-L205】 Le provider frontend déduplique jusqu’à 200 jobs, applique des toasts selon la sévérité et maintient une liste de notifications historiques pour l’utilisateur.【F:workspace/SEIDRA-Ultimate/frontend/src/lib/websocket-context.tsx†L66-L200】 Les événements côté serveur incluent les snapshots système, la progression des générations et les alertes issues du `NotificationService`.【F:workspace/SEIDRA-Ultimate/backend/services/generation_service.py†L168-L199】

## 6. Scénarios d'utilisation recommandés
1. **Créer une série cohérente** :
   - Créez/dupliquez une persona avec prompts et LoRA préférés depuis l’onglet Personas.【F:workspace/SEIDRA-Ultimate/frontend/src/components/personas/persona-manager.tsx†L95-L169】
   - Lancez une génération en synchronisant prompt/paramètres persona et en sélectionnant un preset de qualité.【F:workspace/SEIDRA-Ultimate/frontend/src/components/generation/generation-interface.tsx†L82-L188】
   - Suivez la progression en direct dans l’onglet Jobs ou via les toasts, puis retrouvez les images filtrées par persona dans la galerie.【F:workspace/SEIDRA-Ultimate/frontend/src/components/jobs/job-monitor.tsx†L67-L198】【F:workspace/SEIDRA-Ultimate/frontend/src/components/media/media-gallery.tsx†L150-L200】
2. **Gestion des LoRA personnalisées** :
   - Consultez l’état runtime (modèles chargés, batch optimal) et déclenchez un téléchargement LoRA depuis l’onglet Models.【F:workspace/SEIDRA-Ultimate/frontend/src/components/models/model-manager.tsx†L66-L188】
   - Assurez-vous que le backend a bien enregistré le preset et qu’il est disponible pour la prochaine génération.【F:workspace/SEIDRA-Ultimate/backend/services/model_manager.py†L262-L312】
3. **Surveillance de performances** :
   - Ouvrez Settings pour vérifier la température GPU, l’occupation mémoire et les connexions actives.【F:workspace/SEIDRA-Ultimate/frontend/src/components/settings/settings-panel.tsx†L64-L112】
   - Configurez vos préférences de notifications pour recevoir les alertes critiques (erreurs, jobs terminés) en temps réel.【F:workspace/SEIDRA-Ultimate/frontend/src/components/settings/settings-panel.tsx†L167-L200】【F:workspace/SEIDRA-Ultimate/frontend/src/lib/websocket-context.tsx†L112-L200】

## 7. Personnalisation et productivité
- **Favoris & tags** : utilisez la galerie pour marquer vos œuvres préférées, ajouter des tags et filtrer rapidement vos collections.【F:workspace/SEIDRA-Ultimate/frontend/src/components/media/media-gallery.tsx†L150-L200】
- **Batchs optimisés** : profitez des presets qualité et du paramètre `num_images` pour générer jusqu’à 4 images d’un coup tout en conservant la traçabilité (metadata, seed).【F:workspace/SEIDRA-Ultimate/frontend/src/components/generation/generation-interface.tsx†L167-L199】
- **Scripts de relance** : en cas de mise à jour de modèles ou dépendances, relancez `scripts/setup-models.py` et les scripts `start-backend.sh` / `start-frontend.sh` générés automatiquement.【F:workspace/SEIDRA-Ultimate/GETTING_STARTED.md†L61-L88】

## 8. Dépannage rapide
- Vérifiez l’état du GPU avec `nvidia-smi` si la télémétrie remonte une indisponibilité, puis relancez `./start-seidra.sh` pour réinitialiser backend et WebSocket.【F:workspace/SEIDRA-Ultimate/GETTING_STARTED.md†L73-L132】
- En cas d’erreur 401 sur l’API, régénérez un token JWT via le script Python fourni et mettez-le à jour côté frontend (`api.setToken`).【F:workspace/SEIDRA-Ultimate/GETTING_STARTED.md†L89-L108】
- Si un téléchargement de modèle échoue, rejouez `python scripts/setup-models.py` depuis l’environnement virtuel backend ; des placeholders sont créés automatiquement en CI mais un téléchargement complet est requis pour la génération GPU.【F:workspace/SEIDRA-Ultimate/GETTING_STARTED.md†L61-L69】【F:workspace/SEIDRA-Ultimate/backend/services/model_manager.py†L262-L312】

## 8 bis. Collection Postman et exemples cURL

### Préparer votre environnement d’appels

1. Ajoutez une variable `base_url` pointant vers l’URL du backend (par défaut `http://localhost:8000`).
2. Authentifiez-vous via `POST /api/auth/login`, récupérez le jeton JWT et stockez-le dans la variable `token` pour l’en-tête `Authorization: Bearer {{token}}`.
3. Activez l’affichage des en-têtes `X-RateLimit-*` et `X-RateLimit-Policy` dans Postman afin de suivre les quotas propres aux routes `generation` et `media`, tels que configurés côté backend.【F:SEIDRA-Ultimate/backend/main.py†L118-L147】【F:SEIDRA-Ultimate/backend/api/generation.py†L188-L520】【F:SEIDRA-Ultimate/backend/api/media.py†L224-L606】

### Route `generation`

- **Postman** : `POST {{base_url}}/api/generate/single` avec corps JSON
  ```json
  {
    "prompt": "Portrait mystique en clair-obscur",
    "width": 1024,
    "height": 1024,
    "num_inference_steps": 30,
    "guidance_scale": 7.5,
    "num_images": 1,
    "model_name": "sdxl-base"
  }
  ```
  Attendez un `status` HTTP `202` et un `job_id` permettant de suivre la génération via `/api/jobs/{job_id}`.【F:SEIDRA-Ultimate/backend/api/generation.py†L188-L374】
- **cURL** :
  ```bash
  curl --request POST "${base_url:-http://localhost:8000}/api/generate/single" \
    --header "Authorization: Bearer ${token}" \
    --header "Content-Type: application/json" \
    --data '{
      "prompt": "Portrait mystique en clair-obscur",
      "width": 1024,
      "height": 1024,
      "num_inference_steps": 30,
      "guidance_scale": 7.5,
      "num_images": 1,
      "model_name": "sdxl-base"
    }'
  ```

La réponse précise si le traitement est délégué à Celery (`SEIDRA_USE_CELERY=1`) ou exécuté localement, puis renvoie un message d’estimation et l’identifiant du job.【F:SEIDRA-Ultimate/backend/api/generation.py†L202-L352】

### Route `media`

- **Lister la médiathèque** : `GET {{base_url}}/api/media` avec l’en-tête `Authorization`. Ajoutez éventuellement `search_query`, `tags` ou `favorites_only` pour filtrer la réponse paginée (`total`, `items`).【F:SEIDRA-Ultimate/backend/api/media.py†L224-L356】
- **Téléverser un asset vidéo** : `POST {{base_url}}/api/media/video-assets` en `form-data` (`file`, `duration`, `kind`). La réponse `VideoAssetResponse` contient `id`, `url`, `download_url` et le statut `ready`.【F:SEIDRA-Ultimate/backend/api/media.py†L182-L287】
- **cURL – export ZIP** :
  ```bash
  curl --request POST "${base_url:-http://localhost:8000}/api/media/export" \
    --header "Authorization: Bearer ${token}" \
    --header "Content-Type: application/json" \
    --data '{
      "media_ids": ["<uuid_media>"],
      "format": "zip",
      "include_metadata": true
    }'
  ```

Utilisez ensuite `GET /api/media/{media_id}` ou `/api/media/{media_id}/download` pour récupérer les fichiers, et `GET /api/media/stats` pour consulter les agrégats (par persona, par période). Les quotas exposés dans les en-têtes permettent d’anticiper les éventuels retours `429` lors d’opérations massives.【F:SEIDRA-Ultimate/backend/api/media.py†L298-L606】

## 9. Documentation API
- Consultez les fiches par ressource (exemples `curl`, réponses JSON, erreurs fréquentes) dans [`SEIDRA-Ultimate/docs/api/`](../SEIDRA-Ultimate/docs/api/README.md).
- Générez la version HTML interactive depuis la racine `SEIDRA-Ultimate/` avec `make docs-api` pour obtenir `docs/api/reference.html` (Redoc).

---
Ce guide fournit une vue utilisateur exhaustive de SEIDRA Ultimate et cadre l’expérience vers l’objectif principal : un studio vidéo IA premium surpassant invideo.ai. Pour toute question avancée (pipeline GPU, intégrations externes, déploiement), référez-vous aux documents techniques complémentaires (`SEIDRA_Ultimate_Documentation.md`, `Ultimate_UPGRADE.md`).
