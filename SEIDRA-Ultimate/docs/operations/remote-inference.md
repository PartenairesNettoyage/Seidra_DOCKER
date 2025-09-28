# Opérations – Services d'inférence distants (ComfyUI / SadTalker)

Ce document décrit la nouvelle configuration de résilience appliquée aux appels
ComfyUI et SadTalker ainsi que le comportement de repli local mis en place dans
le `ModelManager`.

## Paramétrage des timeouts et retries

Les paramètres sont exposés via la section `remote_inference` des settings
Pydantic (`backend/core/config.py`). Chaque service dispose de son propre bloc
(`comfyui`, `sadtalker`) avec les champs suivants :

| Variable d'environnement | Description | Valeur par défaut |
|--------------------------|-------------|-------------------|
| `SEIDRA_REMOTE_INFERENCE__COMFYUI__REQUEST_TIMEOUT_SECONDS` | Timeout total appliqué aux requêtes ComfyUI. | `90.0` |
| `SEIDRA_REMOTE_INFERENCE__COMFYUI__CONNECT_TIMEOUT_SECONDS` | Timeout de connexion TCP vers ComfyUI. | `10.0` |
| `SEIDRA_REMOTE_INFERENCE__COMFYUI__READ_TIMEOUT_SECONDS` | Timeout de lecture des réponses ComfyUI. | `90.0` |
| `SEIDRA_REMOTE_INFERENCE__COMFYUI__WRITE_TIMEOUT_SECONDS` | Timeout d'écriture/streaming vers ComfyUI. | `90.0` |
| `SEIDRA_REMOTE_INFERENCE__COMFYUI__MAX_ATTEMPTS` | Nombre maximal de tentatives avant abandon. | `3` |
| `SEIDRA_REMOTE_INFERENCE__COMFYUI__BACKOFF_FACTOR` | Facteur de backoff exponentiel entre les retries. | `1.5` |
| `SEIDRA_REMOTE_INFERENCE__COMFYUI__BACKOFF_MAX_SECONDS` | Délai maximal entre deux tentatives. | `30.0` |
| `SEIDRA_REMOTE_INFERENCE__COMFYUI__QUEUE_MAX_RETRIES` | Nombre de reprises automatiques via la file locale. | `5` |
| `SEIDRA_REMOTE_INFERENCE__COMFYUI__QUEUE_RETRY_DELAY_SECONDS` | Délai entre deux reprises asynchrones. | `15.0` |

Le même jeu de variables est disponible pour SadTalker via le préfixe
`SEIDRA_REMOTE_INFERENCE__SADTALKER__*` (timeouts ajustés à 120 s par défaut).

Ces paramètres peuvent être surchargés dans `.env`, via Vault ou dans les
environnements d'exécution (Docker, Kubernetes…).

## File de reprise locale

Lorsque toutes les tentatives synchrones échouent, le `ModelManager` place la
requête dans une file locale (`asyncio.Queue`). Un worker asynchrone rejoue les
jobs en respectant le backoff défini par `QUEUE_RETRY_DELAY_SECONDS` et limite
le nombre de reprises à `QUEUE_MAX_RETRIES`.

* Les notifications sont publiées via `NotificationService` lors de la mise en
  file, de chaque tentative échouée et quand le job est définitivement abandonné
  ou relancé avec succès.
* Les jobs sont identifiés et journalisés (logger `seidra.model_manager`) afin
  de faciliter le troubleshooting.

> **Remarque** : si `QUEUE_MAX_RETRIES` vaut `0`, aucun fallback asynchrone n'est
> planifié et seule l'alerte d'échec est envoyée.

## Télémetrie et observabilité

Le `TelemetryService` enregistre désormais pour chaque appel distant :

* la durée (`durationSeconds`),
* le nombre de tentatives (`attempts`),
* l'état (succès / échec),
* la taille actuelle de la file de reprise (`queueLength`).

Les métriques sont exposées via Prometheus (`seidra_remote_call_latency_seconds`
et `seidra_remote_call_failure_rate`) et relayées sur le WebSocket système.

Dans les snapshots `/api/system/status`, la section `remoteCalls` récapitule les
statistiques agrégées (taux d'échec, latence moyenne, dernière requête) par
service.

## Bonnes pratiques

1. **Adapter les timeouts** en fonction de la taille des workflows ComfyUI ou
   des vidéos générées via SadTalker.
2. **Superviser les notifications** côté opérations afin de détecter rapidement
   une dégradation prolongée.
3. **Ajuster `QUEUE_MAX_RETRIES`** selon la criticité des jobs : une valeur plus
   faible limite le délai de détection d'incidents permanents.
4. **Surveiller les métriques Prometheus** `seidra_remote_call_*` pour corréler
   les dégradations avec les traces applicatives.
