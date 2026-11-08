# LocalChords v1.3 : les paroles, avec les accords au-dessus des mots

## Nouveautés

- **Paroles et accords** : les paroles du morceau, chaque accord posé sur le mot où il tombe. La ligne en
  cours s'allume, la page défile seule et l'accord joué est mis en évidence. Les diagrammes de guitare et de
  piano restent à côté.
- **Quatre vues**, avec le bouton **Paroles** ou la touche `K` : Grille seule, Grille et paroles (la ligne en
  cours et la suivante au-dessus de la grille), Paroles, Paroles et accords.
- **D'où viennent les paroles** (**Obtenir les paroles**) :
  - **de votre ordinateur** : un fichier `.lrc`, `.srt` ou `.txt` du même nom à côté du morceau, ou les
    paroles écrites dans ses étiquettes, trouvés seuls à l'ouverture ; ou un fichier choisi ;
  - **en ligne, à votre demande**, dans la base libre LRCLIB : seuls le titre, l'artiste, l'album et la durée
    sont envoyés, jamais l'audio. Ces paroles s'affichent mais ne s'exportent pas ;
  - **transcrites par l'IA, sur cet ordinateur** : whisper.cpp est livré avec le programme et le modèle se
    télécharge une fois, à votre demande (190 Mo, conseillé, ou 574 Mo, plus précis et plus lent), avec
    vérification de son empreinte. L'audio ne quitte pas le PC. Le résultat est marqué « Brouillon » ;
  - ou **saisies et collées** à la main.
- **Corriger** : modifier le texte, puis **Synchroniser** : `Entrée` cale la ligne choisie sur la lecture.
  Décalage de toutes les paroles par pas de 0,1 s. Un clic sur une ligne lit depuis elle. Le texte d'origine
  et la version précédente restent récupérables.
- **Déplacer un accord** : glissez son nom sur un autre mot. **Remettre tous les accords à leur place** annule
  ces déplacements. Tout est enregistré avec le projet.
- **Taille du texte** réglable (`−` `+` ou `Ctrl` + molette), de 12 à 48 points.
- **Exporter → Paroles et accords (PDF)** : une fiche A4 (portrait ou paysage) avec les accords au-dessus des
  mots et les diagrammes en tête ou en annexe. Aussi : paroles en `.txt` ou `.lrc` synchronisé, et grille avec
  paroles en `.txt`. L'export n'est proposé que pour les paroles que vous avez le droit de copier : les vôtres,
  celles d'un fichier ou des étiquettes, ou une transcription ; jamais celles trouvées en ligne.

## Ce qu'il faut savoir

- La transcription est un brouillon : sur 12 chansons sous licence libre, le modèle conseillé se trompe sur
  environ un mot sur trois, et les débuts de ligne tombent à moins d'une seconde près de 9 fois sur 10.
  Mesures dans `docs/BENCHMARKS.md`.
- Une voix noyée dans la musique, ou une langue peu courante, donne un texte moins juste. Un passage
  instrumental ne produit pas de mots inventés.
- Sans paroles, rien ne change : la grille reste la vue par défaut.

## Compatibilité

- Les projets v1.2.1 s'ouvrent tels quels. Un projet avec des paroles est enregistré au format 2 ; un projet
  sans paroles reste au format 1 et s'ouvre toujours avec les versions précédentes.
- Nouveau composant : whisper.cpp b5454 (licence MIT), dans le dossier `whisper` du programme. Les modèles ne
  sont pas livrés : ils sont téléchargés à la demande depuis Hugging Face (licence MIT). Même empaquetage que
  la v1.2.1 pour le reste : FFmpeg LGPL dans des DLL séparées, sources et licences tierces jointes.
