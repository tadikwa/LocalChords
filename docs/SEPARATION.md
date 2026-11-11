# Séparation des instruments et mixage (v1.6)

LocalChords peut séparer un morceau en pistes (voix, batterie, basse, autres) puis les mixer en direct
pendant la lecture. La séparation est faite une fois, sur demande, par un modèle d'IA local ; les pistes
sont gardées sur le disque, et le mixage ne refait jamais tourner le modèle. Rien n'est envoyé nulle part.

## Ce qui a été comparé

Mesures de 2026-11-11 sur le PC de développement (Ryzen 7 9800X3D 8 cœurs, 31 Go, RTX 5070 Ti 16 Go,
pilote 621.01), par le code même du programme (`separation.py`) sauf mention contraire.

**Qualité sur MUSDB18** (50 extraits de 7 s de la partie test, vérité terrain par instrument ; SDR médian
en dB, plus c'est haut mieux c'est ; « fuite voix » = part de la vraie voix restée dans l'instrumental) :

| Modèle | Voix | Instrumental | Batterie | Basse | Autres | Fuite voix | Temps (CPU) |
|---|---|---|---|---|---|---|---|
| **Demucs v4 htdemucs** (retenu) | **8,9** | **13,1** | 9,4 | 9,2 | 5,2 | −17,5 dB | 0,19 × la durée |
| Demucs v4 htdemucs_ft (4 réseaux) | 8,4 | 13,1 | 9,8 | 9,3 | 5,3 | −18,1 dB | ×4,5 |
| Demucs v4 htdemucs_6s (6 pistes) | 8,6 | 13,3 | 9,2 | 8,2 | 4,7 | −17,5 dB | ≈ htdemucs |
| UVR MDX-Net Inst_HQ_4 (via python-audio-separator) | 6,8 | 10,1 | – | – | – | −23,4 dB | 0,57 × la durée |

Sur ces extraits, htdemucs_ft n'apporte rien à la voix et coûte quatre fois plus de temps et de
téléchargement (697 Mo). MDX-Net laisse moins de voix dans l'instrumental mais l'abîme davantage
(3 dB de moins). Les modèles RoFormer/MDXC et les autres modèles communautaires ont été écartés sans
mesure : leurs droits de redistribution ne sont pas établis.

**Le portage.** Les réseaux de Meta sont convertis en ONNX sans leur transformée de Fourier
(`scripts/export_demucs_onnx.py`, dans un environnement à part qui a PyTorch). Le programme fait la STFT,
le découpage en segments de 7,8 s (recouvrement 25 %, fondus triangulaires) et la normalisation comme
`demucs.apply`, avec numpy, et exécute les réseaux avec onnxruntime, déjà présent pour les accords. Écart
avec PyTorch : STFT 5·10⁻⁷, STFT inverse 2·10⁻⁶, pistes à 68 à 90 dB de SDR de la sortie PyTorch,
c'est-à-dire identiques à l'oreille. Pas de PyTorch ni de CUDA dans le programme.

**Morceaux complets** (libres de droits, Wikimedia Commons, voir `work/test-songs/SOURCES.txt`) : temps de
séparation en mode Musicien sur le processeur, mémoire maximale du processus de séparation, taille des
pistes, et part de l'énergie du morceau dans chaque piste :

| Morceau (licence) | Durée | Temps | Mémoire | Pistes | Voix | Batterie | Basse | Autres |
|---|---|---|---|---|---|---|---|---|
| Monkeys At Typewriters, funk pop chanté, fait avec Suno (CC0) | 2:33 | 29 s | 2,96 Go | 44 Mo | −4,4 | −5,2 | −7,6 | −11,6 |
| Welcome to the War, folk rock guitare et voix (CC BY-SA) | 2:38 | 30 s | 2,97 Go | 34 Mo | −6,9 | −5,8 | −14,8 | −4,5 |
| Chee Zee Jungle, instrumental batterie et basse (CC BY) | 2:42 | 30 s | 2,98 Go | 39 Mo | −25,9 | −3,8 | −6,6 | −6,9 |
| Victimae Paschali Laudes, voix seule (domaine public) | 1:49 | 20 s | 2,84 Go | 16 Mo | 0,0 | −60,6 | −63,9 | −36,1 |
| Mendelssohn, Romance sans paroles, piano seul (CC BY-SA) | 1:16 | 14 s | 2,74 Go | 10 Mo | −58,5 | −55,0 | −59,5 | 0,0 |

La voix seule va entièrement dans « Voix », le piano seul dans « Autres ». Sur l'instrumental, « Voix »
garde −26 dB de l'énergie (des notes de synthé prises pour du chant, audibles seules mais pas dans le
mélange). En mode Karaoké (même modèle, deux pistes), le premier morceau prend 28,5 s et 28 Mo.

