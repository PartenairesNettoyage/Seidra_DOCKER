# Guide d’onboarding – Studio vidéo

Le studio vidéo de SEIDRA Ultimate combine une timeline multi-pistes, une gestion d’assets centralisée et des rendus proxy rapides pour itérer sans attendre la fin d’un export haute résolution. Cette page résume les pratiques recommandées pour une prise en main optimale.

## Parcours recommandé

1. **Importer ses médias**
   - Glissez-déposez directement vos fichiers dans le panneau « Assets » ou utilisez la touche `Entrée` lorsque la zone est focalisée pour ouvrir l’explorateur.
   - Les fichiers audio déclenchent automatiquement un calcul de waveform. Celle-ci peut provenir de l’API (`/media/video-assets/:id/waveform`) ou être générée côté client à partir du flux audio.
2. **Assembler la timeline**
   - Chaque clip est focusable : utilisez `←` et `→` pour déplacer le clip par pas de 0,5 s et `Suppr` pour le retirer.
   - Les pistes disposent d’une annonce ARIA et d’un retour visuel renforcé pour la navigation clavier.
3. **Prévisualiser grâce au proxy**
   - Le bouton « Générer un proxy » appelle l’API `/generate/video/timeline/:id/proxy` et actualise automatiquement l’état de la prévisualisation.
   - Le proxy basse résolution est lu directement dans le composant de prévisualisation et reste accessible via un lien « Ouvrir le proxy ».
4. **Lancer le rendu final**
   - Une fois satisfait du montage proxy, la commande « Lancer un rendu » déclenche le pipeline haute qualité. Les jobs restent visibles dans le panneau de suivi.

## Accessibilité & bonnes pratiques

- Tous les boutons critiques disposent d’intitulés explicites et d’un retour `aria-live`.
- Les statuts des jobs, proxies et waveforms sont annoncés vocalement pour un lecteur d’écran.
- Les contrastes ont été renforcés (jaune/pourpre) pour répondre aux exigences WCAG AA sur fond sombre.

## Résolution des incidents courants

| Symptôme | Diagnostic | Solution |
| --- | --- | --- |
| Waveform absente | Endpoint waveform indisponible | Un recalcul local est tenté automatiquement depuis l’URL de téléchargement. Vérifiez l’accessibilité du fichier.
| Proxy bloqué en « préparation » | Timeline non sauvegardée ou job en échec | Sauvegardez la timeline, puis relancez le proxy. Consultez l’historique des jobs pour récupérer le message d’erreur détaillé.
| Clip impossible à déplacer au clavier | Focus perdu sur la timeline | Sélectionnez le clip avec la souris ou la touche `Tab`, puis utilisez les flèches.

Pour une compréhension exhaustive de l’ergonomie, se référer également à la page `/studio/video` qui introduit le workflow directement dans l’application.
