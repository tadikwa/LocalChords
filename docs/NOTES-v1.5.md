# LocalChords v1.5 : interface revue et installateur Windows

## Nouveautés

- **Un installateur Windows** (`LocalChords-Setup-v1.5.exe`), recommandé pour un usage quotidien :
  installation pour votre compte, **sans droits d'administrateur**, dans
  `%LOCALAPPDATA%\Programs\LocalChords` (ou un autre dossier). Entrée dans le menu Démarrer, raccourci de
  bureau au choix, projets `.lchords` ouverts d'un double-clic (au choix), désinstallation depuis
  Paramètres → Applications. Détail dans [INSTALLATEUR.md](INSTALLATEUR.md).
- **Une interface plus calme et plus lisible** : thème sombre chaud, une seule action principale en
  ambre par écran, boutons discrets dans les barres, contrôles segmentés pour les vues et les
  instruments, icônes et compteurs dans la barre latérale de la bibliothèque.
- **Une fenêtre utilisable dès 800 px de large** (environ 1090 px en v1.4) : sur une fenêtre étroite,
  annuler/rétablir, exporter, paroles, tonalité et tempo se replient dans les barres ; les textes et
  les zones cliquables gardent leur taille. Pratique à côté d'une autre fenêtre, ou dans un gestionnaire
  de fenêtres en mosaïque.
- **Diagrammes** : le nom de la position (« barré case 2 »…) passe sous le diagramme au lieu d'être
  coupé.
- **Écran court** (portable à 125 % ou 150 %) : le panneau des accords du bas cède de la hauteur pour que
  la fenêtre tienne à l'écran.
- **Accessibilité** : la grille, le ruban des accords, la liste des morceaux et la boucle ont un nom
  pour les lecteurs d'écran ; l'ordre de tabulation suit l'ordre visuel. Contrastes du texte de 7,5:1 à
  15,9:1.

## Vos données

Aucune donnée n'est modifiée par la v1.5 : mêmes projets, même bibliothèque, mêmes préférences. Vos
données restent dans `%LOCALAPPDATA%\LocalChords`. **L'installateur ne les modifie et ne les supprime
jamais**, ni à l'installation, ni à la mise à jour, ni à la désinstallation ; pour les supprimer vous-même,
voir [INSTALLATEUR.md](INSTALLATEUR.md#désinstaller). Le mode portable (`LocalChords.portable` à côté du
programme) fonctionne comme avant ; l'installateur refuse un dossier portable.

## Toujours vrai

Tout reste sur votre PC. La reconnaissance des accords, la synchronisation, la lecture, la
transcription et les formats de fichiers sont inchangés. Aucun service, aucune tâche planifiée, aucune
télémétrie, aucune mise à jour automatique.

## Fichiers

- `LocalChords-Setup-v1.5.exe` : installateur (recommandé).
- `LocalChords-v1.5-portable.exe` : exécutable unique, sans installation.
- `LocalChords-v1.5-windows-x64.zip` : dossier, sans installation, démarrage immédiat.
- `LocalChords-v1.5-sources-tierces.zip`, `SHA256SUMS.txt` : sources des composants tiers (FFmpeg LGPL)
  et empreintes.

Programmes non signés : SmartScreen peut demander « Informations complémentaires », puis « Exécuter
quand même ». Vérifiez l'empreinte avec `Get-FileHash` et `SHA256SUMS.txt`.
