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
           "transpose_audio": false, "latin": false}
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

## Reconstruire

`scripts\build.ps1`, puis `dist\LocalChords\LocalChords.exe --self-test <audio> <dossier>` : code de
sortie 0 et `report.json` détaillent chaque étape. `requirements-lock.txt` fige les versions testées.
`chordotomy` est épinglé à 0.3.1 car `engines.py` appelle trois de ses fonctions privées
(`_tracker`, `_log_mel`, `_chunked`), passe par son argument `cache` et remplace le temps d'un appel
`librosa.beat.beat_track` ; `onnx_engine.py` remplace `model._networks` et reproduit `beats._log_mel` sans
torch. À revérifier à toute mise à jour : `scripts/compare_backends.py` compare torch et ONNX sur Tiny AAM
et GuitarSet.
