# LocalChords v1.4 : Ma bibliothèque

## Nouveautés

- **La page d'accueil devient votre bibliothèque musicale** : tous les morceaux analysés, avec leur titre,
  artiste, genre, durée, tonalité, tempo, nombre d'accords, paroles, état de l'audio, et leurs dates
  d'ajout et de dernière ouverture. En liste (colonnes triables) ou en cartes. Double-clic ou Entrée
  ouvre le morceau ; elle reste fluide avec des centaines de morceaux.
- **Recherche instantanée** (Ctrl + F) sur le titre, l'artiste et l'album, sans tenir compte des accents ;
  **filtres** par genre, étiquette et état (avec ou sans paroles, audio introuvable, audio conservé) ;
  **tris** par titre, artiste, date d'ajout, dernière ouverture, année, genre, tonalité ou tempo.
- **Favoris** d'un clic, sur l'étoile de la page du morceau ou dans la bibliothèque. Ils restent.
- **Collections** : créer, renommer, ajouter (menu, ou glisser les morceaux sur la collection), retirer,
  réordonner (Alt + ↑ ↓), supprimer.
  Supprimer une collection ne supprime aucun morceau.
- **Genres et étiquettes** : le genre vient des étiquettes du fichier, se corrige, et « Non renseigné »
  s'affiche quand il n'est pas connu. Des étiquettes libres en plus (« à travailler », « concert »…).
- **Garder une copie de l'audio** (au choix, taille annoncée) : le morceau se joue même si l'original est
  déplacé ou sur un disque débranché. L'original n'est jamais déplacé ni supprimé.
- **Retrouver des fichiers déplacés** dans un dossier que vous choisissez : seul ce dossier est examiné,
  et un fichier n'est accepté que s'il s'agit bien du même enregistrement.
- **Un lien déjà importé** se rouvre aussitôt, sans nouveau téléchargement.
- **Sauvegarder la bibliothèque** dans un seul fichier : projets, corrections, favoris, collections,
  étiquettes, préférences, et l'audio si vous le voulez (taille estimée avant). **Restaurer** montre
  d'abord ce qui va changer, n'écrase rien sans votre accord, ne crée aucun doublon, et met de côté la
  version qu'il ne garde pas.

## Les quatre notions

| Notion | Ce que c'est |
|---|---|
| **Projet sauvegardé** | l'analyse d'un morceau et vos corrections (`.lchords`), enregistrées seules |
| **Audio référencé** | le fichier d'origine, là où il est sur votre PC : LocalChords note seulement son emplacement |
| **Audio conservé** | une copie que LocalChords garde dans son dossier, sur votre demande |
| **Sauvegarde de bibliothèque** | un fichier zip à garder ailleurs, pour tout retrouver sur un autre PC |

## Supprimer, sans mauvaise surprise

Chaque action est séparée et demande confirmation : retirer d'une collection, retirer des favoris,
retirer du catalogue (le projet reste, « Retirés » le rend), supprimer l'analyse, supprimer la copie
conservée. Ce qui est supprimé va à la Corbeille de Windows. **Le fichier audio d'origine n'est jamais
supprimé.** Un disque débranché affiche « Disque absent » et ne supprime rien.

## Vos données existantes

Au premier lancement, la bibliothèque se remplit seule d'après vos analyses, sans les refaire et sans
modifier vos fichiers `.lchords`. Les dates d'ajout et d'ouverture d'avant la v1.4 ne sont pas connues :
elles s'affichent approchées (« ≈ »), d'après les fichiers. L'index est copié chaque jour et se
reconstruit seul s'il est endommagé.

## Toujours vrai

Tout reste sur votre PC : la bibliothèque est un fichier local, rien n'est envoyé. La reconnaissance des
accords, la transcription, les diagrammes et la lecture sont inchangés.

## Fichiers

- `LocalChords-v1.4-portable.exe` : exécutable unique.
- `LocalChords-v1.4-windows-x64.zip` : dossier, démarrage immédiat.
- `SHA256SUMS.txt`, notices et sources des composants tiers (FFmpeg LGPL).

Programme non signé : SmartScreen peut demander « Informations complémentaires », puis « Exécuter quand
même ».
