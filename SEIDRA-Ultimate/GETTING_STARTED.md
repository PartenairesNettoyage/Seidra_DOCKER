# Guide de mise en route – SEIDRA Ultimate

Bienvenue dans **SEIDRA Ultimate**, la plateforme de génération IA optimisée pour un GPU de classe **RTX 3090** et l'utilisation de modèles avancés (Stable Diffusion XL, LoRA, etc.). Ce guide détaille les prérequis matériels, l'installation automatique des dépendances, la configuration des modèles et les étapes pour lancer l'ensemble backend/frontend.

## 1. Prérequis matériels et système

| Composant | Recommandation |
|-----------|----------------|
| GPU       | NVIDIA RTX 3090 (24 Go VRAM) ou carte équivalente compatible CUDA 12.1 |
| Pilotes   | NVIDIA Driver ≥ 535 + CUDA 12.1 Toolkit |
| CPU       | 8 cœurs (16 threads recommandés) |
| RAM       | 32 Go minimum (64 Go recommandés) |
| Stockage  | 100 Go libres (les modèles SDXL/LoRA occupent ~20 Go) |
| OS        | Ubuntu 22.04 LTS ou distribution Linux compatible avec `install-linux.sh` |

Assurez-vous également que `git`, `curl`, `wget` et `systemd` sont disponibles pour permettre le démarrage automatique de Redis et la création des services.

### 1.1 Services GPU externes (ComfyUI / SadTalker)

La génération d'images et de vidéos s'appuie désormais sur deux services d'inférence distants :

- **ComfyUI** pour les workflows Stable Diffusion XL.
- **SadTalker** pour la synthèse vidéo lip-sync.

Installez ces services sur une ou plusieurs machines équipées d'un GPU NVIDIA compatible CUDA 12.1 (24 Go de VRAM recommandés). Exposez les API HTTP correspondantes (par défaut `http://<hôte>:8188` pour ComfyUI et `http://<hôte>:8002` pour SadTalker) et définissez les variables d'environnement suivantes côté backend :

```bash
export SEIDRA_COMFYUI_URL="http://gpu-box.local:8188"
export SEIDRA_SADTALKER_URL="http://gpu-box.local:8002"
```

Les services doivent publier un endpoint `GET /health` renvoyant l'état de la file d'attente. Durant l'initialisation, le backend télécharge automatiquement les LoRA référencées et vérifie la disponibilité de chaque moteur GPU.

## 2. Structure du projet

```
SEIDRA-Ultimate/
├── backend/                # API FastAPI + orchestrateur de jobs
├── frontend/               # Interface utilisateur (Vite + Svelte)
├── scripts/setup-models.py # Téléchargement automatique des modèles (SDXL & LoRA)
├── install-linux.sh        # Installation automatisée (backend, frontend, modèles)
└── start-seidra.sh         # Script de démarrage combiné (Redis + backend + frontend)
```

## Ressources QA et validation

- **Plan de tests E2E** : suivez [`doc/QA/PLAN_TESTS_E2E.md`](doc/QA/PLAN_TESTS_E2E.md) pour vérifier les parcours critiques (login, génération SDXL, SadTalker, observabilité).
- **Matrice GPU / OS** : consultez [`doc/QA/GPU_OS_MATRIX.md`](doc/QA/GPU_OS_MATRIX.md) pour connaître les combinaisons certifiées et la procédure de qualification.
- **Tests de charge** : définissez `SEIDRA_API_URL` et un token `SEIDRA_JWT` puis exécutez `make loadtest`. La cible construit l'image Docker `seidra-loadtest`, lance Locust en mode headless et génère automatiquement les rapports HTML/Markdown dans `reports/perf`.
- **Rotation des secrets** : le guide [`doc/SRE/GESTION_ROTATION_SECRETS_SUPPORT.md`](doc/SRE/GESTION_ROTATION_SECRETS_SUPPORT.md) décrit les procédures SRE (mot de passe démo, `SECRET_KEY`, Grafana, MinIO).

## 3. Installation automatisée

1. **Cloner le dépôt**
   ```bash
   git clone <URL_DU_REPO>
   cd SEIDRA-Ultimate
   ```

2. **Lancer le script d'installation Linux** (gère toutes les dépendances système, Python, Node.js, Redis, modèles IA, LoRA et optimisations RTX 3090) :
   ```bash
   chmod +x install-linux.sh
   ./install-linux.sh
   ```
   Le script effectue notamment :
   - Vérification du matériel (CPU, RAM, VRAM)
   - Installation de Python 3.11 (ou version supérieure disponible) + virtualenv
   - Installation des dépendances backend (`requirements.txt`) et IA avancées (`requirements-ml.txt` : diffusers, transformers, xFormers, etc.)
   - Installation des dépendances frontend (`npm install`)
   - Téléchargement automatique des modèles SDXL et LoRA via `scripts/setup-models.py`
   - Génération des scripts `start-backend.sh`, `start-frontend.sh` et `start-seidra.sh`

