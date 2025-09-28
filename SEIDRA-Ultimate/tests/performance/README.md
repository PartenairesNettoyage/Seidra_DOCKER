# Plan de tests de charge SEIDRA Ultimate

Ce dossier contient les scénarios Locust pour solliciter les routes critiques du backend FastAPI (`/api/generate`, `/api/media`, `/api/system/*`). Il complète la cible `make loadtest`, qui bâtit un container dédié (`scripts/load-testing`) et publie les rapports dans `reports/perf`.

## Prérequis
- Backend démarré sur `http://localhost:8000` (adapter `--host` le cas échéant).
- Jeton JWT valide pour l’utilisateur de test (`SEIDRA_PERF_TOKEN`).
- Python 3.11+ avec `locust` installé **ou** utilisation de l'image Docker fournie (`make loadtest`).

### Installation Locust locale
```bash
pip install locust
```

## Variables d’environnement
| Variable | Description | Défaut |
| --- | --- | --- |
| `SEIDRA_PERF_TOKEN` | Jeton JWT utilisé dans l’en-tête `Authorization`. | `changeme` |
| `SEIDRA_PERF_PROMPT` | Prompt injecté lors des tests de génération. | « Portrait mystique… » |
| `SEIDRA_PERF_MODEL` | Modèle cible (`sdxl-base`, `sdxl-refiner`, etc.). | `sdxl-base` |
| `SEIDRA_PERF_ENABLE_GENERATION` | Mettre à `0` pour désactiver les appels coûteux (`/api/generate`). | `1` |
| `SEIDRA_PERF_TIMEOUT` | Timeout (secondes) pour chaque requête HTTP. | `30` |
| `SEIDRA_PERF_GENERATION_ENDPOINT` | Endpoint POST pour la génération d’image. | `/api/generate/single` |
| `SEIDRA_PERF_MEDIA_LIST_ENDPOINT` | Endpoint GET listant les médias. | `/api/media` |
| `SEIDRA_PERF_MEDIA_STATS_ENDPOINT` | Endpoint GET des statistiques médias. | `/api/media/stats` |

## Lancer Locust (mode interactif)
```bash
export SEIDRA_PERF_TOKEN="<votre_token>"
locust -f tests/performance/locustfile.py --host http://localhost:8000
```

Ouvrez ensuite `http://localhost:8089`, définissez le nombre d’utilisateurs simulés et le taux d’apparition puis lancez la charge. Le rapport temps réel permet d’ajuster les quotas (`X-RateLimit-*`) exposés par le middleware de l’API.【F:SEIDRA-Ultimate/backend/main.py†L118-L147】

### Mode Docker automatisé
```bash
make loadtest SEIDRA_API_URL=http://localhost:8000 SEIDRA_JWT="<votre_token>"
```

La cible build l’image `seidra-loadtest`, exécute Locust en headless avec les variables fournies (`USERS`, `SPAWN_RATE`, `RUN_TIME` optionnels) et génère un rapport Markdown/HTML (via `scripts/load-testing/generate_report.py`).

## Bonnes pratiques
- Activez `SEIDRA_PERF_ENABLE_GENERATION=0` sans GPU ou pour concentrer la charge sur `/api/media`.
- Montez progressivement les utilisateurs pour identifier les seuils de saturation avant les erreurs `HTTP 429`.
- Archivez les rapports HTML/Markdown produits dans `reports/perf/` à la fin de chaque campagne.

## Scénario vidéo longue durée

Le fichier `video_longform_locustfile.py` pilote le pipeline ComfyUI/SadTalker via `POST /api/generate/video`. Chaque utilisateur envoie un segment (`duration_seconds ≤ 60`) mais renseigne les métadonnées d’un rendu multi-minutes (`targetDurationSeconds`, `segmentCount`). Les rapports sont exportés automatiquement dans `reports/perf/`.

### Variables spécifiques
| Variable | Description | Défaut |
| --- | --- | --- |
| `SEIDRA_PERF_HOST` | URL du backend ciblé. | `http://localhost:8000` |
| `SEIDRA_PERF_VIDEO_MODEL` | Modèle vidéo (SadTalker distant ou preset local). | `sadtalker` |
| `SEIDRA_PERF_VIDEO_TOTAL_MIN` | Durée totale minimale simulée (secondes). | `180` |
| `SEIDRA_PERF_VIDEO_TOTAL_MAX` | Durée totale maximale simulée (secondes). | `420` |
| `SEIDRA_PERF_VIDEO_SEGMENT` | Durée d’un segment envoyé au backend (≤ 60 s). | `45` |
| `SEIDRA_PERF_VIDEO_PIPELINE` | Preset ComfyUI injecté dans les métadonnées. | `comfyui-longform-v1` |
| `SEIDRA_PERF_VIDEO_VOICE` | Preset SadTalker (voix/visage). | `sadtalker-conversation` |
| `SEIDRA_PERF_REPORT_NAME` | Préfixe du rapport Markdown généré. | `video_longform` |

### Exécution
```bash
export SEIDRA_PERF_TOKEN="<votre_token>"
locust -f tests/performance/video_longform_locustfile.py --host "$SEIDRA_PERF_HOST"
```

Le script collecte la latence, les pics VRAM (`/api/system/telemetry/generation?media_type=video`) et les erreurs GPU (`cudaErrors`) via l’API système. Les mesures sont consolidées à l’arrêt de Locust dans `reports/perf/<nom>_<horodatage>.md`.

### Seuils recommandés
- **Latence vidéo** : p95 < 420 s et moyenne < 300 s sur la fenêtre de test.
- **VRAM** : pic moyen < 22 000 MB (≈ 90 % d’une carte 24 Go).
- **Erreurs GPU** : aucune occurrence `cudaErrors`; toute occurrence déclenche une investigation immédiate.
- **Débit** : maintenir > 0,15 req/s pour un utilisateur unique (sinon revoir la capacité des workers Celery).

Consignez les rapports Markdown générés et partagez-les avec l’équipe opérations pour corrélation avec Prometheus/Grafana.
