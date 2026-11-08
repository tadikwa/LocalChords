# État du projet

Mis à jour le 2026-11-08 : v1.4 (Ma bibliothèque) publiée
(<https://github.com/tadikwa/LocalChords/releases/tag/v1.4>), dernière version. Les versions v1.1, v1.2,
v1.2.1, v1.3 et v1.3.1 restent en ligne, inchangées.

## Où on en est

**v1.4 :** la page d'accueil devient une bibliothèque : index SQLite (`catalog.db`) reconstruit à partir des
projets `.lchords`, qui restent la référence et ne sont pas modifiés ; recherche, filtres, tris, favoris,
collections (glisser-déposer, ordre), genres et étiquettes, liste ou cartes ; audio référencé ou conservé
(copie au choix, sans doublon) ; recherche des fichiers déplacés dans un dossier choisi, empreinte vérifiée ;
liens déjà importés rouverts sans téléchargement ; sauvegarde et restauration de la bibliothèque (zip, plan
avant d'écrire, rien d'écrasé sans accord, paroles du catalogue seulement sur demande). Suppressions
séparées, toutes confirmées, vers la Corbeille ; l'audio d'origine n'est jamais supprimé. Migration : dates
d'avant la 1.4 marquées estimées (« ≈ »). Détail dans [TECHNIQUE.md](TECHNIQUE.md#la-bibliothèque-v14),
notes dans [NOTES-v1.4.md](NOTES-v1.4.md), étude d'installateur dans
[INSTALLER-ETUDE.md](INSTALLER-ETUDE.md) (Inno Setup conseillé, rien de construit).
765 tests passent (dont 42 sur l'index et la sauvegarde, et ceux de la page). Mille morceaux synthétiques : la page se rafraîchit en moins d'une
seconde (test). Auto-test avec une étape « bibliothèque ». Captures sur huit morceaux synthétiques inventés
(`scripts/library_screenshots.py`).
Migration vérifiée sur une copie des données réelles de ce PC (3 projets v1.3.1) : deux lancements, 3 morceaux
sans doublon, dates marquées estimées, audio retrouvé, fichiers `.lchords` identiques octet pour octet et
à la même date.
Builds locaux vérifiés : auto-test du dossier et de l'exécutable unique (302 Mo), 18 étapes sur 18,
sortie sans erreur.
Binaires de la CI vérifiés avant publication : empreintes SHA256SUMS, auto-test du zip et de l'exécutable
unique (18 étapes sur 18), FFmpeg LGPL v3 sans x264 ni x265, notices et sources tierces jointes. Après
publication, les quatre fichiers téléchargés sans compte correspondent aux empreintes.

**v1.3.1 :** ligne « Aucune parole disponible » au-dessus de la grille, reconnaissance du morceau par ses
noms (informations musicales du lien, titre de vidéo nettoyé, étiquettes, nom du fichier ; jamais la chaîne
pour l'artiste), recherche LRCLIB automatique seulement avec l'accord donné une fois (titre, artiste, album,
durée), verdict sûr / à choisir / rien, horodatages écartés pour un live ou une reprise. Détail dans
[TECHNIQUE.md](TECHNIQUE.md#identifier-le-morceau-et-proposer-ses-paroles-v131), notes dans
[NOTES-v1.3.1.md](NOTES-v1.3.1.md). 710 tests passent. Auto-test avec une étape « invitation aux paroles ».
Binaires de la CI vérifiés avant publication : empreintes SHA256SUMS, auto-test du zip sans modèle, puis du
zip et de l'exécutable unique avec LRCLIB (20 résultats, verdict « sûr »).
La CI a dû être relancée quatre fois : les téléchargements depuis github.com répondaient 503/504.
`fetch_whisper.py` et `build_av_lgpl.py` réessaient désormais (5 fois, 30 s d'écart) ; ce n'est pas dans le
tag v1.3.1.
L'auto-test de la v1.3.1 fermait la fenêtre rouverte pendant le décodage de l'audio : Python plantait à la
sortie (code 127 pour le dossier), après un rapport complet. Corrigé après le tag : il attend l'audio.

**v1.3 :** paroles du morceau (fichier ou étiquettes, LRCLIB à la demande, transcription locale par
whisper.cpp, ou saisie), quatre vues (`K`), accords posés sur les mots et déplaçables, synchronisation à la
main, export PDF, texte et `.lrc` réservé aux paroles exportables. Détail dans
[TECHNIQUE.md](TECHNIQUE.md#les-paroles-v13), mesures de transcription dans
[BENCHMARKS.md](BENCHMARKS.md#transcription-des-paroles-v13), notes dans [NOTES-v1.3.md](NOTES-v1.3.md).
676 tests passent. Auto-test (`--self-test`) avec une étape « paroles et accords » ; captures sur des paroles écrites pour la
démo (`scripts/screenshot_lyrics.py`).
Builds locaux vérifiés : auto-test sans modèle, puis avec le modèle 190 Mo et la recherche LRCLIB (transcription 10 lignes en 10 s, 20 résultats). Exécutable unique 302 Mo, démarrage 4 s, 606 Mo décompressés ; dossier 606 Mo.
Binaires de la CI vérifiés avant publication : empreintes SHA256SUMS, auto-test du zip sans modèle, puis du zip et de l'exécutable unique avec modèle et LRCLIB ; URL des modèles épinglées (taille et empreinte conformes).

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
| L. v1.3.1 | Morceau reconnu par ses noms, recherche des paroles avec accord, ligne d'invitation au-dessus de la grille |
| M. v1.4 | Bibliothèque : index SQLite, favoris, collections, étiquettes, audio conservé, sauvegarde et restauration |
| G. P2 | Liens, lots, comparaison de moteurs, progressions, transposition de l'audio. Non faits : sections, séparation de sources, GPU, avec leurs raisons dans DECISIONS.md |

## Limites connues

- Paroles transcrites : un brouillon (environ un mot sur trois faux avec le modèle conseillé, sur 12 chansons
  libres) ; pas mesuré sur des morceaux du commerce. Modèles de 190 et 574 Mo à télécharger.
- Accord déplacé à la main : perdu si le lissage ou une correction change le début de son segment.
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

**v1.4 :** revue du diff entier par un agent séparé, 10 constats. Neuf corrigés, avec des tests :
- un projet v1.3 ouvert avant que l'index ne l'ait lu était daté « ajouté aujourd'hui » : sa date de
  création sert, marquée estimée ;
- une date d'ouverture estimée venue d'une sauvegarde devenait réelle à la restauration ;
- une sauvegarde sans les paroles du catalogue réécrivait les projets à la date du jour : ils gardent la leur ;
- un projet illisible partait tel quel dans une telle sauvegarde, paroles du catalogue comprises : il reste
  dehors, et la fin de la sauvegarde le dit ;
- l'estimation de la taille de l'audio attendait un disque débranché à chaque morceau : une fois par disque ;
- un `catalog.json` mal formé dans une sauvegarde faisait planter la restauration : refusé avec un message ;
- un index verrouillé ou occupé était pris pour un index endommagé : il n'est plus touché ;
- le morceau ouvert pouvait être réenregistré par-dessus un projet que la restauration venait d'écrire ;
- la restauration proposait « Annuler » pendant l'écriture : plus de bouton une fois commencée.

Laissé : un index de secours en mémoire (index illisible, cas rare) partage une connexion SQLite entre la
fenêtre et le fil de lecture des projets ; il ne sert qu'à la session en cours.

**v1.3.1 :** revue du diff entier, 6 constats, tous corrigés avec un test : un mot entre crochets
(« [Acoustic] ») pris pour l'identifiant de la vidéo ; l'artiste du titre perdu quand le site donne le
morceau sans artiste ; une recherche abandonnée qui marquait le morceau comme déjà cherché ; le nom du
fichier gardé comme correction de l'utilisateur sans qu'il l'ait modifié ; une réponse en cours gardée après
la désactivation de la recherche automatique ; un artiste contenu dans un nom plus long (« Adele » dans
« Adele Givens ») compté comme le même.

**v1.3 :** revue du diff entier par un agent séparé, 11 constats. Dix corrigés, avec des tests :
- « Enregistrer une copie du projet » emportait les paroles du catalogue : la copie les laisse de côté,
  même gardées comme version précédente ;
- le texte du catalogue pouvait être copié depuis l'aperçu de recherche ou l'éditeur, puis recollé comme
  paroles « à vous » : copie bloquée pour ces paroles, et `exportable` refuse toute source « catalog » ;
- une transcription finie après réouverture du même morceau était perdue : elle va au morceau ouvert ;
- un projet illisible (paroles abîmées, version plus récente) était remplacé par une nouvelle analyse :
  il est d'abord mis de côté (`<empreinte>-<date>.illisible`, signalé dans `log.txt`) ;
- whisper-cli n'ouvrait pas un dossier au nom cyrillique ou chinois : il tourne dans le dossier des modèles
  et ne reçoit que des noms ASCII ;
- des lignes calées dans le désordre recevaient les accords d'une autre ligne : triées par temps ;
- ancres et temps des mots mal formés dans un projet : écartés à la lecture au lieu de planter ;
- supprimer un modèle demande confirmation ;
- les modèles sont téléchargés depuis une révision fixe de Hugging Face (empreintes vérifiées dessus) ;
- l'album est gardé avec le projet pour la recherche LRCLIB.

Laissé : un accord déplacé à la main tient au début de son segment ; si le lissage (« Accords très
courts ») ou une correction déplace ce début, l'accord revient à sa place calculée. Limite notée plus haut.

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
# avec un modèle dans <données>\models\whisper, l'auto-test transcrit aussi ;
# LOCALCHORDS_SELFTEST_ONLINE=1 ajoute une recherche LRCLIB (seul le nombre de résultats est gardé)
```

Depuis zéro : `scripts/build.ps1`. Données de test : `chordotomy evaluate tiny-aam --engine model` les
télécharge. `work/` contient les essais et n'est pas suivi par Git.

## Prochaines étapes possibles

1. Écouter de vrais morceaux et corriger : c'est ce qui manque aux mesures.
2. Tester sur un PC sans NVIDIA ni outils de développement.
3. Si la taille gêne encore : FFmpeg sans encodeurs vidéo (environ 23 Mo, et plus de GPL).
