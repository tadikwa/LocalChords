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
| [PySide6 / Qt](https://www.qt.io/qt-for-python) 6.12.0 | Interface | LGPL-3.0 | Les bibliothèques Qt restent des DLL séparées et remplaçables dans le dossier du programme. |
| [PyAV](https://github.com/PyAV-Org/PyAV) 19.0.2 | Décodage audio | BSD-3-Clause | Recompilé pour LocalChords contre un FFmpeg LGPL (voir plus bas) : la wheel officielle embarque libx264 et libx265 (GPL). |
| [FFmpeg](https://ffmpeg.org) n9.0.2-48-gd4070a14ce | Décodage audio, via PyAV | LGPL-3.0-or-later | Sept DLL séparées et remplaçables (`_internal/av.libs`). Aucune bibliothèque GPL ni non libre. |
| [python-soxr](https://github.com/dofuuz/python-soxr) 1.1.0 / libsoxr | Rééchantillonnage | LGPL-2.1+ | Via librosa. |
| [soundfile](https://github.com/bastibe/python-soundfile) 0.14.0 / libsndfile | Lecture de fichiers son | BSD-3-Clause / LGPL-2.1+ | Via librosa. |
| [numba](https://numba.pydata.org), [llvmlite](https://github.com/numba/llvmlite) | Compilation à la volée pour librosa | BSD ; BSD-2-Clause et Apache-2.0 avec exception LLVM | |
| [pooch](https://github.com/fatiando/pooch) | Dépendance | BSD-3-Clause | |
| [pretty_midi](https://github.com/craffel/pretty-midi), [pydub](https://github.com/jiaaro/pydub) | Dépendances des modèles | MIT | |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) / PortAudio | Sortie audio | MIT | Seule `libportaudio64bit.dll` est livrée : les variantes ASIO (SDK Steinberg, autre licence) sont retirées. |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Import de liens | Unlicense | L'usage qui en est fait reste sous la responsabilité de l'utilisateur et des conditions de chaque site. |

scikit-learn, h5py, einops et rotary-embedding-torch ne sont plus livrés depuis la v1.1 (ils servaient
au chemin torch).

LocalChords lui-même est sous licence MIT (`LICENSE`). Le texte de chaque licence est dans le dossier
`_internal` du programme, avec le paquet concerné (`*.dist-info`), ou à l'adresse du projet ; les textes
LGPL-3.0, GPL-3.0 (auquel la LGPL-3.0 renvoie) et LGPL-2.1 sont dans `_internal/licences`.

## FFmpeg

Construction partagée LGPL de [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds), version
`ffmpeg-n9.0.2-48-gd4070a14ce-win64-lgpl-shared-9.0` (publication `autobuild-2026-11-07-12-47`, SHA-256
`0cf5bd578e201901f4afff4fee53f4a8e08b899de7e4bb91c357d43e81ba3d54`), configurée avec `--enable-version3`,
sans `--enable-gpl` ni `--enable-nonfree`. `scripts/build_av_lgpl.py` recompile PyAV contre elle et refuse
le résultat si FFmpeg annonce une autre licence que la LGPL ou active une bibliothèque des listes GPL,
GPLv3 ou non libres de son `configure` ; `localchords.spec` refait la vérification avant chaque
construction. Les bibliothèques externes compilées dans ces DLL (dav1d, libvorbis, opus, LAME, libaom,
libvpx, libass, freetype, harfbuzz, fribidi, libxml2, zlib, etc.) sont sous licences libres
compatibles avec la LGPL-3.0 ; leur liste exacte est la ligne `configuration` affichée par
`python -c "import av._core as c; print(c.library_meta['libavcodec'])"`.

## Sources des composants LGPL

- **FFmpeg** : source au commit
  [`d4070a14ce`](https://github.com/FFmpeg/FFmpeg/tree/d4070a14cecc7e29eb278f9b6036c2284255f70d) ;
  scripts de construction, avec le commit de chaque bibliothèque externe, au commit
  [`c63bb30`](https://github.com/BtbN/FFmpeg-Builds/tree/c63bb308a1de656b425c132a8102f8fd5389afc5) de
  FFmpeg-Builds. Une copie des deux, avec la source de PyAV 19.0.2, est jointe à chaque publication
  (`LocalChords-vX.Y-sources-tierces.zip`).
- **Qt 6.12.0** : <https://download.qt.io/official_releases/qt/6.12/> ; PySide6 :
  <https://code.qt.io/cgit/pyside/pyside-setup.git/>.
- **libsoxr**, **libsndfile** : dans les dépôts de python-soxr et de soundfile, aux versions ci-dessus.

Les DLL LGPL restent remplaçables dans la version en dossier (zip). Pour l'exécutable unique, qui les
regroupe, `scripts/build.ps1` reconstruit le programme à partir de ce dépôt avec vos propres DLL.
Ce n'est pas un avis juridique.

Le code de LocalChords ne reprend aucun code de Chordify et n'utilise aucun de ses services.

Les diagrammes de guitare et de piano (v1.2) n'ajoutent aucune dépendance, police ni base de doigtés :
les positions sont calculées par `voicings.py` à partir des notes de l'accord et dessinées par Qt. Les
quelques formes usuelles écrites à la main (Bm en x24432, D/F♯ en 2x0232…) sont des connaissances musicales
courantes, vérifiées par le programme comme les autres.
