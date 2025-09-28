# Documentation API SEIDRA Ultimate

Ce dossier regroupe des fiches opérationnelles pour chaque ressource exposée par la spécification OpenAPI (`openapi/ultimate.json`). Chaque fiche contient :

- une commande `curl` prête à l'emploi ;
- un exemple de réponse JSON réaliste ;
- les cas d'erreur les plus fréquents.

## Ressources documentées

- [Racine (`GET /`)](root.md)
- [Santé (`GET /api/health`)](health.md)
- [Politique de throttling (`GET /api/system/throttling`)](throttling.md)

## Générer la version HTML (Redoc)

```bash
make docs-api
```

La commande produit `docs/api/reference.html` à partir de `openapi/ultimate.json` et inclut automatiquement les exemples fournis dans les fiches Markdown. Vous pouvez ensuite publier le fichier généré (CI/CD, artefact) ou l'ouvrir localement dans votre navigateur.

> 💡 Les scripts de tests de charge (`tests/performance/`) réutilisent ces mêmes endpoints pour valider la cohérence des quotas (`X-RateLimit-*`). Pensez à mettre à jour la fiche `throttling.md` lorsque les politiques changent.
