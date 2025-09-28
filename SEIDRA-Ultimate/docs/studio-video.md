# Studio vidéo SEIDRA

Le studio vidéo apporte une expérience de montage légère directement dans l’interface SEIDRA. Cette section documente les
concepts principaux, les interactions et le flux de synchronisation avec les jobs vidéo temps réel.

## Architecture générale

- **Module dédié** : le dossier `frontend/src/components/video-studio/` regroupe la timeline, la prévisualisation frame-by-
  frame, la gestion des assets et le panneau des jobs.
- **Store Zustand** : `store.ts` centralise l’état (assets, clips, sélection de frame, jobs synchronisés). Les uploads
  passent par `queueUpload`, qui crée des aperçus locaux (`URL.createObjectURL`) tout en envoyant les fichiers via
  `apiClient.uploadVideoAsset` et en mettant à jour l’état dès réception de la réponse backend.
- **Synchronisation backend** : `VideoStudio` s’appuie sur les actions `refreshJobs`/`syncJobs` du store (requêtes
  `apiClient.listJobs`) et sur le contexte WebSocket. Chaque mise à jour `jobRealtimeUpdate` déclenche `applyRealtimeUpdate`,
  maintenant la progression des rendus et les assets générés en phase avec le backend.

## Parcours utilisateur

1. **Import d’assets** : glisser-déposer ou sélection de fichier depuis l’explorateur. Chaque fichier obtient immédiatement
   un aperçu local via `URL.createObjectURL`, tandis que l’upload réel est géré par `apiClient.uploadVideoAsset`.
2. **Organisation sur la timeline** : les assets sont drag-and-drop sur la piste vidéo ou audio. Les clips se déplacent
   librement et peuvent être ajustés par incréments d’une seconde via les actions `Trim`.
3. **Prévisualisation image par image** : un slider contrôle la tête de lecture, avec affichage du frame courant, du temps
   (secondes) et du timecode formaté.
4. **Suivi des jobs** : la carte `Jobs vidéo` liste les jobs synchronisés (progression, statut, assets générés). L’interface
   signale aussi les erreurs de récupération d’historique pour rester exploitable sans backend.

## Tests end-to-end

Le dossier `frontend/e2e/` contient les tests Playwright. Le fichier `video-studio.spec.ts` vérifie :

- l’accès direct à `/studio/video`,
- l’upload d’un fichier `.mp3`,
- le drag-and-drop sur la piste vidéo,
- la mise à jour du slider de prévisualisation.

Commande de lancement :

```bash
cd frontend
npx playwright test
```

## Points d’extension

- Étendre `queueUpload` pour transférer les uploads vers un stockage définitif (MinIO) et enrichir les métadonnées renvoyées par l’API.
- Alimenter le store avec des durées réelles (métadonnées vidéo/audio) plutôt que des valeurs par défaut.
- Ajouter un export de timeline (JSON) pour partager ou relancer un job vidéo depuis la configuration courante.
