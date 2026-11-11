# L'installateur Windows (depuis la v1.5)

`LocalChords-Setup-v1.5.exe` installe le dossier `LocalChords\` du zip, produit par la même CI,
pour **votre compte uniquement**, **sans droits d'administrateur**. Il est construit avec
[Inno Setup](https://jrsoftware.org/isinfo.php) 6.7.3 à partir de
[`installer/LocalChords.iss`](../installer/LocalChords.iss).

L'exécutable unique et le zip restent publiés : ils ne demandent aucune installation et restent la
forme portable ([PORTABLE.md](PORTABLE.md)).

## Ce qu'il fait

| | |
|---|---|
| Dossier du programme | `%LOCALAPPDATA%\Programs\LocalChords` par défaut ; un autre dossier peut être choisi |
| Menu Démarrer | une entrée « LocalChords » |
| Bureau | un raccourci, seulement si la case est cochée (décochée par défaut) |
| Projets `.lchords` | s'ouvrent avec LocalChords par double-clic (case cochée par défaut, décochable) |
| Applications installées | une entrée « LocalChords » dans Paramètres → Applications, pour désinstaller |
| Fin de l'installation | propose de lancer LocalChords |

## Langue (depuis la v1.7)

L'assistant est en anglais et en français, par le mécanisme officiel d'Inno Setup (`[Languages]` :
`Default.isl` pour l'anglais, `Languages\French.isl` pour le français ; les textes propres à LocalChords
dans `[CustomMessages]`). Au lancement, il propose la langue de Windows si c'est l'une des deux, et
demande sinon (`ShowLanguageDialog=auto`). `/LANG=english` ou `/LANG=french` choisit sans demander : c'est
ce que fait la mise à jour depuis le programme, dans la langue de l'interface. La langue de l'assistant
ne change rien à celle de LocalChords (menu ☰ → Langue / Language), ni à l'AppId, au dossier ou aux
données.

## Ce qu'il ne fait jamais

- Il ne touche **jamais** à `%LOCALAPPDATA%\LocalChords` : projets, bibliothèque, sauvegardes,
  copies conservées, préférences, modèles téléchargés. Ni l'installation, ni la mise à jour, ni la
  désinstallation n'y écrivent ou n'y suppriment quoi que ce soit.
- Il refuse d'installer le programme dans ce dossier de données (ou dans un dossier qui le
  contient), et dans un dossier qui contient un `LocalChords.portable`.
- Il n'installe pas de marqueur `LocalChords.portable` : la version installée garde ses données
  dans `%LOCALAPPDATA%\LocalChords`.
- Aucun service Windows, aucune tâche planifiée, aucune télémétrie, aucune mise à jour automatique,
  aucune connexion réseau.
- Il ne demande pas l'élévation et n'écrit que dans votre profil (`HKEY_CURRENT_USER`).

## Mettre à jour

Lancez l'installateur de la nouvelle version : il reprend le dossier déjà choisi, remplace le
programme entier (aucun fichier de l'ancienne version ne subsiste dans `_internal`) et laisse vos
données telles quelles. Si LocalChords est ouvert, l'installateur propose de le fermer.

## Désinstaller

Paramètres → Applications → LocalChords → Désinstaller. Le programme, ses raccourcis et
l'association `.lchords` sont retirés. Vos données restent dans `%LOCALAPPDATA%\LocalChords` et
l'assistant vous le rappelle.

**Supprimer aussi vos données** (définitif, à faire vous-même) : fermez LocalChords, tapez
`%LOCALAPPDATA%` dans la barre d'adresse de l'Explorateur, puis supprimez le dossier `LocalChords`.
Pensez d'abord à une sauvegarde de la bibliothèque (menu Options de la bibliothèque) si vous
comptez réinstaller un jour.

## Installation silencieuse

```
LocalChords-Setup-v1.5.exe /VERYSILENT /SUPPRESSMSGBOXES /DIR="D:\Programmes\LocalChords" /TASKS="association,desktopicon"
```

`/TASKS=""` n'ajoute ni raccourci de bureau ni association. Un dossier refusé (voir plus haut)
arrête l'installation avec le code de sortie 7, sans rien copier.

## SmartScreen : l'installateur n'est pas signé

Un certificat de signature de code est payant ; LocalChords n'en a pas. Au premier lancement,
Windows peut afficher « Windows a protégé votre ordinateur ». Pour continuer : **Informations
complémentaires**, puis **Exécuter quand même**. Avant cela, vous pouvez vérifier que le fichier est
bien celui de la publication : son empreinte SHA-256 figure dans `SHA256SUMS.txt`.

```
Get-FileHash LocalChords-Setup-v1.5.exe -Algorithm SHA256
```

## Licences

- Inno Setup est distribué sous sa propre licence, qui en permet l'usage pour tout logiciel, y
  compris commercial, sans frais ([texte](https://jrsoftware.org/files/is/license.txt), relu le
  8 novembre 2026). L'outil n'est utilisé que pour fabriquer l'installateur.
- Le programme installé est identique au zip : mêmes fichiers, mêmes notices tierces
  (`_internal\LICENCES-TIERS.md`, `_internal\licences\`) et même FFmpeg LGPL, dont les sources sont
  dans `LocalChords-v1.5-sources-tierces.zip`.
- La CI télécharge l'installateur d'Inno Setup 6.7.3 depuis la publication officielle
  (`github.com/jrsoftware/issrc`) et vérifie son empreinte SHA-256 avant de s'en servir.

## Essais réalisés (v1.5)

Sur Windows 11, compte sans élévation, avec un dossier de données de test séparé :

| Essai | Résultat |
|---|---|
| Installation dans un dossier dont le chemin contient une espace | fichiers identiques au dossier du zip, licences comprises ; entrée « Applications », menu Démarrer, bureau, association |
| Réinstallation de la même version | reprend le dossier choisi, code 0 |
| Mise à jour pendant que LocalChords est ouvert | le Gestionnaire de redémarrage ferme l'application ; ancien fichier de `_internal` retiré ; fichier personnel posé à côté du programme conservé ; version mise à jour dans « Applications » |
| Auto-test du programme installé (données vides) | 17 vérifications sur 17 |
| Désinstallation | programme, raccourcis, entrée et clés de registre retirés ; le fichier personnel reste |
| Installation par défaut puis désinstallation | `%LOCALAPPDATA%\Programs\LocalChords` créé puis retiré entièrement |
| Dossier contenant `LocalChords.portable` | refusé, rien copié (code 7 en silencieux) |
| Dossier de données `%LOCALAPPDATA%\LocalChords` | liste des fichiers (tailles et dates) identique avant et après tous les essais |
