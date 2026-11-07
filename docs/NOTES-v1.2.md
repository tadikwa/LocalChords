# LocalChords v1.2 : diagrammes d'accords

## Nouveautés

- **Diagrammes de guitare et de piano** dans un panneau à droite de la grille (sous la grille dans une fenêtre
  étroite). Trois modes : Guitare, Piano, Les deux. Le panneau peut être complet, réduit ou masqué (touche
  `D`), et l'application s'en souvient.
- **Suit la lecture** : le diagramme change avec l'accord joué. Un clic sur un accord de la grille (ou
  `Maj + D`) l'épingle, et `← →` déplacent l'épingle ; « Suivre la lecture », `Échap` ou la reprise de la
  lecture reviennent au suivi. Le double-clic corrige toujours l'accord.
- **Guitare** : cordes, cases, doigts 1 à 4, cordes à vide et étouffées, barrés, plusieurs positions à
  parcourir (formes ouvertes classiques en premier, par exemple x24432 pour Si mineur). Accords renversés
  (D/F♯) avec la bonne basse. Quand aucune position jouable n'existe, le panneau le dit au lieu de dessiner
  une forme fausse.
- **Capo** : le diagramme montre la forme à jouer, et le panneau indique le son réel (« forme de C, son réel D »).
  En mode Piano, le titre est le son réel et le panneau rappelle la forme de guitare.
- La basse d'un accord renversé porte le même nom dans la grille et dans les diagrammes (E/G♯, pas E/A♭).
- **Piano** : touches de l'accord en couleur, noms des notes dans la notation choisie (Do ré mi ou C D E),
  position fondamentale et renversements, basse demandée toujours la plus grave, et une répartition main
  gauche / main droite proposée à titre indicatif.
- Les diagrammes suivent la transposition, le capo, les corrections, la notation, le choix dièses / bémols, et
  reviennent tels quels à la réouverture d'un projet. « N.C. » affiche un panneau vide.

## Justesse

Aucune position n'est dessinée parce qu'elle « a l'air juste » : chaque position de guitare et chaque
disposition de piano est recalculée note par note et comparée à l'accord demandé (411 tests sur toutes les
qualités, toutes les fondamentales, renversements et capos). Les diagrammes sont dessinés par le programme ;
aucune police, image ni base de doigtés extérieure n'a été ajoutée.

## Limites

- Accordage standard uniquement (mi la ré sol si mi).
- Doigtés calculés et vérifiés par leurs notes, pas relus un à un par un guitariste.
- Comme en v1.1, la fenêtre ne descend pas sous environ 1000 px de large.

## Téléchargements

| Fichier | Pour qui |
|---|---|
| `LocalChords-v1.2-portable.exe` | un seul fichier à lancer, plus lent au démarrage |
| `LocalChords-v1.2-windows-x64.zip` | dossier à décompresser, démarrage rapide : forme recommandée |
| `LocalChords-v1.2-sources-tierces.zip` | sources de FFmpeg et PyAV (LGPL), pour qui veut les recompiler |
| `SHA256SUMS.txt` | empreintes pour vérifier les téléchargements |

Windows 10 ou 11, 64 bits. Tout fonctionne hors ligne, rien n'est envoyé. Le programme n'est pas signé :
SmartScreen peut avertir (« Informations complémentaires », puis « Exécuter quand même »).

Vérifier un fichier sous PowerShell :

```powershell
Get-FileHash .\LocalChords-v1.2-windows-x64.zip -Algorithm SHA256
```
