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

Environ 10 s de chargement, puis 4 s par minute. Dans le programme compilé : de 12,7 à 19,1 s pour le morceau
de 2 min 03, selon les lancements. Le cache numba reste vide dans le programme compilé : le gain de 6,5 s entre
froid et chaud, mesuré en développement, ne s'y applique pas.

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

## Transposition de l'audio, mesurée (v1.1)

Mesure objective (`scripts/measure_pitch.py`) : le programme compilé joue un la 440 Hz et des gammes
(`--self-test-pitch`), la sortie est enregistrée en boucle par la carte son, puis la fréquence et la durée de
chaque note sont mesurées. Même résultat dans le dossier et dans l'exécutable unique :

| Condition | Mesuré | Attendu |
|---|---|---|
| +12, −12 | 880,00 Hz, 220,00 Hz | 880, 220 |
| +1, −1, +5, −5 | 466,2, 415,31, 587,33, 329,63 Hz | à 0,1 cent près |
| +12 à 50 %, −12 à 150 %, +5 à 75 % | hauteur juste, défilement 0,49, 1,48, 0,74 | 0,5, 1,5, 0,75 |
| Gammes ±12, ±5, +1, avec ralenti | durée des notes à 1 % près, hauteur à 0 cent | |
| Boucle A/B transposée, changement de transposition dans la boucle, son d'origine | jointure juste, notes attendues | |
| « Son d'origine », grille à +5 | 440,2 Hz | 440 |

La hauteur changeait déjà en v1.0 : le défaut signalé venait de l'option, cachée dans un menu et
désactivée par défaut. En v1.1, le bouton « Son transposé / Son d'origine » est à côté de `Transposer`.

## Moteur : ONNX Runtime à la place de torch (v1.1)

Les six réseaux (Beat This!, cinq lv-chordia) sont exportés en ONNX (`scripts/export_onnx.py`) et exécutés par
ONNX Runtime ; le reste de chordotomy (CQT, décodage, harmonie) ne change pas. Comparaison par l'analyse du
programme, torch puis ONNX (`scripts/compare_backends.py`) :

| Jeu | Fichiers | Accords et basses identiques | Temps identiques | Tonalité, mesure | Durée torch → ONNX |
|---|---|---|---|---|---|
| Tiny AAM | 20 | 20 | 20, écart max 0 s | 20, 20 | 198,8 → 184,4 s |
| GuitarSet | 180 | 180 | 180, écart max 0 s | 180, 180 | 338,9 → 326,9 s |
| Morceaux entiers (2 min 03 en deux copies, 10 min 35, 20 min 28) | 4 | 4 | 4, écart max 0 s | 4, 4 | 120,9 → 119,8 s |

Sorties identiques à la précision enregistrée : les scores de qualité ci-dessus restent valables tels quels.
L'export lui-même est contrôlé contre torch sur un enregistrement (log-mel et sorties de chaque réseau). `LOCALCHORDS_BACKEND=torch` revient à torch
en développement.

## Transcription des paroles (v1.3)

