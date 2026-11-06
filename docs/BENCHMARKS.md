# Mesures

Toutes faites ici, le 2026-11-06, sauf mention contraire.

**Machine :** Ryzen 7 9800X3D, RTX 5070 Ti (non utilisée), Windows 11, sortie Focusrite USB à 48 kHz.
**Logiciel :** Python 3.12.11, torch 2.15.0+cpu, chordotomy 0.3.1, lv-chordia 1.1.0, beat-this 1.1.0.

## Qualité, sur audio annoté

Scores `mir_eval`, pondérés par la durée. **Ces deux jeux ne sont pas des morceaux du commerce** : aucun
n'a été possible sur ce type de musique faute d'annotations libres, et les résultats sur une chanson
produite avec voix peuvent être moins bons.

- **Tiny AAM** : 20 mélanges *artificiels* (instruments échantillonnés), CC BY 4.0, majeur/mineur uniquement.
- **GuitarSet** : 180 prises *réelles* d'accompagnement à la guitare, CC BY 4.0, un seul instrument.

| Jeu | Moteur | root | majmin | sevenths | tetrads | F temps |
|---|---|---|---|---|---|---|
| Tiny AAM | `dsp` (chordotomy) | 0,842 | 0,803 | 0,768 | 0,768 | 0,827 |
| Tiny AAM | `model` (chordotomy seul) | 0,955 | 0,950 | 0,914 | 0,914 | 0,896 |
| Tiny AAM | **`model` dans LocalChords**, grille suivie | n.m. | **0,958** | **0,921** | n.m. | **0,936** |
| GuitarSet | `model` (chordotomy, sa documentation, poids `final0`) | 0,855 | 0,902 | 0,848 | 0,552 | 0,958 |
| GuitarSet | **`model` dans LocalChords**, grille suivie | **0,854** | **0,902** | **0,848** | **0,552** | **0,965** |

