# Plan de tests E2E SEIDRA Ultimate

Ce document décrit la stratégie et les scénarios de tests de bout en bout (E2E) pour garantir qu'une instance SEIDRA Ultimate est opérationnelle sur l'ensemble de la pile (backend, frontend, traitements GPU distants et observabilité).

## Objectifs

- Valider les parcours utilisateurs critiques de la plateforme en environnement quasi-production.
- Couvrir les intégrations externes indispensables (authentification JWT, services ComfyUI/SadTalker, stockage objets).
- Détecter les régressions fonctionnelles majeures avant toute mise en production.

## Pré-requis

- Une installation complète suivant `GETTING_STARTED.md` (backend, frontend, workers et services GPU distants fonctionnels).
- Un compte administrateur actif ou un token JWT valide généré via `scripts/rotate-default-user.py`.
- Des modèles SDXL/LoRA présents sur la machine d'inférence.
- Les jobs de fond Celery et Redis opérationnels.

## Jeux de données

| Jeux | Description | Utilisation |
|------|-------------|-------------|
| `fixtures/users.json` | Comptes de test (admin + créateurs) | Connexion et permissions |
| `fixtures/prompts/sdxl.json` | Prompts de génération d'image | Parcours « Nouvelle création » |
| `fixtures/audio/sample.wav` | Piste audio 10 s | Génération vidéo SadTalker |
| `fixtures/video/reference.png` | Image de référence visage | Génération vidéo SadTalker |

> Adapter les chemins si les fixtures sont stockées dans un bucket S3/MinIO.

## Environnements cibles

- **Staging** (GPU mutualisé) : exécution quotidienne.
- **Pré-production** (GPU dédié) : exécution avant chaque release.
- **CI nocturne** : scénario réduit (login + job image) pour validation rapide.

## Matrice navigateurs

| Navigateurs | Version de référence | Couverture | Particularités |
|-------------|----------------------|------------|----------------|
| Chromium (Desktop Chrome) | Playwright bundle stable | Scénarios complets (drag & drop timeline, rendu, proxy) | Référence fonctionnelle pour le studio vidéo. |
| Firefox (Desktop Firefox) | Playwright bundle stable | Fumigations UI (chargement studio, accès proxy) | Drag & drop de la timeline non supporté côté composant, scénarios avancés en attente. |
| WebKit (Desktop Safari) | Playwright bundle stable | Fumigations UI (chargement studio, accès proxy) | Limitations similaires à Firefox pour le glisser-déposer HTML5. |

## Scénarios obligatoires

| ID | Scénario | Étapes principales | Résultat attendu |
|----|----------|--------------------|------------------|
| E2E-01 | Connexion administrateur | 1. Ouvrir `/login` 2. Saisir identifiants 3. Vérifier redirection dashboard | Dashboard chargé, token stocké, appel `/api/me` 200 |
| E2E-02 | Création d'une image SDXL | 1. Depuis dashboard cliquer « New artwork » 2. Remplir prompt et paramètres 3. Soumettre 4. Attendre statut `COMPLETED` | Fichier image disponible, métriques GPU remontées |
| E2E-03 | Génération vidéo SadTalker | 1. Remplir formulaire vidéo (prompt + audio + référence) 2. Vérifier enfilement job 3. Télécharger vidéo finale | Vidéo lisible (<= 30 s), logs backend sans erreur |
| E2E-04 | Parcours notifications | 1. Ouvrir centre de notifications 2. Marquer comme lue 3. Rafraîchir page | Statut persisté, websocket OK |
| E2E-05 | Export observabilité | 1. Lancer `make observability-up` 2. Générer job 3. Vérifier métriques Prometheus/Grafana | Dashboard « Jobs » montre le run, traces Tempo disponibles |
| E2E-06 | Gestion comptes | 1. Créer utilisateur via UI 2. Lui assigner rôle créateur 3. Connexion avec nouvel utilisateur | Connexion réussie, permissions limitées |
| E2E-07 | Rotation secret démo | 1. Exécuter `make rotate-demo-user` 2. Mettre à jour `.env` 3. Reconnexion | Ancien mot de passe invalide, nouveau accepté |

## Critères d'acceptation

- 100 % des scénarios passent sur les deux matrices GPU/OS certifiées (cf. `GPU_OS_MATRIX.md`).
- Pas d'erreur critique (HTTP 5xx, exceptions non gérées) dans les logs backend durant l'exécution.
- Les métriques clés (latence API P95 < 2s hors génération, taux de réussite jobs > 98 %) sont respectées.

## Automatisation

- Tests UI automatisés via Playwright (`frontend` : `npm run test:e2e`).
- Hooks backend : `pytest backend/tests/e2e` (à créer si besoin).
- Orchestration CI suggérée : GitHub Actions `qa-e2e.yml` avec déclencheur manuel.

## Reporting

- Publier les rapports Playwright (`.zip` + HTML) dans `reports/qa/e2e`.
- Renseigner la checklist de validation dans le ticket de release.
- Archiver les logs backend et exports Grafana dans le dossier de campagne.

## Risques & mitigation

- **Services GPU indisponibles** : prévoir un mock de secours pour ne pas bloquer la campagne.
- **Temps d'exécution > 60 min** : paralléliser les scénarios sur plusieurs workers CI.
- **Données sensibles** : anonymiser les médias uploadés avant partage.

