# Licences des composants tiers

LocalChords s'appuie sur les composants ci-dessous. Vérifié à la source le 2026-11-06, mis à jour le 2026-11-07 ; les versions
exactes de la distribution sont dans `requirements-lock.txt`.

| Composant | Rôle | Licence | Remarque |
|---|---|---|---|
| [chordotomy](https://github.com/zeikar/chordotomy) 0.3.1 | Moteur d'analyse, harmonie | MIT | |
| [lv-chordia](https://github.com/openmirlab/lv-chordia) 1.1.0 | Modèle de reconnaissance d'accords | MIT (code et poids) | Poids entraînés par les auteurs sur des enregistrements commerciaux annotés (Isophonics, Billboard, RWC-Pop, USPOP). |
| [Beat This!](https://github.com/CPJKU/beat_this) 1.1 | Temps et premiers temps | MIT (code et poids) | Certains fichiers d'entraînement sont sous copyright ; les auteurs laissent à l'utilisateur le soin d'en juger. |
| [ONNX Runtime](https://onnxruntime.ai) | Exécution des modèles | MIT | Modèles exportés depuis les poids d'origine avec [PyTorch](https://pytorch.org) (BSD-3-Clause), qui n'est plus livré. |
| [librosa](https://github.com/librosa/librosa) | Analyse audio | ISC | |
| [NumPy](https://numpy.org), [SciPy](https://scipy.org) | Calcul | BSD-3-Clause | |
| [PySide6 / Qt](https://www.qt.io/qt-for-python) | Interface | LGPL-3.0 | Les bibliothèques Qt restent des DLL séparées et remplaçables dans le dossier du programme. |
| [PyAV](https://github.com/PyAV-Org/PyAV) | Décodage audio | BSD-3-Clause | Embarque FFmpeg (`avcodec_license()` de la DLL livrée : « LGPL version 3 or later ») et, en DLL séparées, ses codecs, dont **libx264 et libx265 (GPL-2.0+)**, jamais appelés : LocalChords ne fait que décoder de l'audio. Voir plus bas. |
| [python-soxr](https://github.com/dofuuz/python-soxr) / libsoxr | Rééchantillonnage | LGPL-2.1+ | Via librosa. |
| [soundfile](https://github.com/bastibe/python-soundfile) / libsndfile | Lecture de fichiers son | BSD-3-Clause / LGPL-2.1+ | Via librosa. |
| [numba](https://numba.pydata.org), [llvmlite](https://github.com/numba/llvmlite) | Compilation à la volée pour librosa | BSD ; BSD-2-Clause et Apache-2.0 avec exception LLVM | |
| [pooch](https://github.com/fatiando/pooch) | Dépendance | BSD-3-Clause | |
| [pretty_midi](https://github.com/craffel/pretty-midi), [pydub](https://github.com/jiaaro/pydub) | Dépendances des modèles | MIT | |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) / PortAudio | Sortie audio | MIT | |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Import de liens | Unlicense | L'usage qui en est fait reste sous la responsabilité de l'utilisateur et des conditions de chaque site. |

scikit-learn, h5py, einops et rotary-embedding-torch ne sont plus livrés depuis la v1.1 (ils servaient
au chemin torch).

Le texte de chaque licence est dans le dossier `_internal` du programme, avec le paquet concerné
(`*.dist-info`), ou à l'adresse du projet.

## Avant de redistribuer le programme

Pour votre usage personnel, rien à faire. **Avant de le diffuser** à d'autres, sachez que le paquet contient
libx264 et libx265 (GPL-2.0+), présents dans les wheels PyAV bien que non utilisés. Il faudrait alors respecter
la GPL pour l'ensemble, ou remplacer ces DLL en construisant FFmpeg sans eux. Ce n'est pas un avis juridique.

Le code de LocalChords ne reprend aucun code de Chordify et n'utilise aucun de ses services.
