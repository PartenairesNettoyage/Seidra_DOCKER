# SEIDRA Ultimate

SEIDRA Ultimate est la distribution « build your own myth » de SEIDRA : un backend FastAPI prêt pour la production, une interface Next.js 14 temps réel et une chaîne d'orchestration IA calibrée pour les GPU NVIDIA RTX 3090. Le dépôt rassemble les artefacts d'architecture, les scripts d'installation natives et toute la documentation d'exploitation de la plateforme.

## 🎯 Vision & positionnement
- **Studio vidéo IA nouvelle génération** : orchestration complète des pipelines d'images, de vidéos et de voix via des workers Celery et des services GPU externes (ComfyUI, SadTalker).【F:SEIDRA-Ultimate/backend/services/orchestrator.py†L1-L189】
- **Personas et cohérence créative** : gestion des profils stylistiques, galeries médias et métadonnées enrichies côté frontend pour maintenir la continuité visuelle.【F:SEIDRA-Ultimate/frontend/src/app/personas/page.tsx†L1-L178】
- **Expérience premium** : UI violette/dorée, WebSockets pour le retour temps réel, télémétrie GPU intégrée et notifications toast.【F:SEIDRA-Ultimate/frontend/src/app/layout.tsx†L1-L85】【F:SEIDRA-Ultimate/backend/api/routes/system.py†L1-L132】
- **Industrialisation** : scripts d'installation automatisés, Makefile orienté QA, observabilité complète et déploiements Kubernetes/Helm pour le staging et la production.【F:SEIDRA-Ultimate/install-dev.sh†L1-L130】【F:SEIDRA-Ultimate/Makefile†L1-L110】【F:SEIDRA-Ultimate/deploy/README.md†L1-L160】

## 🗂️ Structure du dépôt
- `SEIDRA-Ultimate/` : code source principal et outils d'exploitation.
  - `backend/` : API FastAPI, orchestrateur IA, workers Celery et schémas Pydantic.【F:SEIDRA-Ultimate/backend/main.py†L1-L205】
  - `frontend/` : application Next.js 14 (TypeScript, Tailwind, Radix UI) couvrant génération, personas, galerie et monitoring temps réel.【F:SEIDRA-Ultimate/frontend/package.json†L1-L53】
  - `scripts/` : scripts shell/Python pour l'onboarding, la rotation des secrets, la validation monitoring et la charge.【F:SEIDRA-Ultimate/scripts/monitoring/check_dashboards.py†L1-L167】【F:SEIDRA-Ultimate/scripts/load-testing/generate_report.py†L1-L154】
  - `deploy/` : manifests Docker Compose, Helm et guides Kubernetes pour le staging/production.【F:SEIDRA-Ultimate/deploy/README.md†L1-L160】
  - `monitoring/` : provisioning Prometheus/Grafana/Loki + runbook d'observabilité.【F:SEIDRA-Ultimate/monitoring/README.md†L1-L120】
  - `docs/`, `doc/` : documentation API, PRD, guides utilisateurs/ops, diagrammes et dossiers QA.【F:SEIDRA-Ultimate/docs/api/README.md†L1-L60】【F:doc/SEIDRA_Ultimate_Documentation.md†L1-L120】
- `SEIDRA_logo.png` : identité visuelle.
- `SEIDRA-MGX-codex-restructure-ultimate-project-details.zip` : archive des livrables détaillés (PRD, wireframes, diagrammes).

## 🚀 Mise en route (environnement développeur)
1. **Cloner & se placer dans le projet**
   ```bash
   git clone <URL_DU_REPO>
   cd SEIDRA_Ultimate/SEIDRA-Ultimate
   ```