## Ce que fait le programme

**Modes.** *Karaoké* : voix et instrumental. *Musicien* : voix, batterie, basse, autres. Les deux
utilisent le même modèle, htdemucs (174 Mo, téléchargé une fois). Ce que le modèle laisse de côté
(−30 dB en moyenne) est ajouté à la dernière piste (instrumental ou autres) : à leur niveau d'origine, les
pistes redonnent exactement le morceau (−72 dB d'écart, celui du FLAC 16 bits).

**Pas de mode 6 pistes.** htdemucs_6s ajoute guitare et piano, mais Meta le dit faible sur le piano
(« beaucoup de fuites et d'artefacts »), il dégrade la basse d'un dB sur MUSDB18, et rien ne permet de
mesurer ses pistes guitare et piano (MUSDB18 n'en a pas). Un mode 4 pistes fiable a été préféré.

**Calcul.** Sur le processeur, partout : environ un cinquième de la durée du morceau sur le PC de mesure
(8 cœurs ; plus lent sur une machine plus modeste). La séparation tourne dans un processus à part, en
priorité basse : la lecture et la fenêtre restent fluides, l'annulation arrête le processus aussitôt.
Mémoire : environ 3 Go au maximum pour un morceau de 2 à 3 minutes, dont 2,2 Go pour le réseau (sans le
cache mémoire d'onnxruntime, qui en prenait 8 de plus pour la même vitesse).

Accélération graphique : DirectML (onnxruntime-directml 1.24.4) donne des résultats faux sur ce réseau
(erreur relative de l'ordre de 10⁴, à tous les niveaux d'optimisation) : écarté. CUDA (onnxruntime-gpu
1.31.1, CUDA 13 et cuDNN 9.28) donne le bon résultat sur la RTX 5070 Ti, environ trois fois plus vite,
mais demande 1,34 Go de bibliothèques NVIDIA à télécharger. Voir « État » plus bas.

**Cache.** `<données>/stems/<empreinte>-<mode>-htdemucs-<SHA-256 du modèle>/` : une piste FLAC 16 bits
stéréo à 44,1 kHz par instrument et un `info.json` (modèle, empreinte, facteur d'échelle d'une piste qui
dépasserait la pleine échelle). L'empreinte est celle de l'enregistrement (taille et premiers et derniers
Mo), la même que pour les projets ; un autre modèle ne réutilise jamais un ancien résultat. Taille
mesurée : 33 à 96 ko par seconde et par piste, soit 25 à 45 Mo pour 4 pistes d'un morceau de 2 min 30.
Le FLAC 16 bits garde un bruit de quantification à −96 dB, très en dessous des artefacts de séparation
(−20 à −30 dB) ; le WAV prendrait deux à trois fois plus de place pour rien. Les données
`%LOCALAPPDATA%\LocalChords` ou, en mode portable, `Data` à côté du programme.

**Mixage.** Les pistes sont lues en mémoire en float16 (une piste de 4 minutes : 23 Mo) et mixées bloc par
bloc par le lecteur, avant le changement de vitesse et de hauteur : boucles, sauts, vitesse, transposition,
volume général, accords et paroles suivent la même horloge. Chaque gain change par une rampe de 30 ms
(sans clic), la bascule Original / Mix est un fondu de 30 ms entre l'enregistrement et la somme des
pistes, alignées à l'échantillon près (vérifié après rééchantillonnage 44,1 → 48 kHz). Loi de gain des
curseurs : 0 = silence total, position 75 = 0 dB, −12 dB à mi-course, +5 dB au maximum (gain en carré de
la position, comme un fader). Une somme de pistes poussées au-delà de 0,95 est arrondie (tangente
hyperbolique) plutôt qu'écrêtée ; aucune normalisation par piste.

## Limites

Aucune séparation n'est parfaite : un peu de chaque instrument reste audible dans les autres pistes
(réverbération du chant dans « Autres », charleston dans « Voix », synthés pris pour du chant). Les
chœurs vont dans « Voix ». Guitare, piano, cuivres, synthés restent ensemble dans « Autres ».
