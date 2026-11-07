# LocalChords v1.1 : rapport

2026-11-07, branche `v1.1`. Détail des mesures dans [BENCHMARKS.md](BENCHMARKS.md), mode portable dans
[PORTABLE.md](PORTABLE.md). La v1.0 (`dist/LocalChords`, `dist/LocalChords-windows-x64.zip`) n'a pas été touchée.

## Livrables

Dans `dist/`, à côté de la v1.0. Mo au sens de l'Explorateur Windows.

| Fichier | Taille | Contenu |
|---|---|---|
| `LocalChords-v1.1-windows-x64.zip` | 283 Mo | dossier `LocalChords` (592 Mo décompressé), forme recommandée |
| `LocalChords-v1.1-portable.exe` | 283 Mo | exécutable unique |
| `LocalChords-v1.1-sources-tierces.zip` | 21 Mo | sources de FFmpeg et PyAV, exigées par la LGPL |

## Ce qui change pour vous

- **Transposer le son** : un bouton « Son transposé / Son d'origine » à côté de `Transposer`, allumé quand le
  son suit. Éteint, seule la grille change, comme avant.
- **Plus léger** : 592 Mo au lieu de 928, mêmes accords (ONNX Runtime à la place de torch ; 510 Mo avec le
  FFmpeg GPL de PyAV, remplacé pour la diffusion par un FFmpeg LGPL, voir plus bas).
- **Un seul fichier** possible, et un **mode portable** : tout dans un dossier `Data` à côté du programme.
- Morceaux récents : titres longs coupés proprement, durée affichée, « audio introuvable » si le fichier
  a disparu. Fenêtres de confirmation entièrement en français (les boutons Qt étaient en anglais).

## P1 : transposition de l'audio

**Constat :** la hauteur changeait déjà en v1.0 ; le défaut venait de l'option, cachée dans un menu et
désactivée par défaut, d'où des boutons qui ne changeaient « que les accords ».

**Mesure objective, dans les deux programmes compilés :** un la 440 Hz donne 880,00 Hz à +12 et 220,00 Hz à
−12, sans changement de vitesse ; ±1 et ±5 à 0,1 cent près ; avec ralenti (50 %, 75 %, 150 %) la hauteur
reste juste et la durée des notes suit la vitesse à 1 % près ; boucles A/B transposées justes, y compris en
changeant la transposition pendant la boucle. Aucun défaut reproduit, donc rien de corrigé dans le lecteur.

## P2 : exécutable unique

Livré, avec ses limites :

| | Dossier | Exécutable unique |
|---|---|---|
| Démarrage (fenêtre visible) | 0,7 s | 3,4 s |
| Analyse d'un morceau de 2 min | 16,6 à 17,5 s | 16,9 à 19,6 s |
| `%TEMP%` à chaque lancement | rien | 567 Mo, effacés à la fermeture |
| Programme tué (Gestionnaire des tâches) | rien | **567 Mo restent** dans `%TEMP%\_MEIxxxxxx` |

Vérifié dans l'exécutable unique : `freeze_support` et processus d'analyse (un seul dossier décompressé,
partagé), modèles embarqués, chemin accentué et japonais, scénario complet (`--self-test` : analyse, lecture,
synchronisation, ralenti, boucle, correction, transposition, trois exports, réouverture), mesure de hauteur,
mode portable. Le dossier reste la forme recommandée pour un usage quotidien.

## P3 : taille

| Solution | Gain mesuré | Effet |
|---|---|---|
| ONNX Runtime à la place de torch | dossier −418 Mo (928 → 510), zip −151 Mo (398 → 247), exécutable unique −150 Mo (397 → 247) | mêmes accords, temps, tonalités et mesures sur 204 fichiers (Tiny AAM 20, GuitarSet 180, 4 morceaux entiers) ; analyse 1 à 7 % plus rapide |
| Exclure scikit-learn, h5py, einops (inutiles sans torch) | compris ci-dessus | aucun |
| Compression de l'exécutable unique | incluse (zlib de PyInstaller) | 3 s de décompression au lancement |
| FFmpeg LGPL de BtbN à la place de celui de PyAV | **+83 Mo** (65 → 148), dossier 592 Mo, zip et exécutable 283 Mo | nécessaire à la diffusion (plus de GPL) ; décodage identique |
| FFmpeg réduit au décodage audio | environ 140 Mo, **non fait** | demanderait de compiler FFmpeg |
| UPX | non essayé | casse souvent les DLL Qt, alertes antivirus |

