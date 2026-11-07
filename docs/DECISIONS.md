# Décisions

Chaque décision avec ce qui l'a motivée. Les chiffres viennent de [BENCHMARKS.md](BENCHMARKS.md).

## Moteur : chordotomy (lv-chordia + Beat This!), et non un moteur écrit ici

Comparaison à la source, le 2026-11-06 :

| Candidat | Licence code / poids | Vocabulaire | Temps, mesures | Windows x64 sans NVIDIA | Verdict |
|---|---|---|---|---|---|
| [chordotomy](https://github.com/zeikar/chordotomy) 0.3.1 | MIT / MIT | 13 qualités + renversements | Beat This! (temps et mesures dans le modèle, jetées par chordotomy, récupérées ici) | Installé et mesuré ici | **Retenu**, mesures ci-dessous |
| [lv-chordia](https://github.com/openmirlab/lv-chordia) 1.1.0 | MIT / MIT | Grand vocabulaire | Aucun | Wheel `py3-none-any` | Utilisé via chordotomy |
| [BTC](https://github.com/jayg996/BTC-ISMIR19) | MIT / non indiqué à part | 25 ou 170 | Aucun | Pas de paquet ; inactif depuis 2020 | Écarté |
| [Chordino](https://github.com/c4dm/nnls-chroma) | GPL-2.0 | maj, min, 7, dim, aug, renv. (non vérifié) | Aucun | Binaire Vamp ; pas de wheel `vamp` récent | Écarté : GPL et intégration fragile |
| [madmom](https://github.com/CPJKU/madmom) | BSD / modèles CC BY-NC-SA 4.0 | maj/min | Oui | Dernière version PyPI de 2018 ; compilation depuis git | Écarté : données non commerciales, maj/min seuls |
| [chord-engine](https://github.com/Jeremyszs/chord-engine) | README MIT, aucun fichier de licence | BTC | librosa | Service FastAPI, torch requis | Écarté : son propre `eval_result.json` indique 0 accord et 30 BPM sur 10 s |
| [chordflask](https://github.com/bkl2000/chordflask) | MIT, s'appuie sur Vamp | Chordino | QM Vamp | Binaires Linux cités ; Windows non vérifié | Écarté : interface web autour des mêmes moteurs |
| [autochord](https://github.com/cjbayron/autochord) | Apache-2.0 | 25 | Aucun | README : Windows non pris en charge | Écarté |
| [ChordMini](https://github.com/ptnghia-j/ChordMini) | MIT / non vérifié | BTC, 170 | Via son application | README : backend Windows peu fiable | Écarté |

**Expérience :** chordotomy `model` et `dsp` mesurés ici sur Windows, Tiny AAM et GuitarSet. Les scores
de `model` reproduisent ceux de sa documentation, chiffre pour chiffre, sur Tiny AAM. Le neuronal gagne
nettement (majmin 0,950 contre 0,803) pour un temps comparable, donc il n'est pas retenu « parce qu'il est
neuronal » : le DSP coûte presque autant. Le tableau de chordotomy place BTC, ChordMini et crema sous
lv-chordia sur les mêmes données ; **ces trois-là n'ont pas été relancés ici**, c'est leur documentation.
Le code d'interface de chordotomy (visionneuse web) n'est pas utilisé.

Second moteur : le `dsp` de chordotomy, pour le « deuxième avis » : méthode indépendante des réseaux.

## La grille suit le tempo quand il varie (ajout à chordotomy)

chordotomy impose un tempo par fichier. Sur un morceau dont le tempo bouge, la grille dérive et les
barres de mesure tombent à côté. Quand elle s'écarte des temps que Beat This! a lui-même détectés
(F-mesure < 0,9), l'unique appel à son tracker est remplacé par ces temps. Mesuré : majmin 0,954 → 0,958,
F-mesure des temps 0,887 → 0,936 sur Tiny AAM ; aucun recul d'accord sur GuitarSet, écarté du réglage.
Cette approche reste un remplacement ciblé, pas un fork.

## Barres de mesure recalées, pas un compte unique

Un temps manqué décale tout le reste d'un comptage modulo. Un Viterbi sur la position dans la mesure
recale le compte quand l'évidence le justifie. Mesuré : précision des premiers temps 0,747 → 0,921 sur
Tiny AAM avec la grille suivie. Une mesure incomplète en résulte parfois : un vide en fin de mesure, plutôt
qu'un décalage définitif. Une correction manuelle repasse à un compte régulier.

## Lecteur maison plutôt que QMediaPlayer

Mesuré : un déplacement avec QMediaPlayer (Qt 6.12, FFmpeg) met 450 à 500 ms à se stabiliser, trop pour
une boucle A/B. Sa correction de hauteur fonctionne (440,1 Hz à vitesse 0,5). Avec les échantillons en
mémoire et PortAudio : boucle sans trou, déplacement immédiat, position exacte, et tout le rendu testable
sans carte son. Écart assumé : environ 200 lignes à maintenir, et QtMultimedia en moins dans le paquet.

Ralenti : WSOLA, en numpy dans le rappel audio, 0,1 ms par bloc en moyenne pour 23 ms disponibles. Rubber Band sonnerait mieux mais
il est sous GPL. Le ralenti peut produire de légers doublements sur les attaques marquées.

## PySide6 Widgets, grille peinte à la main

Pas de serveur web local, pas de seconde pile technique. Qt est natif, fin et net à 5120 × 1440 ; la grille
peinte ne redessine que les cases qui changent pendant la lecture. Pas de QML : rien ne le demande.

## L'analyse dans un autre processus

Annulation franche, plantage isolé, démarrage de l'interface sans torch (0,4 s mesuré dans le programme
compilé). `multiprocessing` plutôt qu'un exécutable séparé : PyInstaller le gère, sans dépendance en plus.

## PyAV pour décoder, pas FFmpeg en ligne de commande

Tous les formats, chemins Unicode, pas de sous-processus ni de fichier à rendre présent. Licence vérifiée
dans la DLL embarquée : `avcodec_license()` renvoie « LGPL version 3 or later », mais les wheels livrent aussi
libx264 et libx265 (GPL-2.0+), jamais appelés : sans effet pour un usage personnel, à régler avant toute
diffusion (`LICENCES-TIERS.md`).

## GPU : non

Les réseaux n'occupent qu'une part de l'analyse (Beat This! 5 s, lv-chordia 5 s, sur 20 s pour un morceau de
2 min), le reste est du CQT sur CPU avec librosa. chordotomy force le CPU : passer au GPU demanderait de le
modifier, d'embarquer torch CUDA (environ 2,5 Go de plus) pour un gain plafonné à environ un tiers de 20 s.
**Non mesuré directement** : le plafond est calculé d'après les étapes mesurées.

## Poids embarqués plutôt que téléchargés au premier lancement

89 Mo sur 510 (108 Mo sur 900 avec torch) : le programme marche hors ligne dès le départ, sans consentement à demander ni
téléchargement à vérifier. Licences MIT, redistribution permise.

## ONNX Runtime pour exécuter les modèles, sans torch (v1.1)

torch pesait 295 Mo pour faire tourner six petits réseaux. Exportés en ONNX, ils donnent les mêmes accords,
temps, tonalités et mesures sur les 204 fichiers comparés, un peu plus vite, et le dossier passe de 928 à
510 Mo. chordotomy reste le moteur : seuls les appels aux réseaux sont redirigés (`onnx_engine.py`), ce qui
dépend de fonctions privées de chordotomy 0.3.1, version figée dans `requirements-lock.txt`. Les fichiers
`.onnx` sont produits à la construction depuis les poids MIT d'origine, pas suivis par Git.

## Deux formes : dossier et exécutable unique (v1.1)

L'exécutable unique se copie en un fichier, mais se décompresse (485 Mo) dans `%TEMP%` à chaque lancement :
3 s au lieu de 0,7 s, et le dossier reste si le programme est tué. Les deux sont livrés, le dossier reste la
forme recommandée pour un usage quotidien. Détails dans [PORTABLE.md](PORTABLE.md).

## Mode portable sur demande, sans migration

Un marqueur `LocalChords.portable` à côté du programme, plutôt qu'une détection de clé USB : le comportement
ne change jamais par surprise. Rien n'est copié d'un emplacement à l'autre : une migration automatique
risquerait d'écraser ou de dédoubler des analyses. Si `Data` ne peut pas être écrit, le programme demande
avant d'utiliser le dossier du PC.

## Ce qui n'a pas été fait, et pourquoi

- **Sections (couplet, refrain) :** pas de méthode dont la fiabilité soit mesurable ici sans annotations ; une
  étiquette fausse fait plus de tort qu'aucune. Les progressions répétées donnent déjà une lecture honnête
  de la forme.
- **Séparation de sources :** deux modèles lourds de plus, sans gain démontré ; lv-chordia est entraîné sur
  des mélanges complets, et chordotomy documente avoir écarté Demucs pour la basse. Non testé ici.
- **Cache de compilation numba dans le programme compilé :** il reste vide, d'où environ 6 s de plus à chaque
  analyse. Non traité : gain modeste pour un chemin fragile.
- **Accords 9, 11, 13 en sortie moteur :** lv-chordia les reconnaît mais chordotomy les réduit. Rétablir
  cette information demanderait de modifier son vocabulaire et son analyse harmonique.
- **Changement de mesure en cours de morceau :** une seule longueur de mesure par morceau.
- **Signature de code et installateur :** il faut un certificat payant ; le dossier se décompresse.
