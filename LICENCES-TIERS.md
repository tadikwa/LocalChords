# Licences des composants tiers

LocalChords s'appuie sur les composants ci-dessous. Vérifié à la source le 2026-11-06 ; les versions
exactes de la distribution sont dans `requirements-lock.txt`.

| Composant | Rôle | Licence | Remarque |
|---|---|---|---|
| [chordotomy](https://github.com/zeikar/chordotomy) 0.3.1 | Moteur d'analyse, harmonie | MIT | |
| [lv-chordia](https://github.com/openmirlab/lv-chordia) 1.1.0 | Modèle de reconnaissance d'accords | MIT (code et poids) | Poids entraînés par les auteurs sur des enregistrements commerciaux annotés (Isophonics, Billboard, RWC-Pop, USPOP). |
| [Beat This!](https://github.com/CPJKU/beat_this) 1.1 | Temps et premiers temps | MIT (code et poids) | Certains fichiers d'entraînement sont sous copyright ; les auteurs laissent à l'utilisateur le soin d'en juger. |
| [PyTorch](https://pytorch.org) | Exécution des modèles | BSD-3-Clause | Version CPU. |
| [librosa](https://github.com/librosa/librosa) | Analyse audio | ISC | |
| [NumPy](https://numpy.org), [SciPy](https://scipy.org), [scikit-learn](https://scikit-learn.org) | Calcul | BSD-3-Clause | |
| [PySide6 / Qt](https://www.qt.io/qt-for-python) | Interface | LGPL-3.0 | Les bibliothèques Qt restent des DLL séparées et remplaçables dans le dossier du programme. |
| [PyAV](https://github.com/PyAV-Org/PyAV) | Décodage audio | BSD-3-Clause | Embarque FFmpeg (LGPL-2.1+), en DLL séparées. |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) / PortAudio | Sortie audio | MIT | |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Import YouTube, si présent | Unlicense | |

Le texte de chaque licence est dans le dossier `_internal` du programme, avec le paquet concerné
(`*.dist-info`), ou à l'adresse du projet.

Le code de LocalChords ne reprend aucun code de Chordify et n'utilise aucun de ses services.