3. **Installation automatisée sous Windows**
   ```powershell
   cd SEIDRA-Ultimate
   install-windows.bat
   ```
   Le script Windows vérifie l'exécution en administrateur, installe Python 3.11.8 (ou une version plus récente compatible), Node.js 18, Redis pour Windows, toutes les dépendances backend (`requirements.txt`) **et** la pile IA avancée (`requirements-ml.txt` : torch CUDA 12.1, diffusers, transformers, xFormers, etc.), puis exécute `scripts/setup-models.py` pour télécharger SDXL et les LoRA. Des scripts `start-backend.bat`, `start-frontend.bat` et `start-seidra.bat` sont générés automatiquement.

4. **Variables d'environnement critiques**
- `SEIDRA_DEFAULT_USER_PASSWORD` (obligatoire) : définissez une phrase de passe d'au moins 12 caractères pour le compte d'administration créé automatiquement. La valeur est hachée au démarrage via `get_password_hash`. Si la variable est absente, le compte est créé mais désactivé ; si une valeur faible ou issue de la liste de blocage (`demo`, `password`, `changeme`) est détectée, l'initialisation échoue.
- `SEIDRA_DEFAULT_USER_ROTATION_DAYS` (optionnel, défaut : 90) : nombre de jours entre deux rotations recommandées du compte démo. Positionnez la valeur à `0` pour désactiver l'alerte.
- `SECRET_KEY` : clé JWT utilisée pour signer les tokens (par défaut `seidra-secret-key-change-in-production`).

### Rotation du mot de passe par défaut

- Lors d'une nouvelle installation, définissez systématiquement `SEIDRA_DEFAULT_USER_PASSWORD` dans votre `.env` ou votre service `systemd` avant le premier lancement.
- Lorsque l'alerte « Rotation du compte démo requise » apparaît dans les notifications (ou de manière proactive selon votre politique), exécutez `make rotate-demo-user`. Le script `scripts/rotate-default-user.py` génère un mot de passe robuste, met à jour le hachage dans la base et affiche le secret en clair une seule fois.
- Une fois le secret stocké en lieu sûr, mettez à jour `SEIDRA_DEFAULT_USER_PASSWORD` dans vos environnements (fichiers `.env`, variables système, gestionnaire de secrets) puis redémarrez le backend pour aligner la configuration.
- Si vous omettez la variable ou laissez une valeur de test, le backend désactivera automatiquement le compte (il faudra alors définir une valeur forte et relancer le service).

## 5. Téléchargement manuel / reprise des modèles

### 5.1 Installer les dépendances Python requises

Avant d'exécuter `scripts/setup-models.py`, assurez-vous que l'environnement Python actif contient les bibliothèques Hugging Face et PyTorch nécessaires :

```bash
cd backend
source venv/bin/activate
pip install --upgrade huggingface_hub diffusers torch
```

> Adaptez l'installation de `torch` selon votre plateforme (CUDA, ROCm ou CPU) en suivant la [documentation officielle PyTorch](https://pytorch.org/get-started/locally/).

Si le téléchargement automatique échoue (problème réseau ou proxy), vous pouvez relancer :
```bash
cd backend
source venv/bin/activate
python ../scripts/setup-models.py
```
Le script gère la connexion au Hub HuggingFace, la vérification du GPU et le téléchargement de LoRA populaires (anime, photoréaliste, fantasy, cyberpunk).

## 6. Lancement de la plateforme

Une fois l'installation terminée :
```bash
./start-seidra.sh
```
Ce script :
1. Démarre Redis via `systemctl`
2. Lance le backend FastAPI (port 8000)
3. Lance le frontend (port 3000)
4. Ouvre automatiquement l'interface dans votre navigateur (si `xdg-open` est disponible)

Pour un lancement manuel :
```bash
./start-backend.sh
./start-frontend.sh
```

## 7. Authentification et utilisation de l'API

Les routes critiques (génération, jobs, médias, NSFW, personas) sont désormais protégées par JWT.