Le calcul des deux lignes « LocalChords » diffère un peu : Tiny AAM par `scripts/bench_meter.py` (intervalles
d'annotation par temps, F des temps sur `trim_beats`), GuitarSet par le correcteur de chordotomy
(`scripts/bench_guitarset.py`). Avec le même script, la grille à tempo unique donne 0,954 / 0,917 / 0,887 sur
Tiny AAM : c'est ce chiffre qu'il faut comparer à la ligne « grille suivie ». Beat This! s'est entraîné sur les
prises GuitarSet : sa F des temps y est optimiste. n.m. : non mesuré par ce script.

Sur GuitarSet, la correction `AMLt` recule de 0,978 à 0,955 (la grille suivie casse parfois une prise de jazz
rapide) et `CMLt` progresse de 0,889 à 0,908.

**Non comparés ici :** Chordify (aucune comparaison valide n'a été faite), BTC, ChordMini et crema (la
documentation de chordotomy les donne sous lv-chordia sur ces jeux, non reproduit ici).

## Grille et barres de mesure, Tiny AAM

| Grille | majmin | F temps | Premiers temps justes (70 ms) |
|---|---|---|---|
| Un tempo par fichier (chordotomy) | 0,954 | 0,887 | 0,857 |
| Suivie sous 0,9 d'accord, compte unique | 0,958 | 0,936 | 0,747 |
| **Suivie sous 0,9 d'accord, barres recalées (retenu)** | **0,958** | **0,936** | **0,921** |

La grille a été suivie sur 10 morceaux sur 20. Le seuil de 0,9 et le coût de recalage (6,0) ont été réglés
sur ces 20 morceaux, sans jeu séparé pour les barres : les 0,921 sont donc un peu optimistes. Le seuil a été
contrôlé sur GuitarSet, qui n'a pas servi au réglage : aucune perte d'accords.

Longueur de mesure : 20 sur 20, mais **tous les morceaux sont à 4 temps**. Le 3, 5, 6 et 7 temps ne sont testés
que sur des signaux construits (`tests/test_core.py`). L'indice de confiance vaut 1,0 sur les 20 morceaux : il
n'a pas pu être calibré, et l'interface ne s'en sert que sous 0,25.

## Audio synthétique

Ni musique ni évaluation : un contrôle à réponse connue (`tests/synth.py`, `scripts/bench_synth.py`), sons additifs,
basse et clic à chaque temps. Part du temps où l'accord est le bon. **Exact : avec la qualité.**
**Triade : réduit à majeur/mineur.** Avant l'ajout du suivi du tempo.

| Progression | `dsp` exact | `dsp` triade | `model` exact | `model` triade |
|---|---|---|---|---|
| C Am F G, 100 BPM | 0,979 | 0,979 | 0,997 | 0,997 |
| Dm7 G7 Cmaj7 Am7, 90 BPM | 0,248 | 0,990 | 0,748 | 0,998 |
| Em C G D en 2 temps, 140 BPM | 0,973 | 0,973 | 0,989 | 0,989 |
| Asus4 A B° E7, 110 BPM | 0,743 | 0,990 | 0,498 | 0,747 |

Limites visibles : `dsp` lit presque toutes les septièmes comme des triades ; les deux moteurs ont pris le
`Asus4` pour un `A` et `model` le `B°` pour `Bm`. Sur ce son synthétique en tout cas. Les tests automatisés
vérifient aussi : résultats identiques d'une exécution à l'autre, début silencieux, silence complet (refusé
avec un message), morceau trop court, changement de tempo de 90 à 130 BPM.

## Vitesse et mémoire, sur CPU

Analyse dans un processus neuf comme dans le programme (`scripts/bench_speed.py`), cache numba chaud sauf mention :

| Audio | Moteur | Total | Par minute d'audio | Pic mémoire |
|---|---|---|---|---|
| 2 min 03 | `model`, premier lancement (cache numba froid) | 27,2 s | 13,3 s | 0,97 Go |
| 2 min 03 | `model` | 20,7 s | 10,1 s | 0,90 Go |
| 2 min 03 | `dsp` | 18,0 s | 8,8 s | 0,65 Go |
| 20 min | `model` | 87,2 s | 4,3 s | 4,05 Go |
| 61 min | `model` | 240,6 s | 3,9 s | 11,06 Go |
| 61 min | `dsp` | 191,4 s | 3,1 s | 10,78 Go |

Environ 10 s de chargement, puis 4 s par minute. Dans le programme compilé : 13,5 s pour le morceau de 2 min 03.

Fenêtre visible 0,82 s après le lancement du programme compilé (mesure externe, `scripts/real_launch.ps1`).
Projet rouvert en 0,06 s. Mémoire de l'interface : 219 Mo, morceau de 2 min chargé.

**Sur un PC moins puissant :** non mesuré ; le temps croît avec le CPU, l'interface reste fluide car l'analyse
est dans un autre processus.

## Lecture

| Mesure | Résultat |
|---|---|
| Latence de sortie WASAPI, Focusrite à 48 kHz | 43 ms, déduite de la position affichée |
| Rendu par bloc (23 ms disponibles), à vitesse 1 | moins de 0,01 ms |
| Rendu par bloc avec ralenti ou hauteur | 0,1 ms en moyenne, 8 ms au pire |
| Hauteur à vitesse 0,5 à 1,5 | 440 Hz rendu à ± 3 Hz |
| Boucle | aucun échantillon perdu à la jointure, test à l'échantillon près |
| QMediaPlayer, écarté | 450 à 500 ms pour se stabiliser après un déplacement |

Pas de mesure de synchronisation à l'oreille : le test vérifie que la case allumée suit l'horloge audio, pas ce
qu'entend un musicien.

## Programme compilé

`dist/LocalChords` : 922 Mo, zip 412 Mo. Postes principaux : `torch_cpu.dll` 295 Mo, `llvmlite` 115 Mo (requis par
librosa), poids Beat This! 79 Mo, FFmpeg 64 Mo, Qt 51 Mo, poids lv-chordia 27 Mo.

Scénario complet dans l'exécutable (`--self-test`), chemins accentués et japonais, sur le morceau de 2 min 03 :
démarrage, analyse, lecture sur le vrai périphérique à volume nul, synchronisation, ralenti, boucle, correction,
transposition, trois exports, réouverture sans recalcul. **Tout réussi.** Lancement réel avec une vraie fenêtre, un
fichier en argument, lecture et transposition au clavier réel (`SendKeys`), capture d'écran, fermeture propre (code 0),
transposition retrouvée dans le fichier.

**Non testé dans l'exécutable :** le glisser-déposer à la souris (l'événement est testé dans l'interface hors écran) ;
un PC sans Python ni outils de développement ; un PC sans carte son, sinon par le code d'erreur.
