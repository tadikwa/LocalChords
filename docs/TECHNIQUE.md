# Documentation technique

## Organisation

```
src/localchords/
  app.py, __main__.py   démarrage ; freeze_support d'abord, pour le processus d'analyse
  audio.py              décodage (PyAV), empreinte de fichier, forme d'onde
  engines.py            l'interface des moteurs, et chordotomy derrière elle
  onnx_engine.py        les réseaux de chordotomy exécutés par ONNX Runtime, sans torch
  rhythm.py             tempo, mesure, barres de mesure, fiabilité de la grille
  worker.py             analyse et téléchargement dans un processus à part
  project.py            le projet : analyse brute + corrections, et tout ce qui s'en déduit
  chords.py             étiquettes, orthographe des notes, saisie, transposition
  voicings.py           positions de guitare et dispositions de piano, vérifiées par leurs notes
  export.py             texte et ChordPro
  library.py            dossiers utilisateur, réglages
  player.py             lecture : PortAudio, ralenti WSOLA, boucle, hauteur
  selftest.py           le scénario complet, lancé dans le programme compilé
  ui/                   thème, grille, chronologie, dialogues, PDF, fenêtre, diagrammes
tests/                  test_core (pur), test_voicings, test_player, test_engines (lents), test_ui (hors écran)
scripts/                compilation, mesures de performance, captures d'écran
```

Le processus d'interface n'importe ni ONNX Runtime ni librosa : il démarre en moins d'une seconde. L'analyse
est un second lancement du même programme (`multiprocessing` en `spawn`) ; l'annuler revient à le tuer.

## L'interface des moteurs

Un moteur est une fonction `run(y, progress) -> dict`, où `y` est l'audio mono float32 à 22 050 Hz et
`progress(fraction, texte)` rend compte de l'avancement. Elle lève `AnalysisError` avec un message pour
l'utilisateur. On l'ajoute à `engines.ENGINES` ; rien d'autre ne sait d'où vient l'analyse. Le menu
« Réanalyser » et la comparaison s'en servent sans changement.

## Le format de projet (`.lchords`)

JSON UTF-8, écrit de façon atomique. Le format sépare ce que le moteur a dit de ce que l'utilisateur a
changé : `analysis` n'est jamais modifié.

```jsonc
{
  "format": "localchords",
  "version": 1,               // refusé s'il vient d'une version plus récente
  "audio": {
    "path": "C:/…/chanson.mp3",
    "title": "…", "artist": "…",
    "duration": 196.3,        // secondes
    "fingerprint": "…",       // taille + premier et dernier Mo : retrouve un morceau déplacé
    "waveform": "…",          // 3000 octets de crêtes, en base64
    "source_url": null        // la page d'origine, pour un lien importé
  },
  "analysis": {               // tel que le moteur l'a écrit
    "engine": {"name": "model", "generator": {…}, "requested": "model"},
    "beats": [0.021, 0.673, …],        // secondes
    "segments": [{
      "start_beat": 0, "end_beat": 4, "start_time": 0.021, "end_time": 2.63,
      "chord": "F#:hdim7",             // étiquette Harte, ou "N" : pas d'accord
      "bass": "A", "inversion": "first",
      "candidates": ["F#:hdim7", "A:min6"],   // classement, sans score
      "numeral": "iiø7", "role": "diatonic", "function": "…", "target": null
    }],
    "global_key": {"label": "E:min", "source": "estimated", "candidates": […]},
    "key_regions": [{"start_beat": 0, "end_beat": 96, "label": "E:min"}],
    "meter": {
      "beats_per_bar": 4, "first_downbeat": 1,
      "bar_lines": [1, 5, 9, …],       // indices de temps ; peuvent se recaler
      "confidence": 0.8, "candidates": [4, 3, 6]
    },
    "tempo": {"bpm": 92.3, "steadiness": 0.99},
    "grid_fit": 0.99,                  // accord entre la grille et Beat This!
    "followed_tempo": false
  },
  "edits": {                  // ce que l'utilisateur a changé
    "chords": [{"start": 12.1, "end": 14.7, "chord": "D:min7", "bass": null}],  // en secondes
    "meter": {"beats_per_bar": 3, "first_downbeat": 0},   // ou null
    "grid": {"scale": 2, "offset": 0.1, "bpm": null},     // ou null
    "key": "C:maj"                                        // ou null
  },
  "view": {"transpose": 0, "capo": 0, "accidentals": "auto", "simplify": false,
           "min_beats": 1, "show_bass": true, "show_numerals": false,
           "transpose_audio": false, "latin": false,
           "positions": {"g:D:maj::0": 1}}  // v1.2.1 : position choisie par accord, absente = la première
}
```