1. **Créer un token** (exemple avec l'utilisateur système) :
   ```bash
   cd backend
   source venv/bin/activate
   python - <<'PY'
   from datetime import timedelta
   from auth import create_access_token
   token = create_access_token({"sub": "1"}, expires_delta=timedelta(hours=12))
   print(token)
   PY
   ```
   > Remplacez `"1"` par l'identifiant utilisateur réel si nécessaire.

2. **Configurer le frontend** : ajoutez l'entête `Authorization: Bearer <token>` côté client en appelant `api.setToken('<token>')` avant toute requête protégée.

3. **Tester via cURL** :
   ```bash
   curl -H "Authorization: Bearer <token>" http://localhost:8000/api/jobs
   ```

## 8. Maintenance et monitoring

- **Relancer les téléchargements de modèles** : `python scripts/setup-models.py`
- **Mettre à jour les dépendances** :
  ```bash
  cd backend && source venv/bin/activate
  pip install --upgrade -r requirements.txt -r requirements-ml.txt
  cd ../frontend && npm update
  ```
- **Logs backend** : `tail -f backend/logs/seidra.log` (si configuré) ou surveiller la sortie du terminal de `start-backend.sh`.

## 9. Observabilité locale

Pour activer la surveillance complète en développement :

1. **Démarrer la stack**
   ```bash
   make observability-up
   # ou ./scripts/start-monitoring.sh
   ```
2. **Services exposés**
| Service      | URL locale                | Notes |
|--------------|---------------------------|-------|
| Prometheus   | http://localhost:9090     | Scrape des métriques backend, Celery, Tempo |
| Grafana      | http://localhost:3001     | Identifiants fournis via `SEIDRA_GRAFANA_ADMIN_USER` / `SEIDRA_GRAFANA_ADMIN_PASSWORD` |
| Loki         | http://localhost:3100     | API de requête des logs collectés par Promtail |
| Tempo        | http://localhost:3200     | Interface API pour les traces OTLP (ports 4317 gRPC / 4318 HTTP ouverts) |
3. **Dashboards & datasources** : Grafana provisionne automatiquement le tableau de bord « SEIDRA Ultimate - Observabilité » avec les onglets GPU / Jobs / Notifications.
4. **Arrêt**
   ```bash
   make observability-down
   # ou ./scripts/stop-monitoring.sh
   ```

> ⚠️ Les volumes `grafana-data`, `prometheus-data`, `loki-data` et `tempo-data` sont persistants : utilisez `docker compose -f docker-compose.dev.yml down -v` pour les purger.

### Sécuriser les identifiants locaux

Les services embarqués (MinIO, Grafana) ne démarrent plus avec les couples `admin/password`. Définissez des identifiants explicites dans un fichier `.env.dev` chargé par Docker Compose :

```bash
cp .env.example .env.dev  # si vous disposez déjà d'un gabarit
cat <<'EOF' >> .env.dev
SEIDRA_MINIO_ROOT_USER=seidra_minio_local
SEIDRA_MINIO_ROOT_PASSWORD=remplacez-moi-par-un-secret-solide
SEIDRA_GRAFANA_ADMIN_USER=seidra_obs_admin
SEIDRA_GRAFANA_ADMIN_PASSWORD=un-autre-secret-solide
COMFYUI_CLI_ARGS=--cpu
EOF

docker compose --env-file .env.dev up -d minio grafana
```

Adaptez ces variables pour chaque environnement (CI, staging, production) afin d'éviter la réutilisation de secrets.

### Activer le profil GPU pour ComfyUI

La configuration par défaut force ComfyUI à utiliser le CPU (`COMFYUI_CLI_ARGS=--cpu`). Pour valider les optimisations RTX 3090, activez CUDA avec le fichier d'override `docker-compose.gpu.override.yml` :

```bash
export COMFYUI_CLI_ARGS=""  # laisse ComfyUI détecter le GPU
docker compose \
  -f docker-compose.dev.yml \
  -f docker-compose.gpu.override.yml \
  up comfyui
```

Le fichier d'override déclare la réservation GPU (`driver: nvidia`) et expose les variables `NVIDIA_VISIBLE_DEVICES` / `NVIDIA_DRIVER_CAPABILITIES`. Vérifiez que `nvidia-smi` fonctionne sur l'hôte avant de lancer la stack.

## 10. Dépannage rapide

| Problème | Solution |
|----------|----------|
| **CUDA indisponible** | Vérifiez `nvidia-smi`, réinstallez les drivers, ou exécutez en mode CPU (plus lent). |
| **Échec installation xFormers** | Assurez-vous que la version de CUDA correspond (12.1) et que vous avez suffisamment de RAM. |
| **Erreur 401 sur les endpoints** | Vérifiez le token JWT (non expiré, bien signé). |
| **Modèles manquants** | Relancez `python scripts/setup-models.py` après avoir rétabli la connexion internet. |

## 11. Génération vidéo pilotée depuis l'interface

La vue « Create new artwork » comporte désormais un panneau **Bring characters to life** pour lancer des vidéos synchronisées avec un fichier audio.

- **Video prompt** : décrivez la scène et l'émotion à restituer. Le prompt est envoyé tel quel à l'API `/generation/video`.
- **Reference image URL** (facultatif) : indiquez une image d'identité pour stabiliser le personnage généré.
- **Audio track** : chargez un fichier `wav`, `mp3` ou `ogg`. Le fichier est téléversé avec le reste du formulaire en `multipart/form-data`.
- **Duration** : définissez la durée entre 2 et 30 secondes ; la valeur est validée côté frontend avant l'envoi.

Une fois le formulaire soumis, la tâche apparaît dans le tableau des jobs avec le statut **QUEUED** et les sorties vidéo (`.mp4`, `.webm`, etc.) s'affichent directement grâce à un lecteur `<video>` intégré.

---

Vous êtes prêt à invoquer SEIDRA Ultimate ! Pour toute modification avancée (intégration de nouveaux LoRA, tuning des pipelines), référez-vous aux fichiers `backend/ai_models.py` et `scripts/setup-models.py`.

Bonnes créations !
