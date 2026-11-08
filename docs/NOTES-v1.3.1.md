# LocalChords v1.3.1 : les paroles trouvées pour vous

## Nouveautés

- **Une ligne discrète au-dessus de la grille** quand un morceau n'a pas de paroles (vue Grille et
  paroles) : **Aucune parole disponible — Rechercher les paroles · Transcrire avec l'IA · Importer**. La
  grille garde sa place. La croix masque la ligne pour ce morceau ; elle disparaît dès que les paroles sont
  là. Les vues Paroles et Paroles et accords proposent les mêmes choix, en plus grand.
- **Le morceau est reconnu par ce qu'il dit de lui-même**, sans rien écouter :
  - pour un lien, les informations musicales du site (titre, artiste, album, durée), sinon le titre de la
    vidéo nettoyé : « Artiste - Titre (Official Video) » donne l'artiste et le titre, sans l'identifiant de la
    vidéo ;
  - pour un fichier, ses étiquettes (titre, artiste, album), puis son nom ;
  - le nom de la chaîne n'est jamais pris pour l'artiste, et ce qui reste deviné n'est pas présenté comme sûr.
- **Recherche automatique des paroles, si vous l'acceptez** : la première fois, LocalChords vous le demande.
  La réponse est gardée et se change dans **Menu → Rechercher automatiquement les paroles des morceaux**. La
  recherche se fait en arrière-plan, sans bloquer la fenêtre, et seulement pour un morceau sans paroles dont
  le titre et l'artiste sont connus.
- **Le bon résultat, ou le choix** :
  - une version nettement la bonne (titre, artiste, durée, album) : **Paroles trouvées — Utiliser · Voir les
    autres versions · Modifier la recherche** ;
  - plusieurs versions proches : une courte liste pour choisir ;
  - rien de fiable : rien n'est proposé, plutôt que les paroles d'une autre chanson ; la transcription sur
    votre PC passe en premier.
- **Live, reprise, version acoustique** : les horodatages du catalogue, faits pour une autre version, ne
  sont pas repris ; seul le texte l'est. Nouvelle action **Retirer les horodatages (garder le texte)** dans
  le menu de la vue Paroles.
- **Corriger le titre ou l'artiste** dans **Rechercher les paroles** : la correction est gardée avec le
  projet et n'est jamais remplacée par les étiquettes du fichier.

## Ce qui est envoyé

Rien sans votre accord. Ensuite, pour chaque morceau sans paroles : le titre, l'artiste, l'album et la
durée, à LRCLIB (lrclib.net), comme pour une recherche à la main. Jamais l'audio, ni le nom du fichier, ni
l'adresse de la vidéo. Une suggestion ne remplace jamais des paroles déjà là, et les paroles du catalogue
restent affichables mais non exportables, même corrigées.

## Ce qu'il faut savoir

- Une chanson à vous (générée, inédite) n'a pas d'artiste connu : elle n'est jamais cherchée en ligne. La
  ligne propose de la transcrire sur votre PC, ce qui ne démarre jamais tout seul.
- La reconnaissance ne lit que les noms : un titre de vidéo sans tiret ni informations musicales laisse
  l'artiste vide. **Rechercher les paroles** permet alors de le saisir.

## Compatibilité

- Les projets v1.3 s'ouvrent tels quels ; leur titre et leur artiste sont relus comme des étiquettes.
- Aucun nouveau composant ni nouvelle dépendance. Même empaquetage que la v1.3 : FFmpeg LGPL dans des DLL
  séparées, whisper.cpp (MIT), sources et licences tierces jointes.
