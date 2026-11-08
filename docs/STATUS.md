# État du projet

Mis à jour le 2026-11-08 : v1.3 (paroles) terminée sur la branche `feature/v1.3-lyrics`, en cours de
vérification avant publication. La v1.2.1 reste la dernière version publiée
(<https://github.com/tadikwa/LocalChords/releases/tag/v1.2.1>), inchangée.

## Où on en est

**v1.3 :** paroles du morceau (fichier ou étiquettes, LRCLIB à la demande, transcription locale par
whisper.cpp, ou saisie), quatre vues (`K`), accords posés sur les mots et déplaçables, synchronisation à la
main, export PDF, texte et `.lrc` réservé aux paroles exportables. Détail dans
[TECHNIQUE.md](TECHNIQUE.md#les-paroles-v13), mesures de transcription dans
[BENCHMARKS.md](BENCHMARKS.md#transcription-des-paroles-v13), notes dans [NOTES-v1.3.md](NOTES-v1.3.md).
668 tests passent. Auto-test (`--self-test`) avec une étape « paroles et accords » ; captures sur des paroles écrites pour la
démo (`scripts/screenshot_lyrics.py`).

**v1.2.1 :** section « Accords du morceau » sous la grille (tous les accords, ou ceux à venir), une position
par accord partagée par le panneau, les cartes et la fiche, et l'export « Fiche des accords (PDF) ». Détail
dans [TECHNIQUE.md](TECHNIQUE.md#les-accords-du-morceau-et-la-fiche-v121), notes dans
[NOTES-v1.2.1.md](NOTES-v1.2.1.md). 613 tests passent.

**v1.2 :** diagrammes d'accords de guitare et de piano à côté (ou sous) la grille, qui suivent la lecture. Détail
dans [TECHNIQUE.md](TECHNIQUE.md#les-diagrammes-daccords), notes de version dans [NOTES-v1.2.md](NOTES-v1.2.md).
595 tests passent (dont 411 sur les positions, vérifiées note par note). Mêmes livrables que la v1.1, renommés
`v1.2`.

**Livrables v1.1 :** `LocalChords-v1.1-windows-x64.zip` (dossier) et `LocalChords-v1.1-portable.exe`
(exécutable unique), construits et vérifiés sur ce PC : voir [BENCHMARKS.md](BENCHMARKS.md), sections v1.1, et
[RAPPORT-v1.1.md](RAPPORT-v1.1.md). La v1.0 (`dist/LocalChords`, avec torch) reste à sa place.

| Phase | État |
|---|---|
| A. Reconnaissance | Fait : [DECISIONS.md](DECISIONS.md) |
| B. Expérimentation | Fait : chordotomy `model` et `dsp`, Tiny AAM et GuitarSet |
| C. Architecture | Fait : [TECHNIQUE.md](TECHNIQUE.md) |
| D. MVP (P0) | Fait, tests réels |
| E. Application aboutie (P1) | Fait |
| F. Distribution | Fait, exécutable testé ; revue indépendante faite, voir plus bas |
| H. v1.1 | Bouton « Son transposé » visible, ONNX à la place de torch, exécutable unique, mode portable |
| I. v1.2 | Diagrammes de guitare et de piano : suivent la lecture, épinglage au clic, capo, transposition, notation |
| J. v1.2.1 | Accords du morceau (tous / à venir), positions partagées et enregistrées, fiche des accords en PDF |
| K. v1.3 | Paroles : sources locales, LRCLIB, transcription locale ; vues, synchronisation, accords sur les mots, PDF |
| G. P2 | Liens, lots, comparaison de moteurs, progressions, transposition de l'audio. Non faits : sections, séparation de sources, GPU, avec leurs raisons dans DECISIONS.md |

## Limites connues

- Paroles transcrites : un brouillon (environ un mot sur trois faux avec le modèle conseillé, sur 12 chansons
  libres) ; pas mesuré sur des morceaux du commerce. Modèles de 190 et 574 Mo à télécharger.
- Paroles en ligne : LRCLIB seulement, et pas d'export de ces paroles (droits des auteurs).
- Placement des accords : sur le mot le plus proche quand la transcription donne les mots, sinon réparti
  dans la ligne (« approx ») ; à vérifier à l'œil, les accords se déplacent à la main.
- Pas de mesure sur des morceaux du commerce, ni de comparaison avec Chordify.
- Le moteur ne sort pas 9, 11, 13, 6 ni add9 (réduits), et a du mal avec sus et ° sur son synthétique.
- Une seule longueur de mesure par morceau ; hors 4 temps, validé seulement sur signaux construits.
- Glisser-déposer physique jamais joué dans l'exécutable (l'événement est testé hors écran).
- Non testé sur un autre PC.
- **Instabilité non élucidée dans les tests :** 2 exécutions complètes de pytest sur 8 se sont arrêtées vers le
  100e test, sur une erreur interne (`SystemError` dans `compile`, ou pile d'appels fatale) ; les 6 autres sont
  passées, dont les 4 dernières à la suite (165 tests). Pas reproduit en isolant les fichiers. Hypothèse non
  vérifiée : Qt et torch dans le même processus, ce qui n'arrive que sous pytest, le programme les séparant En v1.1, torch n'est plus chargé
  quand les modèles ONNX sont présents : à revoir si l'instabilité disparaît.
  À l'appui : 20 analyses sur 20 sans erreur par le vrai processus d'analyse (`scripts/soak_worker.py`), et
  environ 260 analyses de mesure sans plantage. Si le processus d'analyse tombe, l'interface propose de réessayer.
- Accords du morceau : sur une fenêtre de 1000×760 avec le panneau dessous, la grille descend à sa hauteur
  minimale ; `T` masque la section.
- Diagrammes : accordage standard seulement ; positions jusqu'à la case 15, écart de 4 cases au plus ; doigtés
  calculés, pas relus par un guitariste. La répartition main gauche / main droite au piano n'est qu'une
  suggestion.
- Fenêtre : la barre de lecture large impose environ 1093 px de large (997 px une fois réduite), comme en
  v1.1. Le comportement de GlazeWM en dessous n'a pas été observé en vrai. Le panneau, lui, passe sous la
  grille sous 1280 px et n'impose aucune largeur (testé en imposant la taille, comme un gestionnaire de tuiles).
- L'import YouTube dépend d'un site qui change, et parfois de Node.js ou Deno.
- 592 Mo sur disque (dossier), 283 Mo en exécutable unique ou en zip. Programme non signé : SmartScreen avertit.
- Exécutable unique : 3,4 s de démarrage et 567 Mo décompressés dans `%TEMP%` à chaque lancement, laissés
  sur place si le programme est tué.
- Les réseaux passent par des fonctions privées de chordotomy 0.3.1 (`onnx_engine.py`).
- Diffusion publique : FFmpeg LGPL recompilé, sans libx264 ni libx265 (LICENCES-TIERS.md) ; publié sur
  <https://github.com/tadikwa/LocalChords/releases>.

## Revue indépendante

**v1.2.1 :** revue du diff entier, 5 constats. Deux ont été corrigés avec un test : l'ouverture d'un projet
le réenregistrait, et un en-tête trop haut pouvait couper la première rangée de la fiche. Trois sont laissés
de côté, car mineurs :
- le peintre PDF n'est pas fermé en cas d'exception, comme dans l'export PDF existant ;
- les symboles de la grille sont calculés deux fois à l'export ;
- la palette d'impression permute les couleurs du thème le temps du dessin (raccourci documenté dans le
  code).

**Bouton Lecture / Pause (v1.2.1) : cause extérieure identifiée, pas de défaut LocalChords.**
- Le clic réel dans la fenêtre est testé à 1000×760, 1600×1000 et 5120×1440, section réduite ou agrandie.
- Sur ce PC, les clics perdus venaient de Jot 0.2.2 : une fenêtre invisible, toujours au premier plan, en bas
  au centre de l'écran de 5120×1440, au-dessus du bouton quand LocalChords est dans la tuile de droite de
  GlazeWM.

**v1.2 :** relecture des diagrammes par un agent séparé, qui a recalculé les notes : aucune note fausse.
8 constats, tous traités, avec des tests : la basse d'un renversement nommée autrement dans la grille et dans
le titre (E/A♭ contre E/G♯) ; l'épingle perdue après une correction de la grille (elle tient maintenant à un
instant, pas à un numéro de temps), et sans raccourci clavier (`Maj + D`, flèches) ; avec capo, un titre qui ne
nommait pas ce que montrait le mode Piano ; le message « aucune position » qui comptait mal les cases au-dessus
du capo ; un dessin flou en changeant d'écran (échelle) ; une forme à barré partiel trop tordue ; deux détails
de code.

**v1.0 :** relecture par un agent séparé : 15 constats, tous traités, avec des tests pour les défauts les plus graves. Parmi eux :
une tonalité bémol choisie à la main cassait le projet ; une boucle jusqu'à la fin du morceau plantait le flux
audio ; l'affichage se figeait à chaque tour de boucle ; une comparaison annulée pouvait jeter l'analyse suivante.

## Reprendre

```bash
.venv/Scripts/python.exe -m pytest                       # tout, environ 5 min
.venv/Scripts/python.exe -m pytest -m "not slow"         # sans les moteurs
.venv/Scripts/python.exe -m PyInstaller localchords.spec --noconfirm
dist/LocalChords/LocalChords.exe --self-test <audio> <dossier>   # la preuve : voir report.json
```

Depuis zéro : `scripts/build.ps1`. Données de test : `chordotomy evaluate tiny-aam --engine model` les
télécharge. `work/` contient les essais et n'est pas suivi par Git.

## Prochaines étapes possibles

1. Écouter de vrais morceaux et corriger : c'est ce qui manque aux mesures.
2. Tester sur un PC sans NVIDIA ni outils de développement.
3. Si la taille gêne encore : FFmpeg sans encodeurs vidéo (environ 23 Mo, et plus de GPL).