`scripts/bench_lyrics.py`, sur 12 chansons de [JamendoLyrics](https://github.com/f90/jamendolyrics)
(licences Creative Commons, 6 en anglais, 6 en français ; rien n'est copié dans le dépôt), whisper.cpp
b5454 sur CPU, ce PC. WER : taux d'erreur sur les mots (0 = parfait). RTF : temps de calcul / durée du
morceau. « Lignes < 1 s » et « mots < 0,5 s » : part des débuts placés à moins de 1 s (lignes) ou 0,5 s
(mots) des annotations.

| Configuration | Langue | WER moyen | WER médian | RTF | RAM max | Lignes < 1 s | Mots < 0,5 s |
|---|---|---|---|---|---|---|---|
| base | en / fr | 1,78 / 0,58 | 0,70 / 0,56 | 0,04 / 0,03 | 459 Mo | 0,59 / 0,64 | 0,40 / 0,49 |
| small-q5_1, réglages par défaut | en / fr | 0,44 / 0,34 | 0,39 / 0,32 | 0,06 / 0,09 | 620 Mo | 0,65 / 0,58 | 0,49 / 0,49 |
| **small-q5_1, repli + `-mc 0`** | en / fr | **0,39 / 0,32** | 0,29 / 0,32 | 0,10 / 0,08 | 553 Mo | **0,87 / 0,87** | 0,67 / 0,66 |
| large-v3-turbo-q5_0, réglages par défaut (3 chansons) | en | 1,37 | 0,97 | 0,59 | 973 Mo | 0,27 | 0,35 |
| **large-v3-turbo-q5_0, repli + `-mc 0`** | en / fr | **0,32 / 0,21** | 0,25 / 0,21 | 0,26 / 0,25 | 868 Mo | 0,70 / 0,51 | 0,69 / 0,50 |

Choix : `small-q5_1` par défaut (le meilleur calage des lignes, 10 fois plus vite que le temps réel),
`large-v3-turbo-q5_0` proposé pour qui veut moins de fautes et accepte d'attendre. Sans contexte d'une
fenêtre à l'autre (`-mc 0`), le modèle ne part plus en boucle sur une phrase, la cause des WER > 1. `base`
écarté. faster-whisper n'a pas pu être mesuré (son PyAV refuse les fichiers du banc) et ajouterait
CTranslate2 et un second décodeur au programme : non retenu. Même avec le meilleur réglage, une ligne sur trois à
cinq est fausse : la transcription reste un brouillon, présenté comme tel.

## Programme compilé, v1.1

| | v1.0 (torch) | v1.1 (ONNX) | Gain |
|---|---|---|---|
| Dossier décompressé | 928 Mo | 510 Mo | −418 Mo |
| Zip du dossier | 398 Mo (418 millions d'octets) | 247 Mo | −151 Mo |
| Exécutable unique | 397 Mo (essai) | 247 Mo | −150 Mo |

Mo au sens de l'Explorateur Windows (1 048 576 octets).

**Version publiée (FFmpeg LGPL).** Pour la diffusion, PyAV est recompilé contre la construction LGPL de
FFmpeg de BtbN (LICENCES-TIERS.md), qui compile en plus de nombreux encodeurs vidéo : FFmpeg passe de
65 à 148 Mo.

| | ONNX, FFmpeg de PyAV (GPL) | ONNX, FFmpeg LGPL (publié) |
|---|---|---|
| Dossier décompressé | 510 Mo | 592 Mo |
| Zip du dossier | 247 Mo | 283 Mo (296 440 243 octets) |
| Exécutable unique | 247 Mo | 283 Mo (296 617 847 octets) |
| Fenêtre visible, exécutable unique | 2,95 à 3,23 s | 3,42 à 3,45 s |
| Fenêtre visible, dossier | 0,67 à 0,71 s | 0,67 à 0,73 s |
| Décompressé dans `%TEMP%`, exécutable unique | 485 Mo | 567 Mo |

Décodage identique entre les deux FFmpeg (écart nul en MP3, WAV, FLAC, ALAC ; au plus 1,2e-7 en AAC, Opus,
WebM), `--self-test` identique (grille et ChordPro octet pour octet) dans les deux formes.

Postes restants du dossier : FFmpeg 148 Mo, llvmlite 115 Mo (numba, requis par librosa), modèles ONNX 89 Mo,
Qt 51 Mo, SciPy 68 Mo, ONNX Runtime 38 Mo, NumPy 21 Mo. Pistes non retenues : un FFmpeg réduit au décodage
audio, compilé ici (environ 140 Mo de moins, non fait) ; compresser par UPX (casse souvent
les DLL Qt et déclenche les antivirus, non essayé). Un exécutable de 100 Mo n'est pas atteignable sans
retirer librosa/numba ou FFmpeg, donc sans réécrire l'analyse.

| Mesure | Dossier | Exécutable unique |
|---|---|---|
| Fenêtre visible après le lancement (`scripts/launch_time.ps1`) | 0,67 à 0,71 s | 2,95 à 3,23 s |
| Analyse du morceau de 2 min 03 (`--self-test`, deux lancements) | 16,6 et 17,5 s | 16,9 et 19,6 s |
| Écrit dans `%TEMP%` à chaque lancement | rien | 484,9 Mo dans `_MEIxxxxxx` |
| Après fermeture normale | | dossier effacé |
| Après arrêt forcé (Gestionnaire des tâches) | | **484,9 Mo restent** dans `%TEMP%` |
| Processus | interface + analyse | lanceur + interface + analyse, un seul dossier décompressé |

Le processus d'analyse de l'exécutable unique réutilise le dossier décompressé par le lanceur : un seul
`_MEI` pendant une analyse, aucun après la fermeture.

Scénario complet (`--self-test`) **réussi dans les deux formes**, moteur `onnx`, depuis des dossiers aux noms
accentués et japonais (`Été 音楽 one`, `Clé USB 音楽`). Mode portable dans l'exécutable unique : `Data` créé à
côté, analyse et réglages dedans. `Data` impossible à écrire : la fenêtre d'avertissement s'affiche, « Quitter »
ferme le programme (code 1) sans rien écrire.

**Non testé en v1.1 :** une vraie clé USB (un dossier local a servi), un support réellement protégé en
écriture (simulé par un fichier `Data`), un PC hors ligne (aucun accès réseau n'est fait hors import de lien,
mais la carte réseau n'a pas été coupée), un autre PC.

## Programme compilé, v1.0 (avec torch)

`dist/LocalChords` : 928 Mo, zip 418 Mo. Postes principaux : `torch_cpu.dll` 295 Mo, `llvmlite` 115 Mo (requis par
librosa), poids Beat This! 79 Mo, FFmpeg 64 Mo, Qt 51 Mo, poids lv-chordia 27 Mo.

Scénario complet dans l'exécutable (`--self-test`), chemins accentués et japonais, sur le morceau de 2 min 03 :
démarrage, analyse, lecture sur le vrai périphérique à volume nul, synchronisation, ralenti, boucle, correction,
transposition, trois exports, réouverture sans recalcul. **Tout réussi.** Lancement réel avec une vraie fenêtre, un
fichier en argument, lecture et transposition au clavier réel (`SendKeys`), capture d'écran, fermeture propre (code 0),
transposition retrouvée dans le fichier.

Clavier réel, focus vérifié avant chaque touche (`scripts/key_check.ps1`) : 3 Ctrl + ↑ envoyés, transposition 3
retrouvée dans le fichier enregistré.

Environnement dépouillé : même scénario réussi avec le dossier du programme renommé en `dist/Été 音楽 test/`, `PATH`
réduit à `System32`, et profil utilisateur vide (donc sans Python, sans cache et sans poids téléchargés).
Import de lien dans l'exécutable : film Big Buck Bunny (CC BY), 634,6 s décodées. Fichier introuvable : message
clair, capture vérifiée.

**Non testé dans l'exécutable :** le glisser-déposer à la souris (l'événement est testé dans l'interface hors écran) ;
un autre PC, notamment sans NVIDIA ; un PC sans carte son, sinon par le code d'erreur.
