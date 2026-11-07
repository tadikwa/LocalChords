# LocalChords v1.2.1 : tous les accords du morceau, et une fiche à imprimer

## Nouveautés

- **Accords du morceau**, une nouvelle section sous la grille :
  - **Tous les accords** : chaque accord une seule fois, dans l'ordre où il arrive, avec sa mesure et son
    diagramme. Leur nombre est indiqué. Un accord renversé (C/E) compte à part, puisque sa position est
    différente.
  - Pas besoin de lancer la lecture : on ouvre un morceau et on travaille les positions avant de jouer avec
    l'enregistrement.
  - **À venir** : l'accord en cours, mis en évidence, puis les suivants, qui avancent avec la lecture.
  - Guitare, piano ou les deux. La section peut être réduite, agrandie ou masquée (touche `T`), et
    l'application se souvient de vos choix.
  - Un clic sur une carte montre l'accord dans le panneau de droite sans déplacer la lecture. Les flèches
    passent d'une carte à l'autre.
- **Une seule position par accord** : la position choisie avec `‹ ›` est la même dans le panneau, dans les
  cartes et sur la fiche. Elle est enregistrée avec le projet et revient à la réouverture.
- **Exporter → Fiche des accords (PDF)** : une fiche A4 vectorielle, prête à imprimer :
  - le titre, la tonalité, le tempo et la mesure ;
  - les accords du morceau avec leurs diagrammes (guitare, piano ou les deux) ;
  - la grille en option, sur une page à part.

  Aucun diagramme n'est coupé entre deux pages, et chaque page est numérotée. La fiche reprend la
  transposition, le capo et les positions affichés dans le programme. Les exports texte, ChordPro et PDF de
  la grille ne changent pas.
- La section suit la transposition, le capo, les corrections, l'annulation, la notation (C D E ou Do ré mi,
  dièses ou bémols) et une nouvelle analyse.

## Corrigé

- Aucun défaut du bouton Lecture / Pause n'a été trouvé dans LocalChords. Le clic passe, testé avec un vrai
  clic dans la fenêtre, à trois tailles et avec la section réduite ou agrandie.
- Sur le PC où le problème a été signalé, les clics perdus venaient d'une autre application : une fenêtre
  invisible, toujours au premier plan, posée en bas au centre de l'écran.

## Compatibilité

- Les projets v1.2 s'ouvrent tels quels. Une v1.2 qui ouvre un projet enregistré par la v1.2.1 ignore les
  positions choisies.
- Aucune dépendance nouvelle. Même empaquetage que la v1.2 : FFmpeg LGPL dans des DLL séparées, et les
  sources et licences tierces jointes à la version.
