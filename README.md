# UGC Studio

Application Windows pour créer des publicités UGC / influenceur : scripts écrits avec un modèle de texte à partir de la page produit, voix off (TTS), transcription (STT) et sous-titres animés, avec export SRT, calque transparent ProRes 4444 pour Premiere Pro, ou vidéo finale.

- Cahier des charges : [docs/CAHIER_DES_CHARGES.md](docs/CAHIER_DES_CHARGES.md)
- **Télécharger l'app** : section **Releases** du dépôt → `UGC-Studio.exe`. Les versions `0.x` sont les étapes de construction de la V1 (marquées « Pre-release »).

Au premier lancement, Windows affiche « Windows a protégé votre ordinateur » (le `.exe` n'est pas signé) : *Informations complémentaires* → *Exécuter quand même*.

## Comment le projet est organisé

| Dossier / fichier | Rôle |
|---|---|
| `ugc_studio/` | Le code de l'app (Python) |
| `ugc_studio/ui/theme.py` | **Toutes** les couleurs, tailles et espacements de l'interface (§9) |
| `ugc_studio/ecriture/` | Le module Script, sans interface : lecture de la page produit, brief, consignes du modèle, relecture, exemples, variantes, retouche, bibliothèque de briefs |
| `ugc_studio/sous_titres.py`, `style_sous_titres.py`, `mise_en_page.py`, `prereglages.py` | Les sous-titres, sans interface : découpage, style (forme écrite des projets et des préréglages), place des lignes et des mots, préréglages (les 6 fournis, ★ des nouveaux projets, export et import) |
| `ugc_studio/rendu/` | Le moteur de dessin des sous-titres, commun à l'aperçu et aux exports vidéo, et les polices des sous-titres (fournies, importées, de Windows) |
| `ugc_studio/exports/` | Les exports vidéo (V3) : fréquences exactes, commandes données à FFmpeg, résumé avant export, images du calque transparent |
| `ugc_studio/ui/` | L'interface : fenêtre principale, pages, composants réutilisables |
| `ugc_studio/ressources/` | Polices (Inter pour l'interface ; Montserrat, Poppins, Anton et Bebas Neue pour les sous-titres, licence SIL OFL), style de départ et préréglages fournis des sous-titres, icônes (Lucide) et icône de l'app, licence de FFmpeg, embarqués dans le `.exe` |
| `tests/` | Tests automatiques, lancés à chaque envoi de code |
| `packaging/ugc_studio.spec` | Recette de fabrication du `.exe` (PyInstaller) |
| `.github/workflows/fabrication.yml` | Fabrication automatique sur une machine Windows de GitHub |
| `outils/` | Petits outils de développement (ex. génération de l'icône) et préparation de FFmpeg pour la fabrication (version 9.0.2 de gyan.dev, empreinte SHA-256 vérifiée) |

## Comment une nouvelle version est fabriquée

Rien n'est à faire à la main : à chaque envoi de code, GitHub prépare FFmpeg (version figée, empreinte vérifiée), lance les tests, fabrique `UGC-Studio.exe`, le démarre pour vérifier qu'il fonctionne (captures d'écran et vrais exports vidéo, relus image par image) et mesure son temps de démarrage (onglet **Actions**). Quand le numéro de version change sur la branche `main`, une Release est publiée avec le `.exe`.

FFmpeg (licence GPL version 3) est fourni avec l'app pour écrire les fichiers vidéo : sa licence et l'adresse de son code source sont dans `ugc_studio/ressources/ffmpeg/` et dans Réglages, « Journal et données », « À propos ».
