# LocalChords v1.5.1 : paroles animées et mises à jour assistées

## Nouveautés

- **Paroles animées.** La ligne chantée passe au premier plan en douceur, ses voisines s'estompent. Quand
  les paroles donnent l'heure de chaque mot (fichier `.lrc` enrichi, transcription par l'IA), les mots
  s'éclairent un à un pendant qu'ils sont chantés. Avec l'heure de chaque ligne seulement, la ligne
  s'allume ; des paroles sans heures restent fixes. Toujours à l'heure de la lecture : pause, saut,
  boucle, vitesse, transposition et décalage. Les accords ne bougent pas, et rien n'empêche de glisser un
  accord, de modifier le texte ou de faire défiler la page.
- **Animation des paroles** (Paroles → ⋯) : Animée, Simple (la surbrillance de la v1.5) ou Désactivée. Le
  choix est retenu ; si Windows est réglé pour réduire les animations, LocalChords démarre en Simple.
- **Mises à jour assistées.** Au premier lancement, LocalChords vous demande s'il peut vérifier au
  démarrage qu'une nouvelle version est publiée (une requête anonyme à GitHub, au plus une fois par
  jour). Une nouvelle version s'annonce dans un bandeau discret : Nouveautés, Télécharger, Plus tard,
  Ignorer cette version. Le fichier est gardé seulement si sa taille et son empreinte SHA-256 sont celles
  publiées, et **rien ne s'installe ni ne se lance sans votre confirmation**. Le menu ⋯ permet de changer
  d'avis et de **Rechercher des mises à jour** à tout moment. Détail et sécurité :
  [MISES-A-JOUR.md](MISES-A-JOUR.md).
- **Paroles** : une ligne chantée plusieurs fois (`[00:10][00:30]` dans un `.lrc`) éclaire ses mots à
  chaque passage.

## Passer de la v1.5 à la v1.5.1

La v1.5 ne sait pas encore se mettre à jour : téléchargez la v1.5.1 **une fois à la main** ci-dessous.

- **Installateur** : lancez `LocalChords-Setup-v1.5.1.exe` ; il remplace la v1.5 au même endroit
  (LocalChords ouvert est fermé proprement).
- **Exécutable unique** : posez `LocalChords-v1.5.1-portable.exe` à côté de l'ancien (et de
  `LocalChords.portable` et `Data` si vous les utilisez), puis supprimez l'ancien quand tout va bien.
- **Zip** : décompressez dans un nouveau dossier ; en mode portable, copiez-y `LocalChords.portable` et
  `Data`.

Les versions suivantes vous seront proposées depuis le programme, si vous l'avez permis.

## Vos données

Aucune donnée n'est modifiée : mêmes projets, mêmes paroles corrigées, même bibliothèque, mêmes
préférences, dans `%LOCALAPPDATA%\LocalChords` (ou `Data` en mode portable). La mise à jour ne copie, ne
déplace ni ne supprime jamais le dossier `Data`.

## Toujours vrai

Tout reste sur votre PC. Aucun compte, aucune télémétrie, aucun service ni aucune tâche planifiée : la
seule nouveauté réseau est la vérification des mises à jour, si vous l'acceptez, et le téléchargement que
vous demandez. Reconnaissance des accords, synchronisation, lecture, transcription et formats de
fichiers inchangés.

## Fichiers

- `LocalChords-Setup-v1.5.1.exe` : installateur (recommandé).
- `LocalChords-v1.5.1-portable.exe` : exécutable unique, sans installation.
- `LocalChords-v1.5.1-windows-x64.zip` : dossier, sans installation, démarrage immédiat.
- `LocalChords-v1.5.1-sources-tierces.zip`, `SHA256SUMS.txt` : sources des composants tiers (FFmpeg LGPL)
  et empreintes.

Programmes non signés : SmartScreen peut demander « Informations complémentaires », puis « Exécuter
quand même ». Vérifiez l'empreinte avec `Get-FileHash` et `SHA256SUMS.txt`.
