# API – Limitation de débit

## Limites appliquées

| Domaine | Limite | Fenêtre |
| --- | --- | --- |
| Défaut (toutes routes) | 120 requêtes | 1 minute |
| Authentification (`/api/auth/*`) | 10 requêtes | 5 minutes |
| Génération (`/api/generate/*`) | 12 requêtes | 1 minute |
| Médias (`/api/media/*`) | 90 requêtes | 5 minutes |

Les quotas sont évalués par adresse IP (via `get_remote_address`). Les clients
doivent donc propager correctement l’adresse source (ex. en conservant
`X-Forwarded-For` côté proxy) pour éviter de partager le compteur.

## Comportement en cas de dépassement

- Code HTTP retourné : **429 Too Many Requests**.
- Corps JSON typique :

  ```json
  {
    "detail": "Rate limit exceeded: 12 per 1 minute"
  }
  ```

- En-têtes de réponse exposés par SlowAPI :

  | En-tête | Description |
  | --- | --- |
  | `X-RateLimit-Limit` | Quota applicable à la route courante. |
  | `X-RateLimit-Remaining` | Requêtes restantes avant blocage. |
  | `X-RateLimit-Reset` | Timestamp (Unix) du prochain reset. |
  | `Retry-After` | Délai en secondes avant nouvelle tentative. |

## Recommandations front-end

- Surveiller `status === 429` pour afficher un message contextualisé.
- Exploiter `Retry-After` pour planifier un nouvel essai automatique si
  pertinent.
- Utiliser les en-têtes `X-RateLimit-*` afin d’afficher une jauge ou un badge
  d’usage restant.
- Mutualiser les appels (debounce côté UI) pour économiser les quotas.

## Résilience

En cas d’indisponibilité de Redis, SlowAPI bascule automatiquement sur un
stockage en mémoire locale. Les limites restent actives mais ne sont plus
partagées entre plusieurs instances backend.

