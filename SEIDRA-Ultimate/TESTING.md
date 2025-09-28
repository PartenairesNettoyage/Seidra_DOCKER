# Stratégie QA Ultimate

Ce document décrit la stratégie de vérification automatique appliquée à SEIDRA Ultimate ainsi que les seuils de qualité attendus. Toutes les commandes doivent être exécutées depuis la racine du dépôt.

## Pipeline local

1. `make check`
   - Enchaîne le lint (`ruff`, `eslint`), la vérification de type (`mypy`, `tsc`), la compatibilité OpenAPI et les tests unitaires backend/frontend.
   - Doit réussir avant tout envoi de code ou ouverture de Pull Request.
2. `pytest backend/tests --cov=backend`
   - Génère les rapports de couverture XML et HTML dans `reports/qa/backend/`.
   - **Seuil attendu** : 85 % de couverture lignes/fonctions minimum.
3. `npx vitest run --coverage`
   - Produit la couverture frontend (rapport HTML et lcov) dans `reports/qa/frontend/`.
   - **Seuil attendu** : 80 % de couverture statements/branches minimum.
4. `npm run test:e2e`
   - Lance la suite Playwright après avoir installé les navigateurs nécessaires (`playwright install --with-deps`).
   - Vous pouvez également utiliser `make test-e2e` depuis la racine du dépôt.
   - Les rapports HTML sont générés dans `frontend/playwright-report/` et les vidéos/captures dans `frontend/test-results/`.

Les rapports et journaux sont regroupés dans `reports/qa/`.

## Automatisation CI

Le workflow GitHub Actions `ultimate-ci.yml` invoque `scripts/ci-report.sh` qui :

- exécute `make check` pour garantir les gardes-fous lint/type/tests ;
- relance `pytest --cov` et `vitest --coverage` pour produire les rapports dédiés ;
- centralise les journaux dans `reports/qa/logs/` et exporte le dossier pour publication en artifact (`ultimate-qa-reports`).

Un build Next.js dédié (`frontend-build`) est exécuté avant la suite end-to-end (`e2e`) qui lance `npm run test:e2e`. Les artefacts Playwright (`playwright-report`, `test-results`) sont publiés pour consultation hors CI.

### Interprétation des rapports

- `reports/qa/backend/html/index.html` : détails sur la couverture Python, points d'entrée à renforcer si le seuil de 85 % n'est pas atteint.
- `reports/qa/frontend/coverage/index.html` : couverture TypeScript/Vitest, le seuil de 80 % est requis pour statements et branches.
- `reports/qa/logs/*.log` : historique des commandes exécutées (utile pour diagnostiquer un échec CI).
- `frontend/playwright-report/index.html` : rapport HTML Playwright généré lors des tests end-to-end.
- `frontend/test-results/` : artefacts (vidéos, traces, captures) produits lors des tests end-to-end.

Toute baisse sous les seuils doit être justifiée dans la PR avec un plan de remédiation (tests supplémentaires ou refactorisation).

## Tests de charge (Locust)

Les scénarios de charge couvrent les endpoints critiques `/api/generate/single`, `/api/generate/video` et `/api/media`. Ils sont exécutés via une image Docker autonome embarquant Locust.

### Pré-requis d'infrastructure

- **Backend déployé** et accessible publiquement via `SEIDRA_API_URL` (ex : `https://api.seidra.ai`).
- **Jeton JWT utilisateur** avec accès aux endpoints de génération (`SEIDRA_JWT`).
- **Capacités GPU** (RTX 3090 ou équivalent) sur l'environnement cible afin d'absorber les requêtes de génération d'images/vidéos. À défaut, prévoir une instance CPU haute performance et réduire la charge (`USERS`, `SPAWN_RATE`).
- **Docker** installé sur la machine qui lance la campagne de tests.

### Lancement

```bash
SEIDRA_API_URL="https://api.seidra.ai" \
SEIDRA_JWT="<votre_jwt>" \
USERS=10 \
SPAWN_RATE=2 \
RUN_TIME=10m \
make loadtest
```

- `USERS`, `SPAWN_RATE`, `RUN_TIME` et `REPORT_BASENAME` sont optionnels et permettent d'ajuster la pression exercée ou le nommage des rapports.
- Le workflow construit automatiquement l'image `seidra-loadtest`, injecte les variables d'environnement et exécute Locust en mode headless.

### Rapports

- Les exports CSV et le résumé Markdown sont générés dans `reports/perf/` (par défaut `seidra_loadtest_stats.csv`, `seidra_loadtest_failures.csv`, `seidra_loadtest_summary.md`, etc.).
- Le résumé Markdown inclut un tableau synthétique par endpoint ainsi qu'une estimation du débit et du taux d'échec.
