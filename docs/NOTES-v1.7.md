# LocalChords v1.7 : en français et en anglais

*English below.*

LocalChords parle maintenant anglais. Toute l'interface, ses messages, ses exports et son installateur
existent en français et en anglais ; l'analyse, la séparation, vos projets et vos réglages ne changent
pas.

## Nouveautés

- **Menu ☰ → Langue / Language** : *Automatique*, *Français* ou *English*. Automatique suit la langue
  d'affichage de Windows (anglais si ce n'est pas le français). Le changement s'applique au prochain
  démarrage ; le choix est gardé.
- **Vous utilisiez déjà LocalChords ?** Il reste en français. Une première installation suit la langue de
  Windows.
- **Tout est traduit** : menus, boutons, bulles d'aide, noms lus par les lecteurs d'écran, messages
  d'erreur, dialogues, mixage, paroles, bibliothèque, mises à jour, fiches PDF et en-têtes des exports
  texte et ChordPro ; les boutons standard de Qt aussi (OK, Annuler…). Les pluriels sont de vrais pluriels
  dans les deux langues, et les nombres s'écrivent à la manière de chaque langue (1,5 Go / 1.5 GB).
- **Vos données ne sont jamais traduites** : titres, artistes, paroles, étiquettes, collections et noms
  d'accords restent tels quels. La notation Do, Ré, Mi reste un réglage à part.
- **Les genres et étiquettes proposés** s'affichent dans la langue de l'interface, et la recherche les
  trouve sous leurs deux noms.
- **Installateur bilingue** : il propose la langue de Windows, et la mise à jour depuis le programme le
  lance dans la langue de l'interface. Même AppId : il se met à jour par-dessus la v1.6.1, dans le même
  dossier, sans toucher à vos données.
- **README en anglais** ([README.en.md](../README.en.md)) avec des captures de l'interface anglaise, et
  des sous-titres anglais pour la vidéo de présentation
  ([docs/video/LocalChords-presentation.en.srt](video/LocalChords-presentation.en.srt)).
- Pour les traducteurs : [LOCALISATION.md](LOCALISATION.md) explique l'architecture (outils natifs de Qt,
  catalogues `.ts` et `.qm` versionnés) et l'ajout d'une troisième langue.

## Ce qui ne change pas

Les moteurs de reconnaissance, de transcription et de séparation, le format des projets et de la
bibliothèque, le dossier de données et le modèle de séparation (toujours un fichier de la publication
v1.6). Une sauvegarde de bibliothèque restaurée garde la langue de l'interface.

## Limites

- La nouvelle langue s'applique au redémarrage, pas immédiatement.
- Seuls le français et l'anglais sont disponibles. Une partie de la documentation technique (`docs/`)
  reste en français.

---

# LocalChords v1.7: in English and French

LocalChords now speaks English. The whole interface, its messages, exports and installer exist in English
and French; analysis, separation, your projects and settings do not change.

- **☰ menu → Langue / Language**: *Automatic*, *Français* or *English*. Automatic follows the Windows
  display language (English unless it is French). The change takes effect at the next start.
- **Already using LocalChords?** It stays in French until you choose otherwise. A new installation
  follows the Windows language.
- **Everything is translated**: menus, buttons, tooltips, screen reader names, error messages, dialogs,
  mixer, lyrics, library, updates, PDF sheets and export headers; Qt's standard buttons too. Plurals and
  numbers follow each language.
- **Your data is never translated**: titles, artists, lyrics, tags, collections and chord names stay as
  they are. Do, Ré, Mi note names remain a separate setting.
- **Bilingual installer**, same AppId: it updates v1.6.1 in place, without touching your data.
- **English README** ([README.en.md](../README.en.md)) and English subtitles for the presentation video.
