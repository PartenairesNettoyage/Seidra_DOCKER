# Studio vidéo – Workflow proxy & waveform

Cette page décrit le fonctionnement du studio vidéo côté frontend, suite à l’ajout des rendus proxy et des waveforms distantes.

## Vue d’ensemble

1. **Upload d’assets** : l’API `/api/media/video-assets` stocke les fichiers dans `media/video_assets/` et renvoie l’identifiant interne (`asset_id`). Les assets audio sont initialisés avec `waveformStatus = idle`.
2. **Waveforms audio** : lors de la visualisation, le store `useVideoStudioStore` appelle `GET /api/media/video-assets/{asset_id}/waveform`.
   - Si la waveform existe déjà (`media/waveforms/{asset_id}.json`), elle est renvoyée immédiatement avec `status=ready`.
   - Sinon, le backend déclenche un calcul asynchrone via Celery (`workers.video_worker.generate_asset_waveform`) ou une tâche locale. La réponse indique `status=processing` et le frontend reste en attente.
   - En cas d’échec, `status=failed` est renvoyé et un fallback local peut être déclenché côté navigateur.
3. **Timeline & proxy** : la sauvegarde `POST /api/generate/video/timeline` persiste la timeline et son `proxy_preview` courant. Lorsque l’utilisateur demande une prévisualisation :
   - Le store appelle `POST /api/generate/video/timeline/{timeline_id}/proxy`.
   - Si un proxy est déjà prêt et mis en cache, le store renvoie immédiatement l’URL sans rappeler l’API.
   - Sinon, un job `video_proxy` est créé. Celery (`generate_timeline_proxy_task`) ou la boucle locale génère un WebM basse résolution dans `media/video_proxies/`.
4. **Consultation** : `GET /api/generate/video/timeline/{timeline_id}/proxy` permet de rafraîchir l’état (`processing`, `ready`, `failed`). La réponse fournit l’URL publique (`/media/video_proxies/<timeline>.webm`) une fois le fichier disponible.

## Comportement frontend

- Les waveforms sont désormais chargées de manière paresseuse, sans simulation client : la timeline affiche l’état `loading` tant que la série de points n’est pas reçue.
- Les proxys sont mis en cache dans le store. `requestProxyPreview({ force: true })` permet de relancer manuellement un rendu si nécessaire.
- `frame-preview.tsx` affiche des messages clairs pour les états `loading`, `processing`, `error` et conserve l’URL existante lorsque le proxy est prêt.

## Tests

- **Vitest** : `frontend/src/components/video-studio/__tests__/store.test.ts` couvre la récupération des waveforms, le cache proxy et le forçage d’un nouveau rendu.
- **Playwright** : un scénario `frontend/tests/e2e/video-studio-proxy.spec.ts` peut simuler l’affichage du proxy en interceptant les appels API.

## Répertoires media

- `media/video_assets/` : fichiers originaux uploadés.
- `media/waveforms/` : JSON de waveforms (librosa).
- `media/video_proxies/` : prévisualisations WebM/gif générées via FFmpeg.
