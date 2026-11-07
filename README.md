# LocalChords

Une grille d'accords lisible et synchronisée avec la lecture, sur votre PC Windows. Vous déposez un
morceau, les accords apparaissent par mesures et défilent pendant l'écoute. Tout se passe sur votre
ordinateur : l'audio n'est envoyé nulle part, aucun compte, aucun abonnement.

## Télécharger LocalChords

**[Télécharger la dernière version](https://github.com/tadikwa/LocalChords/releases/latest)**, pour
Windows 10 ou 11 en 64 bits. Rien d'autre à installer : ni Python, ni carte graphique particulière, ni
connexion Internet (sauf pour importer un lien).

Sur la page de la version, dans « Assets », prenez **l'un des deux** fichiers :

| Fichier | Pour qui | Comment |
|---|---|---|
| `LocalChords-v1.1-portable.exe` (environ 285 Mo) | le plus simple | Téléchargez-le, double-cliquez. Un seul fichier, à garder où vous voulez. |
| `LocalChords-v1.1-windows-x64.zip` (environ 285 Mo) | un usage quotidien | Clic droit sur le zip → « Extraire tout », puis ouvrez le dossier `LocalChords` et lancez `LocalChords.exe`. |

Même programme, mêmes résultats. Le dossier démarre en moins d'une seconde. L'exécutable unique se
décompresse à chaque lancement : environ 3,5 s, et 570 Mo dans le dossier temporaire de Windows, effacés
à la fermeture.

**Au premier lancement**, Windows SmartScreen peut afficher « Windows a protégé votre ordinateur » : le
programme n'est pas signé. Cliquez sur « Informations complémentaires », puis « Exécuter quand même ».
Pour vérifier le fichier, son empreinte SHA-256 figure sur la page de la version (PowerShell :
`Get-FileHash .\LocalChords-v1.1-portable.exe`).

Pour tout garder à côté du programme (clé USB), créez un fichier vide `LocalChords.portable` à côté de
l'exécutable : voir [docs/PORTABLE.md](docs/PORTABLE.md). Pour désinstaller, supprimez le fichier ou le
dossier ; vos analyses restent dans `%LOCALAPPDATA%\LocalChords` tant que vous ne les effacez pas.

## Utiliser

1. **Glissez un morceau** dans la fenêtre (MP3, WAV, FLAC, M4A, OGG, OPUS…), ou « Ouvrir un morceau ».
   Plusieurs fichiers à la fois : ils sont analysés en arrière-plan et rejoignent les morceaux récents.
2. **L'analyse démarre seule** : comptez une vingtaine de secondes pour une chanson. Le morceau reste
   écoutable pendant ce temps, et « Annuler » arrête tout.
3. **Espace pour écouter.** L'accord en cours s'allume, le suivant est annoncé en haut.
4. **Une erreur ?** Double-cliquez sur l'accord, tapez la correction (`Am7`, `D/F#`, `Sib`, `N.C.`) ou
   choisissez-la parmi les propositions. Un clic droit donne les autres lectures de l'analyse.
5. **C'est enregistré tout seul.** Rouvrez le morceau plus tard : la grille et vos corrections reviennent
   sans nouvelle analyse, même si vous l'ouvrez depuis un autre dossier.

### Pour travailler un morceau

| Quoi | Comment |
|---|---|
| Transposer | `Transposer − +` ou Ctrl + ↑ ↓, jusqu'à ± 12 demi-tons. Le bouton juste à côté choisit si le son suit : « Son transposé » (allumé) ou « Son d'origine » (seule la grille change). La vitesse ne change pas. |
| Capodastre | `Capo − +` : la grille montre les formes à jouer. |
| Ralentir sans changer la hauteur | `Vitesse − +`, de 50 % à 150 %, ou les touches `-` et `+`. |
| Boucler un passage | Sélectionnez des cases (glisser, ou Maj + clic), puis `L`. Ou `A` et `B` pendant l'écoute. Sans sélection, `L` boucle la mesure en cours. |
| Accords simplifiés ou analyse des degrés | `Affichage` → Accords. |
| Dièses ou bémols | `Affichage` → Altérations. |
| Moins de changements parasites | `Affichage` → Accords très courts. |
| Corriger le tempo, la mesure, le décalage | Le bouton `92 BPM · 4 temps`. Clic droit sur une case : « La première mesure commence ici ». Un `?` signale un résultat à vérifier. |
| Corriger la tonalité | Le bouton `Tonalité`. |
| Exporter | `Exporter` : texte, ChordPro ou PDF. |
| Voir ce qui revient | Menu ☰ → Progressions répétées. |
| Deuxième avis | Menu ☰ → Comparer avec : un autre moteur, les passages en désaccord, et vous choisissez. |
| Importer un lien | Accueil → « Importer un lien ». |
| Notes en Do, Ré, Mi | Menu ☰. |

**Raccourcis :** F1 les affiche tous. Espace lecture, ← → temps, Ctrl + ← → mesure, Entrée corriger,
Ctrl + Z annuler.

### Importer un lien

N'importez que ce que vous avez le droit de télécharger : c'est de votre responsabilité, et les
conditions de certains sites l'interdisent. Une vidéo privée ou restreinte est signalée comme telle,
rien ne cherche à le contourner. YouTube change souvent : si l'import cesse de marcher, il faudra une
version plus récente du programme ; pour certaines vidéos, Node.js ou Deno doit aussi être installé.

## Ce qu'il faut savoir sur les résultats

Les accords sont extraits automatiquement : **vérifiez à l'oreille**. Mesures effectives et méthode dans
[docs/BENCHMARKS.md](docs/BENCHMARKS.md). En bref :

- Sur 20 morceaux artificiels annotés (Tiny AAM), 95,8 % du temps en bonnes triades, 92,1 % avec les
  septièmes. Sur 180 prises réelles de guitare (GuitarSet), 90,2 % et 84,8 %.
- Ni l'un ni l'autre n'est un **morceau du commerce** : aucune mesure n'a été faite sur ce type de musique,
  faute d'annotations libres. Attendez-vous à moins bien, surtout avec une voix très présente. Aucune
  équivalence avec Chordify n'est revendiquée : la comparaison n'a pas été faite.
- **Accords reconnus :** majeur, mineur, 7, maj7, m7, m7♭5, °7, °, +, sus2, sus4, 7sus4, et les renversements
  (`C/E`) par la basse. Le moteur ne produit **pas** de 9, 11, 13, 6 ni add9 : ils sont ramenés à
  l'accord le plus proche (`C9` devient `C7`). En correction manuelle, m6, add9 et madd9 sont disponibles.
- **Mesure :** détectée parmi 3, 4, 5, 6 et 7 temps. Vérifiée sur du 4 temps uniquement ; les autres n'ont pas
  d'évaluation sur musique réelle. Le bouton de mesure permet de corriger.
- Le tempo est suivi s'il varie. Un morceau très libre (rubato) reste approximatif.

## Si ça ne marche pas

- **« Sortie audio indisponible »** : vérifiez la sortie son de Windows, puis relancez la lecture.
- **« Mémoire insuffisante »** ou arrêt brutal : l'analyse demande environ 1 Go pour une chanson, 4 Go pour 20 minutes,
  11 Go pour une heure.
- **Autre erreur :** le détail est dans `%LOCALAPPDATA%\LocalChords\log.txt` (en mode portable : `Data\log.txt`).

Vos morceaux analysés sont dans `%LOCALAPPDATA%\LocalChords\projects` : effacer un fichier n'oublie que
son analyse et vos corrections. Les fichiers audio ne sont ni copiés ni modifiés, sauf ceux importés
par lien, gardés dans `%LOCALAPPDATA%\LocalChords\downloads`. En mode portable, tout cela est dans le dossier
`Data` à côté du programme.

## Pour les développeurs

Construire : `scripts\build.ps1`. Tester : `.venv\Scripts\python -m pytest`. Documentation technique :
[docs/TECHNIQUE.md](docs/TECHNIQUE.md). Licences : LocalChords est sous licence MIT ([LICENSE](LICENSE)) ; composants tiers dans
[LICENCES-TIERS.md](LICENCES-TIERS.md).
