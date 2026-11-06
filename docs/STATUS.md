# État du projet

Mis à jour le 2026-11-06.

## Où on en est

**Livrable :** `dist/LocalChords/LocalChords.exe`, construit et vérifié sur ce PC (voir
[BENCHMARKS.md](BENCHMARKS.md), section « Programme compilé »).

| Phase | État |
|---|---|
| A. Reconnaissance | Fait : [DECISIONS.md](DECISIONS.md) |
| B. Expérimentation | Fait : chordotomy `model` et `dsp`, Tiny AAM et GuitarSet |
| C. Architecture | Fait : [TECHNIQUE.md](TECHNIQUE.md) |
| D. MVP (P0) | Fait, tests réels |
| E. Application aboutie (P1) | Fait |
| F. Distribution | Fait, exécutable testé ; revue indépendante faite, voir plus bas |
| G. P2 | Liens, lots, comparaison de moteurs, progressions, transposition de l'audio. Non faits : sections, séparation de sources, GPU, avec leurs raisons dans DECISIONS.md |

## Limites connues

- Pas de mesure sur des morceaux du commerce, ni de comparaison avec Chordify.
- Le moteur ne sort pas 9, 11, 13, 6 ni add9 (réduits), et a du mal avec sus et ° sur son synthétique.
- Une seule longueur de mesure par morceau ; hors 4 temps, validé seulement sur signaux construits.
- Glisser-déposer physique jamais joué dans l'exécutable (l'événement est testé hors écran).
- Non testé sur un autre PC.
- **Instabilité non élucidée dans les tests :** 2 exécutions complètes de pytest sur 8 se sont arrêtées vers le
  100e test, sur une erreur interne (`SystemError` dans `compile`, ou pile d'appels fatale) ; les 6 autres sont
  passées, dont les 4 dernières à la suite (165 tests). Pas reproduit en isolant les fichiers. Hypothèse non
  vérifiée : Qt et torch dans le même processus, ce qui n'arrive que sous pytest, le programme les séparant.
  À l'appui : 20 analyses sur 20 sans erreur par le vrai processus d'analyse (`scripts/soak_worker.py`), et
  environ 260 analyses de mesure sans plantage. Si le processus d'analyse tombe, l'interface propose de réessayer.
- L'import YouTube dépend d'un site qui change, et parfois de Node.js ou Deno.
- 928 Mo sur disque, 418 Mo en zip (`dist/LocalChords-windows-x64.zip`). Programme non signé : SmartScreen avertit.
- Diffusion publique : libx264 et libx265 (GPL) sont dans le paquet, voir LICENCES-TIERS.md.

## Revue indépendante

Relecture par un agent séparé : 15 constats, tous traités, avec des tests pour les défauts les plus graves. Parmi eux :
une tonalité bémol choisie à la main cassait le projet ; une boucle jusqu'à la fin du morceau plantait le flux
audio ; l'affichage se figeait à chaque tour de boucle ; une comparaison annulée pouvait jeter l'analyse suivante.

## Reprendre

```bash
.venv/Scripts/python.exe -m pytest                       # tout, environ 5 min
.venv/Scripts/python.exe -m pytest -m "not slow"         # sans les moteurs
.venv/Scripts/python.exe -m PyInstaller localchords.spec --noconfirm
dist/LocalChords/LocalChords.exe --self-test <audio> <dossier>   # la preuve : voir report.json
```

Depuis zéro : `scripts/build.ps1`. Données de test : `chordotomy evaluate tiny-aam --engine model` les
télécharge. `work/` contient les essais et n'est pas suivi par Git.

## Prochaines étapes possibles

1. Écouter de vrais morceaux et corriger : c'est ce qui manque aux mesures.
2. Tester sur un PC sans NVIDIA ni outils de développement.
3. Si la taille gêne : convertir les modèles en ONNX pour retirer torch.
