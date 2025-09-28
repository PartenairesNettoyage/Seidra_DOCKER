# Limitations de débit API

La plateforme SEIDRA Ultimate utilise désormais [`fastapi-limiter`](https://github.com/long2ice/fastapi-limiter)
pour contrôler le débit des requêtes HTTP. Un même appel applique deux politiques complémentaires :

- **Quota global** : limite les requêtes provenant d'une même adresse IP.
- **Quota utilisateur** : limite les requêtes effectuées par un même utilisateur authentifié.

Les deux quotas sont évalués simultanément. Le premier à atteindre la limite déclenche une réponse
`429 Too Many Requests` avec un en-tête `Retry-After` indiquant le délai de réessai.

## Paramètres de configuration

Les paramètres sont centralisés dans `core.config.Settings`. Chaque politique accepte une
valeur de quota et une fenêtre temporelle pour les volets global et utilisateur.

| Composant | Quota global (défaut) | Quota utilisateur (défaut) | Variables d’environnement |
|-----------|----------------------|----------------------------|---------------------------|
| Politique par défaut | 240 requêtes / 1 minute | 120 requêtes / 1 minute | `SEIDRA_RATE_LIMIT_DEFAULT__GLOBAL_QUOTA`, `SEIDRA_RATE_LIMIT_DEFAULT__GLOBAL_WINDOW`, `SEIDRA_RATE_LIMIT_DEFAULT__USER_QUOTA`, `SEIDRA_RATE_LIMIT_DEFAULT__USER_WINDOW` |
| Génération (`/api/generate`) | 60 requêtes / 1 minute | 12 requêtes / 1 minute | `SEIDRA_RATE_LIMIT_GENERATION__GLOBAL_QUOTA`, `SEIDRA_RATE_LIMIT_GENERATION__GLOBAL_WINDOW`, `SEIDRA_RATE_LIMIT_GENERATION__USER_QUOTA`, `SEIDRA_RATE_LIMIT_GENERATION__USER_WINDOW` |
| Média (`/api/media`) | 180 requêtes / 5 minutes | 90 requêtes / 5 minutes | `SEIDRA_RATE_LIMIT_MEDIA__GLOBAL_QUOTA`, `SEIDRA_RATE_LIMIT_MEDIA__GLOBAL_WINDOW`, `SEIDRA_RATE_LIMIT_MEDIA__USER_QUOTA`, `SEIDRA_RATE_LIMIT_MEDIA__USER_WINDOW` |
| Authentification (`/api/auth`) | 50 requêtes / 5 minutes | 10 requêtes / 5 minutes | `SEIDRA_RATE_LIMIT_AUTH__GLOBAL_QUOTA`, `SEIDRA_RATE_LIMIT_AUTH__GLOBAL_WINDOW`, `SEIDRA_RATE_LIMIT_AUTH__USER_QUOTA`, `SEIDRA_RATE_LIMIT_AUTH__USER_WINDOW` |

Le middleware `RateLimitQuotaMiddleware` ajoute un en-tête `X-RateLimit-Policy` précisant la
politique active sur l’URL appelée. Les valeurs affichées reflètent automatiquement les
overrides fournis par l’environnement.

## Backend Redis

Le limiteur partage une connexion Redis initialisée pendant le cycle de vie de l’application.
Les paramètres suivants permettent d’ajuster la connexion :

- `SEIDRA_RATE_LIMIT_REDIS_URL` : URL du serveur Redis dédié au rate limiting
  (par défaut `redis://localhost:6379/3`).
- `SEIDRA_RATE_LIMIT_REDIS_PREFIX` : préfixe des clés Redis utilisées par `fastapi-limiter`
  (par défaut `seidra-rate-limit`).

En cas d’échec de connexion au démarrage, les contrôles de débit sont automatiquement
désactivés pour éviter de bloquer l’API, et un avertissement est affiché dans les journaux.
Une reconnexion réussie lors du prochain démarrage réactive immédiatement la fonctionnalité.

## Tests

Le fichier `backend/tests/api/test_rate_limiting.py` contient des tests d’intégration couvrant
le dépassement de quota et la remise à zéro automatique après expiration de la fenêtre de temps.
Un stub Redis en mémoire est injecté dans `fastapi-limiter` afin de conserver des tests rapides
et déterministes.

