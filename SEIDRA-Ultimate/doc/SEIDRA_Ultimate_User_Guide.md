# Parcours d'onboarding et accessibilité

## Assistant d'onboarding

Un assistant guidé accompagne les nouvelles utilisatrices et les nouveaux utilisateurs lors de leur première visite :

1. **Démarrer vos générations** – découvre la configuration des prompts, le suivi des rendus et la sauvegarde des réglages clés.
2. **Façonner des personas vivants** – explique la création et le partage des fiches personas au sein de l'équipe.
3. **Explorer le studio vidéo** – présente le montage rapide, la synchronisation audio/vidéo et la publication dans la médiathèque.

La progression est enregistrée dans le navigateur via `localStorage` (`seidra_onboarding_progress` pour l'étape courante, `seidra_onboarding_completed` pour l'achèvement). Une fois le parcours terminé ou ignoré via le bouton *Passer*, la fenêtre ne s'affiche plus automatiquement. Pour relancer la découverte, supprimez ces clés depuis les outils de développement du navigateur.

## Accessibilité renforcée

- Le **Header** annonce l'état de la plateforme dans une région `role="status"` en `aria-live="polite"`, garantissant que les lecteurs d'écran reçoivent la mise à jour de connexion.
- Le **Sidebar** est structuré comme une `navigation` verticale avec des commandes annotées (`aria-current`, `aria-expanded`, `aria-controls`). Les flèches du clavier (`↑` `↓`), ainsi que `Home` et `End`, permettent de parcourir les onglets sans souris.
- Les boutons critiques disposent d'états `focus-visible` visibles et d'intitulés explicites même lorsque la barre latérale est réduite.
- Une palette de couleurs optimisée assure un contraste AA sur les éléments interactifs majeurs, notamment les badges d'état, les cartes d'onboarding et les commandes de navigation.

Ces évolutions favorisent une prise en main progressive tout en offrant un accès équitable aux fonctionnalités clés de SEIDRA Ultimate.
