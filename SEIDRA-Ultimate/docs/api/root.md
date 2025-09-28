# Ressource Racine (`GET /`)

La racine de l'API renvoie un message de statut synthétique qui permet de vérifier rapidement la disponibilité du backend et la version déployée.

## Exemple de requête

```bash
curl -X GET http://localhost:8000/
```

## Exemple de réponse `200 OK`

```json
{
  "message": "SEIDRA API - Build your own myth",
  "version": "1.0.0",
  "status": "mystical"
}
```

## Cas d'erreur possibles

| Code | Description | Exemple de charge utile |
| ---- | ----------- | ----------------------- |
| 503  | Le backend n'a pas fini de démarrer. | `{ "detail": "Service indisponible, réessayez ultérieurement." }` |
| 500  | Une erreur interne empêche le retour du statut. | `{ "detail": "Erreur interne, consultez les logs backend." }` |

> ℹ️ Aucune donnée de requête n'est nécessaire. Un corps JSON vide est ignoré.