Ce qui reste est nécessaire à l'analyse ou à l'interface (llvmlite 115 Mo pour librosa, modèles 89 Mo, FFmpeg
148 Mo, SciPy 68 Mo, Qt 51 Mo, ONNX Runtime 38 Mo). Un exécutable d'environ 100 Mo demanderait de réécrire
l'analyse sans librosa : pas fait.

## P4 : mode portable

Un fichier vide `LocalChords.portable` à côté de l'exécutable : les données vont dans `Data` à côté. Sans lui,
rien ne change (`%LOCALAPPDATA%\LocalChords`). Jamais dans le dossier temporaire de l'exécutable unique. Rien
n'est migré, copié ni supprimé. `Data` impossible à écrire : le programme demande avant d'utiliser les données
du PC pour la session, ou se ferme. Moins de 200 Mo libres : avertissement au démarrage.

## Conformité des licences, pour la diffusion

La wheel PyAV embarquait un FFmpeg lié à libx264 et libx265 (GPL). PyAV 19.0.2 est recompilé contre le
FFmpeg LGPL de BtbN (`scripts/build_av_lgpl.py`, empreintes figées) ; le script et `localchords.spec`
refusent tout FFmpeg qui n'est pas LGPL ou qui active une bibliothèque GPL ou non libre. Retirés aussi :
les DLL PortAudio ASIO (SDK Steinberg), jamais chargées. Ajoutés : `LICENSE` (MIT), les textes LGPL-3.0,
GPL-3.0 et LGPL-2.1 dans le programme, et les sources de FFmpeg et PyAV à chaque publication. Détails dans
[LICENCES-TIERS.md](../LICENCES-TIERS.md). Mêmes résultats : décodage identique, `--self-test` identique
dans les deux formes, 168 tests.

## Tests

- pytest : 168 tests réussis (suite complète, moteurs compris). Un premier passage a révélé une fuite de
  variable d'environnement entre le nouveau test du mode portable et les tests du processus d'analyse, corrigée dans le test.
- Nouveaux tests : mode portable (sans marqueur, avec, `Data` bloqué), morceaux récents dans la fenêtre et
  audio disparu, largeurs 1000, 1120, 1240 et 2560 px.
- `--self-test` réussi dans les deux formes, moteur `onnx`. Mesure de hauteur réussie dans les deux formes.
- Captures aux largeurs étroites (GlazeWM) et larges : `scripts/screenshot.py`.

## Limites et non testé

- Pas de vraie clé USB, ni de support réellement protégé en écriture (simulé), ni de PC coupé du réseau,
  ni d'autre PC.
- Exécutable unique : démarrage plus lent, 567 Mo laissés dans `%TEMP%` s'il est tué.
- `onnx_engine.py` dépend de fonctions privées de chordotomy 0.3.1 : à revérifier avec
  `scripts/compare_backends.py` à toute mise à jour.
- Les limites de la v1.0 restent (pas de mesure sur des morceaux du commerce, pas de 9/11/13…).

## Différences avec la v1.0

| | v1.0 | v1.1 |
|---|---|---|
| Exécution des modèles | torch | ONNX Runtime (torch encore possible : `LOCALCHORDS_BACKEND=torch`, build `LOCALCHORDS_TORCH_BUILD=1`) |
| Taille du dossier | 928 Mo | 592 Mo |
| Exécutable unique | non | oui, 283 Mo |
| FFmpeg | celui de PyAV (avec libx264, libx265) | LGPL, recompilé |
| Licence de LocalChords | non précisée | MIT |
| Son transposé | option de menu, éteinte | bouton visible à côté de `Transposer` |
| Données | `%LOCALAPPDATA%` | idem, ou `Data` en mode portable |
| Accords, temps, mesure | | identiques |
