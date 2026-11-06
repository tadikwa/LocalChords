# Documentation technique

## Organisation

```
src/localchords/
  app.py, __main__.py   démarrage ; freeze_support d'abord, pour le processus d'analyse
  audio.py              décodage (PyAV), empreinte de fichier, forme d'onde
  engines.py            l'interface des moteurs, et chordotomy derrière elle
  rhythm.py             tempo, mesure, barres de mesure, fiabilité de la grille
  worker.py             analyse et téléchargement dans un processus à part
  project.py            le projet : analyse brute + corrections, et tout ce qui s'en déduit
  chords.py             étiquettes, orthographe des notes, saisie, transposition
  export.py             texte et ChordPro
  library.py            dossiers utilisateur, réglages
  player.py             lecture : PortAudio, ralenti WSOLA, boucle, hauteur
  selftest.py           le scénario complet, lancé dans le programme compilé
  ui/                   thème, grille, chronologie, dialogues, PDF, fenêtre
tests/                  test_core (pur), test_player, test_engines (lents), test_ui (hors écran)
scripts/                compilation, mesures de performance, captures d'écran
```

Le processus d'interface n'importe ni torch ni librosa : il démarre en moins d'une seconde. L'analyse
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

## Reconstruire

`scripts\build.ps1`, puis `dist\LocalChords\LocalChords.exe --self-test <audio> <dossier>` : code de
sortie 0 et `report.json` détaillent chaque étape. `requirements-lock.txt` fige les versions testées.
`chordotomy` est épinglé à 0.3.1 car `engines.py` appelle quatre de ses fonctions privées
(`_tracker`, `_log_mel`, `_chunked`) et son argument `cache` : à revérifier à toute mise à jour.
