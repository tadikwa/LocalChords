# Mode portable et exécutable unique

## Deux formes du même programme

| Forme | Fichier | Démarrage | Quand la choisir |
|---|---|---|---|
| **Exécutable unique** | `LocalChords-v1.1-portable.exe` | se décompresse à chaque lancement dans `%TEMP%\_MEIxxxxxx`, effacé à la fermeture | un seul fichier à copier |
| **Dossier** | `LocalChords-v1.1-windows-x64.zip` → `LocalChords\LocalChords.exe` + `_internal\` | immédiat, rien n'est décompressé | lancement plus rapide, aucune écriture dans `%TEMP%` |

Les deux contiennent exactement le même programme et les mêmes modèles, et donnent les mêmes accords.
Aucun des deux n'a besoin de Python ni d'une installation. Le temps de démarrage et la place prise
dans `%TEMP%` sont mesurés dans [BENCHMARKS.md](BENCHMARKS.md).

Le dossier temporaire de l'exécutable unique ne contient que le programme. Les préférences, les
analyses, les téléchargements et le journal n'y sont **jamais** écrits : ils vont dans l'un des deux
emplacements ci-dessous.

## Où vont les données

| Mode | Emplacement | Comment l'obtenir |
|---|---|---|
| Classique (par défaut) | `%LOCALAPPDATA%\LocalChords` | rien à faire |
| Portable | dossier `Data` à côté de l'exécutable | créer un fichier vide `LocalChords.portable` à côté de l'exécutable |

Exemple sur une clé USB :

```
E:\LocalChords\
    LocalChords-v1.1-portable.exe
    LocalChords.portable      ← le marqueur (vide, son contenu est ignoré)
    Data\                     ← créé au premier lancement
        projects\             analyses et corrections (.lchords)
        downloads\            morceaux importés par lien
        cache\                cache de calcul (peut être supprimé)
        settings.json         préférences
        log.txt               erreurs éventuelles
```

Le mode portable est explicite : sans le marqueur, le programme garde le comportement Windows
classique, même lancé depuis une clé. Le marqueur se place à côté de `LocalChords.exe`, dans le
dossier du programme (pour la forme en dossier, à côté de `_internal`, pas dedans). En mode portable,
l'écran d'accueil l'indique (« Mode portable : tout reste dans le dossier Data… »).

La variable d'environnement `LOCALCHORDS_DATA`, si elle est définie, l'emporte sur les deux.

## Aucune migration automatique

Passer d'un mode à l'autre ne copie, ne déplace et ne supprime rien. Les analyses faites en mode
classique restent dans `%LOCALAPPDATA%\LocalChords` et n'apparaissent pas en mode portable, et
inversement. Pour emporter des analyses existantes, copiez vous-même le contenu de
`%LOCALAPPDATA%\LocalChords\projects` dans `Data\projects` (le programme fermé). Un projet garde le
chemin du fichier audio d'origine ; s'il n'est plus là, LocalChords propose de le retrouver.

## Support en lecture seule ou plein

| Situation | Comportement |
|---|---|
| `Data` ne peut pas être créé ou écrit (clé protégée en écriture, CD, droits insuffisants) | au démarrage, une fenêtre l'explique et propose d'utiliser **pour cette session** les données de ce PC (`%LOCALAPPDATA%\LocalChords`). « Non » ferme le programme sans rien écrire. Rien n'est copié. |
| Moins de 200 Mo libres là où vont les données | avertissement au démarrage : les analyses existantes s'ouvrent, mais une sauvegarde ou l'import d'un lien peut échouer. |
| Le support se remplit pendant l'utilisation | la sauvegarde d'une analyse échoue avec un message, et le fichier précédent reste entier (écriture atomique). Une préférence non enregistrée est simplement perdue. |

L'exécutable unique se décompresse dans `%TEMP%` du PC, pas sur la clé : une clé en lecture seule
convient donc pour le lancer, à condition d'accepter les données de ce PC pour la session.

## Construire

```
scripts\build.ps1
```

produit les deux formes : `dist\LocalChords\` (dossier) et `dist\onefile\LocalChords.exe`
(exécutable unique). `LOCALCHORDS_TORCH_BUILD=1` reconstruit l'ancienne version, avec torch.
