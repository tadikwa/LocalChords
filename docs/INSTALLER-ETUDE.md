# Étude : un installateur Windows pour LocalChords

> Étude seulement. La v1.4 ne contient **aucun** installateur et **aucune** mise à jour
> automatique : LocalChords reste distribué en exécutable unique et en dossier zip
> ([PORTABLE.md](PORTABLE.md)).

## Ce qu'un installateur apporterait

- une entrée dans le menu Démarrer et, au choix, sur le bureau ;
- l'ouverture des fichiers `.lchords` par double-clic (association de fichier) ;
- une désinstallation propre depuis les Paramètres de Windows ;
- la forme « dossier » (démarrage immédiat, rien de décompressé dans `%TEMP%`) sans que
  l'utilisateur ait à extraire un zip ni à choisir où le ranger.

Il n'apporte rien à la reconnaissance, ni à la confidentialité : le programme installé est
exactement le dossier `LocalChords\` du zip, produit par la même CI.

## Exigences qu'il devrait respecter

| Exigence | Pourquoi |
|---|---|
| Installation **par utilisateur**, sans droits d'administrateur (`%LOCALAPPDATA%\Programs\LocalChords`) | comme aujourd'hui, rien ne demande l'élévation |
| La désinstallation ne touche **jamais** `%LOCALAPPDATA%\LocalChords` (projets, bibliothèque, sauvegardes, copies conservées) | ce sont les données de l'utilisateur, pas le programme |
| Aucun marqueur `LocalChords.portable` installé | le mode portable reste un choix explicite |
| Mise à jour = nouvelle installation par-dessus, même identifiant d'application | pas de service de mise à jour, pas de tâche planifiée, aucune connexion |
| Les notices et sources tierces (FFmpeg LGPL, modèles, bibliothèques) installées avec le programme | obligations de licence identiques à celles du zip |
| Construit par la CI GitHub Actions existante, gratuitement | aucune dépense |

## Inno Setup ou WiX

| | **Inno Setup 6** | **WiX Toolset (v4 et suivantes)** |
|---|---|---|
| Produit | un `setup.exe` | un paquet `.msi` (et, au besoin, un `.exe` « bundle ») |
| Description | un script `.iss` déclaratif, avec du Pascal Script pour les cas particuliers | des fichiers XML ; le modèle de Windows Installer (composants, GUID, règles de mise à niveau) est à maîtriser |
| Depuis le dossier PyInstaller | une ligne `Source: "dist\LocalChords\*"; Flags: recursesubdirs` | la liste des fichiers est récoltée (`heat` en v3, collecte intégrée en v4+) ; chaque fichier devient un composant |
| Installation par utilisateur | `PrivilegesRequired=lowest`, simple | possible (`Scope="perUser"`), plus délicat à tester |
| Association `.lchords`, raccourcis | quelques lignes | quelques éléments XML |
| Désinstallation | ne supprime que ce qu'il a installé ; les données hors du dossier du programme ne sont pas concernées | idem |
| Déploiement en entreprise (GPO, Intune) | possible (options silencieuses), moins standard | le format attendu par ces outils |
| Prise en main | rapide ; abondamment documenté | plus longue ; plus de risques d'erreur de mise à niveau |
| Licence | gratuite ; conditions d'usage commercial **à relire** au moment du choix (elles ont évolué) | MS-RL ; à partir de la v6, une contribution est demandée aux organisations qui en tirent un revenu (**à relire**) |
| Dans la CI | installable par Chocolatey ou présent sur certaines images Windows de GitHub (**à vérifier**) | outil .NET (`dotnet tool install wix`) |

LocalChords est un logiciel libre (MIT) sans revenu : les deux restent utilisables sans frais, mais
leurs conditions doivent être relues le jour où l'installateur est réellement fait.

## Signature et SmartScreen

Un installateur non signé déclenche l'avertissement SmartScreen (« Windows a protégé votre
ordinateur »), comme l'exécutable actuel. Un certificat de signature de code est payant, ce qui est
exclu. Une piste gratuite pour les projets libres existe (par exemple SignPath Foundation, sur
dossier) ; elle demande une candidature et une CI vérifiable, et n'est pas un prérequis de
l'installateur.

## Recommandation

**Inno Setup**, le jour où un installateur sera fait :

1. il part directement du dossier `dist\LocalChords` que la CI produit déjà ;
2. l'installation par utilisateur, sans administrateur, est son cas le plus simple ;
3. un seul script court, lisible et relu en même temps que le reste.

WiX ne se justifierait que si un déploiement en entreprise par MSI était demandé.

## Ce qui reste à faire avant de s'y mettre

- relire les licences d'Inno Setup et de WiX à la date du choix ;
- décider si l'exécutable unique et le zip restent publiés à côté (recommandé : oui, ils ne
  demandent aucune installation et restent la forme portable) ;
- tester une installation, une mise à jour par-dessus et une désinstallation sur un compte sans
  droits d'administrateur, en vérifiant que `%LOCALAPPDATA%\LocalChords` est intact après chacune.