2. **Initialiser l'environnement Python/Node**
   ```bash
   ./install-dev.sh --with-ml
   ```
   Le script crée `.venv`, installe `requirements-dev.txt` (et `requirements-ml.txt` si l'option est fournie), configure `npm ci` et prépare l'environnement Docker facultatif pour Redis/MinIO selon vos paramètres.【F:SEIDRA-Ultimate/install-dev.sh†L1-L129】
3. **Lancer les services en mode hot-reload**
   ```bash
   source .venv/bin/activate
   make dev-backend    # FastAPI + Celery (uvicorn)
   make dev-frontend   # Next.js 14
   ```
   Utilisez `make check` pour exécuter linting, typage, tests et validation monitoring en une seule commande.【F:SEIDRA-Ultimate/Makefile†L1-L110】
4. **Télécharger ou régénérer les modèles IA**
   ```bash
   python scripts/setup-models.py --profile sdxl
   ```
   Le script vérifie la disponibilité GPU et récupère les modèles/LoRA définis dans le profil choisi.【F:SEIDRA-Ultimate/scripts/setup-models.py†L1-L220】

> 💡 Pour une installation native « one-click » incluant la création des scripts `start-backend.*`, `start-frontend.*` et `start-seidra.*`, utilisez `install-linux.sh` ou `install-windows.bat` selon votre OS.【F:SEIDRA-Ultimate/install-linux.sh†L320-L410】【F:SEIDRA-Ultimate/install-windows.bat†L180-L245】

## 🐳 Exécution complète via Docker Compose
1. **Préparer les variables d'environnement**
   ```bash
   cp .env.docker.example .env.docker
   ```
   Modifiez au besoin les secrets ou URLs d'accès avant de démarrer la stack (le fichier pointe déjà vers Postgres, Redis et MinIO conteneurisés).
2. **Construire et lancer l'ensemble des services**
   ```bash
   docker compose up --build
   ```
   L'interface Ultimate est ensuite disponible sur [http://localhost:8080](http://localhost:8080), MinIO Console sur `http://localhost:9001` et l'API FastAPI sur `http://localhost:8080/api` via le proxy Nginx.
3. **Surveiller ou arrêter les services**
   ```bash
   docker compose logs -f backend   # suivi temps réel
   docker compose down              # arrêt + libération des conteneurs
   ```
   Les volumes `seidra-data`, `pg-data` et `minio-data` conservent données applicatives, base et objets MinIO entre deux exécutions.

## 🔐 Authentification & API
- Les endpoints critiques (`/api/generate`, `/api/media`, `/api/system/*`) sont protégés par JWT et exposent des politiques de rate-limiting via `SlowAPIMiddleware` + Redis.【F:SEIDRA-Ultimate/backend/main.py†L118-L205】【F:SEIDRA-Ultimate/backend/api/middleware.py†L1-L74】
- Générez un token avec les utilitaires backend (`scripts/rotate-default-user.py`, endpoints `/api/auth/login`) ou via les exemples `curl` fournis dans `docs/api/`.
- La documentation OpenAPI (JSON) est disponible dans `openapi/ultimate.json` ; `make docs-api` génère la version Redoc (`docs/api/reference.html`).【F:SEIDRA-Ultimate/docs/api/README.md†L33-L60】【F:SEIDRA-Ultimate/Makefile†L87-L100】

## ✅ QA & validation
- `make check` enchaîne lint, mypy, tests Pytest/Vitest et validation Grafana/Prometheus via `monitoring-validate`.
- `make loadtest` construit l'image Docker Locust et produit des rapports Markdown/HTML dans `reports/perf` (scripts Python complémentaires dans `scripts/load-testing/`).【F:SEIDRA-Ultimate/Makefile†L56-L110】【F:SEIDRA-Ultimate/tests/performance/README.md†L1-L120】
- Les scénarios de tests de performance manuels sont décrits dans `tests/performance/README.md` (génération d'images et pipeline vidéo longue durée).

## 📊 Observabilité & monitoring
- La stack Prometheus/Grafana/Loki peut être démarrée via `make observability-up` (ou `docker compose -f deploy/docker/monitoring.yml up -d`).【F:SEIDRA-Ultimate/Makefile†L111-L140】【F:SEIDRA-Ultimate/monitoring/README.md†L29-L80】
- Les dashboards, règles d'alerte et procédures d'investigation sont centralisés dans `monitoring/` avec un runbook dédié.
- Les déploiements Kubernetes utilisent les valeurs préparées dans `deploy/k8s/monitoring/` pour provisionner les mêmes tableaux de bord et alertes via ConfigMaps.【F:SEIDRA-Ultimate/deploy/k8s/monitoring/README.md†L1-L160】

## 🚢 Déploiement
- Les manifestes Helm (`deploy/helm`) orchestrent backend, frontend, workers et jobs Alembic. Le workflow GitHub Actions `helm-dry-run` reconstruit les images GHCR, exécute `helm lint` et produit le manifeste rendu pour audit.【F:SEIDRA-Ultimate/deploy/README.md†L1-L160】
- Des scripts d'aide (`scripts/deploy-staging.sh`) facilitent la promotion vers un cluster staging (`seidra-staging`).
- Les fichiers `deploy/docker/*.yml` fournissent des stacks Compose prêtes à l'emploi (monitoring, production GPU).

## 📈 Feuille de route & progression
- L'avancement global (~72 %) et les prochaines priorités sont suivis dans `ROADMAP_PROGRESS.md` (piliers IA, frontend, observabilité, QA).【F:SEIDRA-Ultimate/ROADMAP_PROGRESS.md†L1-L116】
- `ROADMAP.md` décrit les livrables prévus (studio vidéo, intégration GPU avancée, sécurité, industrialisation QA).

## 📚 Ressources complémentaires
- [Guide de mise en route détaillé](SEIDRA-Ultimate/GETTING_STARTED.md)
- [Guide utilisateur final](doc/SEIDRA_Ultimate_User_Guide.md)
- [Documentation technique intégrale](doc/SEIDRA_Ultimate_Documentation.md)
- [Documentation API & politiques de throttling](SEIDRA-Ultimate/docs/api/README.md)
- [Roadmap & progression](SEIDRA-Ultimate/ROADMAP.md) • [Progression](SEIDRA-Ultimate/ROADMAP_PROGRESS.md)

---
**SEIDRA Ultimate** vise à livrer une suite IA locale premium, industrialisée de bout en bout, en combinant pipelines GPU de pointe, observabilité maîtrisée et expérience créative haut de gamme.