Les corrections sont en secondes, pas en temps : elles survivent à un changement de grille et à une
réanalyse. Elles se superposent dans l'ordre : la dernière gagne. Chaque temps reçoit l'accord qui le couvre
le plus. Une analyse qui change de grille ne perd donc rien.

## Les diagrammes d'accords

`voicings.py` ne dessine rien ; `ui/diagrams.py` ne décide d'aucune note.

- **Guitare.** Accordage standard (E2 A2 D3 G3 B3 E4), 15 cases au-dessus du capo. Pour un accord et sa
  basse, `guitar()` essaie toutes les combinaisons de cases dans une main (4 cases d'écart au plus) et ne
  garde une position que si `check()` le confirme sur les notes réelles : la plus grave est la basse
  demandée, toutes les autres appartiennent à l'accord, au moins 4 cordes sonnent, il manque au plus la
  quinte d'un accord de 4 sons, et les doigts (1 à 4, barré compris) suffisent. Les formes classiques
  (`CLASSICS`, écrites à la main : x24432 pour Bm, 2x0232 pour D/F♯…) passent les mêmes contrôles et
  viennent en tête quand elles sont valides ; les autres sont classées par difficulté, une par endroit du
  manche, puis en montant. Sans position valide, la liste est vide et le panneau le dit au lieu de dessiner.
- **Piano.** `piano()` donne les renversements en position serrée, puis la basse à la main gauche et
  l'accord à la main droite. Avec une basse demandée, elle est toujours la note la plus grave.
- **Ce qui est affiché.** `describe()` part de l'étiquette du segment et de la vue du projet, comme la
  grille : la forme de guitare suit `transposition − capo` (F♯m entendu, capo en case 2 : forme de Em),
  le son et le piano suivent la transposition seule. Notation, dièses ou bémols, accords simplifiés et
  basses masquées sont ceux de la grille.
- **Tests.** `tests/test_voicings.py` vérifie chaque position de chaque fondamentale, qualité et basse
  (chaque note de l'accord et deux notes étrangères) ; `tests/test_ui.py` vérifie le suivi de la lecture,
  l'épinglage, le capo, la transposition, la notation, les corrections et la réouverture.
- **Interface.** Le panneau suit l'accord sous la tête de lecture. Un clic épingle l'accord ;
  « Suivre la lecture », Échap ou la lecture y reviennent. Les images sont mises en cache par accord et
  par taille ; un changement d'accord se fond en 140 ms. À 1280 px et plus, le panneau est à droite de la
  grille ; en dessous, sous elle. Mode et taille sont dans `settings.json` (`diagram_mode`,
  `diagram_panel`).

## Les accords du morceau et la fiche (v1.2.1)

- **Une seule position par accord.** `diagrams.Positions` garde la position choisie pour chaque accord
  (`g:` guitare, `p:` piano, avec la fondamentale, la qualité, la basse d'un renversement et le capo). Le
  panneau, les cartes et la fiche lisent le même objet ; il est enregistré dans `view.positions` et rechargé
  à la réouverture. Le charger n'enregistre rien.
- **La liste.** `MainWindow._update_song_chords` passe chaque segment par `describe()`, comme la grille, et
  garde le premier de chaque accord (`songchords.chord_key` : nom affiché, basse et capo). Elle est
  recalculée à chaque changement du projet (correction, annulation, transposition, capo, notation), jamais
  pendant la lecture. « À venir » ne refait ses cartes que quand l'accord en cours change.
- **Les cartes.** `ui/songchords.py` : `ChordCard` redessine seulement ce qui a changé ; un clic émet le
  temps du premier passage de l'accord, que la fenêtre épingle dans le panneau sans toucher au lecteur. Vue,
  mode et état (réduit, agrandi, masqué) sont dans `settings.json` (`song_chords_view`, `song_chords_mode`,
  `song_chords_state`).
- **La fiche.** `pdf.write_chord_sheet` : A4 vectoriel par `QPdfWriter`, mise en page calculée d'abord
  (`sheet_layout` : une rangée qui ne tient pas entière passe à la page suivante), dessin ensuite, pour que
  chaque pied de page sache le nombre de pages. Les diagrammes sont ceux de l'écran, dessinés avec une
  palette d'impression. La grille, en option, reprend le dessin de l'export PDF existant.
- **Tests.** `tests/test_songchords.py` : ordre et doublons, corrections, transposition, capo, notation,
  « À venir », clic sans déplacement de la lecture, clavier, positions partagées et rouvertes, pages de la
  fiche, aucune carte coupée, clic réel sur Lecture à trois tailles de fenêtre.

## Les paroles (v1.3)

`lyrics.py` lit, place et écrit les paroles ; `lyrics_online.py` interroge LRCLIB ; `transcribe.py`
fait tourner whisper.cpp ; `ui/lyrics_view.py` et `ui/lyrics_dialogs.py` les affichent ; `ui/pdf.py`
écrit la fiche paroles et accords.

**D'où elles viennent, dans cet ordre :**

1. **Le disque** : un `.lrc`, `.srt` ou `.txt` du même nom que l'audio, ou les paroles écrites dans le
   fichier audio (balises lues par PyAV). Proposées à l'ouverture, prises d'office pour un morceau neuf.
2. **LRCLIB** (<https://lrclib.net>), seulement sur demande : API publique sans clé, faite pour ça. Seuls
   le titre, l'artiste, l'album et la durée partent ; jamais l'audio. LRCLIB n'annonce aucune licence pour les paroles
   qu'il sert, et elles appartiennent à leurs auteurs : marquées `exportable: false`, elles sont
   affichées pour jouer, avec leur origine, mais refusées par tous les exports (texte, LRC, PDF). Aucun
   autre catalogue n'est interrogé : les autres sites de paroles n'ouvrent pas d'API publique à cet usage.
3. **La transcription sur ce PC** : `whisper-cli.exe` (whisper.cpp b5454, CPU), livré avec le programme et
   lancé comme un processus à part, sur un WAV 16 kHz temporaire. Les modèles se téléchargent à la demande
   depuis Hugging Face (taille et SHA-256 vérifiés) : `small-q5_1` (190 Mo, par défaut) ou
   `large-v3-turbo-q5_0` (574 Mo, plus juste, environ 2,5 fois plus lent). Commande :
   `-ojf -pp -np -sns -mc 0` (repli de température gardé, pas de contexte d'une fenêtre à l'autre). Le
   résultat est un brouillon : les lignes répétées en boucle, les génériques (« sous-titres par… ») et les
   mots posés sur du silence sont retirés (`plausible`). Choix mesurés : voir
   [BENCHMARKS.md](BENCHMARKS.md#transcription-des-paroles-v13).

**Dans le projet** (`.lchords` version 2, écrit en version 1 tant qu'il n'y a pas de paroles) :

```jsonc
"lyrics": {
  "source": {"kind": "file", "name": "chanson.lrc", "exportable": true},  // user, file, embedded, catalog, transcription
  "original": [ … ],          // les lignes telles que reçues, pour « Revenir à l'original »
  "lines": [{"text": "…", "start": 12.5, "end": 15.1, "section": false,
             "words": [[0, 12.5], [4, 12.9]]}],  // [caractère, temps] de chaque mot, si la source les donne
  "offset": 0.0,              // décalage global, en secondes
  "anchors": {"12.10": {"line": 3, "char": 14}},  // accords placés à la main : clé = début de l'accord
  "previous": { … }           // les paroles d'avant le dernier remplacement, une fois
}
```

**Les accords sur les mots** (`lyrics.sheet`) : chaque accord va sur la ligne chantée à son début, au mot
chanté à cet instant si la source donne le temps des mots, sinon réparti dans la ligne et affiché en
italique gris (« approximatif »). Un accord qui sonne déjà au début d'une ligne y est rappelé. Glisser un
accord sur un autre mot n'écrit qu'une ancre (ligne, caractère) : l'harmonie et la grille ne changent pas.
Ancres, décalage et corrections de lignes passent par la pile d'annulation du projet.

**Vues** : grille seule, grille et paroles (deux lignes sous la barre de lecture), paroles seules, paroles et
accords ; `K` alterne. La vue suit la lecture, sauf 5 s après un défilement à la main.

## Reconstruire

`scripts\build.ps1`, puis `dist\LocalChords\LocalChords.exe --self-test <audio> <dossier>` : code de
sortie 0 et `report.json` détaillent chaque étape. `requirements-lock.txt` fige les versions testées.
`chordotomy` est épinglé à 0.3.1 car `engines.py` appelle trois de ses fonctions privées
(`_tracker`, `_log_mel`, `_chunked`), passe par son argument `cache` et remplace le temps d'un appel
`librosa.beat.beat_track` ; `onnx_engine.py` remplace `model._networks` et reproduit `beats._log_mel` sans
torch. À revérifier à toute mise à jour : `scripts/compare_backends.py` compare torch et ONNX sur Tiny AAM
et GuitarSet.
