# LocalChords v1.6 : studio d'accompagnement

## Nouveautés

- **Mixage des instruments.** Le bouton **Mixage** (ou `M`) de l'écran du morceau sépare, à votre
  demande, le morceau en pistes : **Karaoké** (voix, instrumental) ou **Musicien** (voix, batterie,
  basse, autres). Ensuite, chaque piste a son curseur (de silence complet à +5 dB), son niveau en dB, **M**
  pour la couper et **S** pour l'écouter seule. Chanter sans la voix, jouer la basse à la place de la
  basse, travailler avec moins de batterie : le changement s'entend aussitôt, sans clic, pendant la
  lecture.
- **Toujours synchronisé.** Le mix passe par le même lecteur : grille, paroles, diagrammes, boucles A/B,
  vitesse, transposition et volume général fonctionnent comme avant, à l'échantillon près.
- **Original / Mix personnalisé** d'un clic (ou `Maj + M`), et des préréglages : Karaoké (sans voix), Voix
  seule, Sans basse, Sans batterie, Personnalisé.
- **Retrouvé à la réouverture.** Les pistes sont gardées sur le disque, sans perte (FLAC) ; votre réglage
  est gardé avec le morceau. Rouvrir un morceau ne relance jamais la séparation.
- **Exporter le mix** en FLAC ou WAV, sans perte (menu ⋯ du panneau).
- **Pistes séparées et modèle** (menu ☰ ou ⋯ du panneau) : place prise, dossier, empreinte du modèle ;
  suppression des pistes d'un morceau, de toutes les pistes ou du modèle, toujours après confirmation. Le
  morceau, ses accords, ses paroles, vos favoris et vos collections ne sont jamais touchés.

## La séparation

- **Sur votre PC.** Rien n'est envoyé nulle part. Le modèle est **Demucs v4 « htdemucs »** de Meta (licence
  MIT), choisi après comparaison avec ses variantes et avec UVR MDX-Net : mesures dans
  [SEPARATION.md](SEPARATION.md). Il est téléchargé **une seule fois**, à la première séparation (174 Mo,
  taille et SHA-256 vérifiées), et peut être supprimé.
- **Jamais automatique** : rien n'est séparé à l'import ni à l'ouverture d'un morceau.
- **Durée** : environ un cinquième de la durée du morceau sur un processeur récent à 8 cœurs (30 s pour
  une chanson de 2 min 30), plus sur une machine modeste. Elle tourne en arrière-plan, en priorité basse :
  le programme reste utilisable, **Annuler** arrête tout. La durée estimée s'affiche dès qu'elle a été
  mesurée sur votre PC.
- **Mémoire** : environ 3 Go pendant la séparation. **Place** : 10 à 20 Mo par minute de morceau en mode
  Musicien, annoncée avant de commencer ; la séparation est refusée s'il n'y a pas assez de place, et le
  panneau prévient si les données sont sur une clé USB.
- **Processeur seulement.** Aucune carte graphique n'est utilisée : DirectML donne des résultats faux avec
  ce modèle, et CUDA demanderait 1,34 Go de bibliothèques NVIDIA en plus. Le programme reste sans PyTorch
  ni CUDA ; sa taille ne change presque pas.
- **Jamais parfaite** : un peu de chaque instrument reste audible dans les autres pistes. Guitare, piano
  et claviers restent ensemble dans « Autres » ; pas de mode 6 pistes, jugé pas assez fiable.

## Passer à la v1.6

- **Depuis la v1.5.1** : LocalChords vous la propose si vous avez permis la vérification des mises à jour,
  ou menu ⋯ → **Rechercher des mises à jour…**.
- **Depuis une version plus ancienne** : téléchargez-la une fois à la main ci-dessous (l'installateur
  remplace l'ancienne version au même endroit).

## Vos données

Aucune donnée existante n'est modifiée : mêmes projets, paroles, bibliothèque et préférences, dans
`%LOCALAPPDATA%\LocalChords` (ou `Data` en mode portable). La v1.6 y ajoute seulement, si vous séparez un
morceau, `models\separation` (le modèle) et `stems` (les pistes), et un réglage `mixer` dans le projet du
morceau. Une version plus ancienne rouvre ces projets en ignorant ce réglage.

## Toujours vrai

Tout reste sur votre PC. Aucun compte, aucune télémétrie. Le seul nouveau téléchargement est celui du
modèle de séparation, quand vous lancez votre première séparation. Reconnaissance des accords,
synchronisation, transcription et formats de fichiers inchangés.

## Fichiers

- `LocalChords-Setup-v1.6.exe` : installateur (recommandé).
- `LocalChords-v1.6-portable.exe` : exécutable unique, sans installation.
- `LocalChords-v1.6-windows-x64.zip` : dossier, sans installation, démarrage immédiat.
- `LocalChords-v1.6-sources-tierces.zip`, `SHA256SUMS.txt` : sources des composants tiers (FFmpeg LGPL)
  et empreintes.
- `htdemucs.onnx` : le modèle de séparation, téléchargé par le programme lui-même ; inutile de le prendre.

Programmes non signés : SmartScreen peut demander « Informations complémentaires », puis « Exécuter
quand même ». Vérifiez l'empreinte avec `Get-FileHash` et `SHA256SUMS.txt`.
