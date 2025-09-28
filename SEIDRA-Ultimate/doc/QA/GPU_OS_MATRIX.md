# Matrice de qualification GPU / OS

Cette matrice définit les combinaisons GPU / systèmes d'exploitation supportées officiellement pour SEIDRA Ultimate. Les campagnes E2E doivent être exécutées sur au moins une configuration par ligne.

| Famille GPU | OS | Pilotes / Runtime | Particularités | Statut QA |
|-------------|----|-------------------|----------------|-----------|
| NVIDIA RTX 3090 / 4090 | Ubuntu 22.04 LTS | NVIDIA ≥ 535 + CUDA 12.1 | Référence laboratoire, pipeline IA complet | ✅ Certifié
| NVIDIA A5000 | Ubuntu 20.04 LTS | NVIDIA ≥ 535 + CUDA 12.1 | Utiliser `install-linux.sh` avec option `--headless` | ✅ Certifié
| NVIDIA L40S | Rocky Linux 9.2 | NVIDIA ≥ 550 + CUDA 12.3 | Adapter pilotes via repo entreprise, vérifier compat. kernel | 🟡 En cours (tests de stabilité)
| NVIDIA T4 | Debian 12 | NVIDIA ≥ 535 + CUDA 12.1 | Débits réduits : limiter `USERS` dans `make loadtest` | 🟡 En cours (performance)
| NVIDIA RTX 6000 Ada | Windows Server 2022 | NVIDIA ≥ 552 + CUDA 12.3 | Frontend en mode Service, backend WSL2 recommandé | 🔄 En observation (support limité)

## Notes d'exploitation

- Les configurations marquées 🟡/🔄 requièrent la validation explicite du SRE avant mise en production.
- Documenter tout pilote ou correctif kernel additionnel dans le ticket de change.
- Les jobs vidéo SadTalker nécessitent au minimum 16 Go de VRAM ; éviter la T4 pour ce cas d'usage.
- Sur Windows Server, utiliser les scripts `install-windows.bat` et `start-seidra.bat` puis vérifier la présence des services GPU distants.

## Procédure de qualification

1. Provisionner l'environnement cible et appliquer la version candidate de SEIDRA Ultimate.
2. Exécuter le plan de tests `PLAN_TESTS_E2E.md`.
3. Lancer `make loadtest` avec `USERS=25 SPAWN_RATE=5 RUN_TIME=10m`.
4. Publier les rapports (`reports/qa/e2e`, `reports/perf`) dans l'espace de partage QA.
5. Compléter la checklist de qualification et mettre à jour la colonne « Statut QA » si nécessaire.

