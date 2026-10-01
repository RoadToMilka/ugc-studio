# UGC Studio

Application Windows pour créer des publicités UGC / influenceur : scripts écrits avec un modèle de texte à partir de la page produit, voix off (TTS), transcription (STT) et sous-titres animés, avec export SRT, overlay transparent ProRes 4444 ou vidéo finale.

- Cahier des charges : [docs/CAHIER_DES_CHARGES.md](docs/CAHIER_DES_CHARGES.md)
- **Télécharger l'app** : section **Releases** du dépôt → `UGC-Studio.exe`. Les versions `0.x` sont les étapes de construction de la V1 (marquées « Pre-release »).

Au premier lancement, Windows affiche « Windows a protégé votre ordinateur » (le `.exe` n'est pas signé) : *Informations complémentaires* → *Exécuter quand même*.

## Comment le projet est organisé

| Dossier / fichier | Rôle |
|---|---|
| `ugc_studio/` | Le code de l'app (Python) |
| `ugc_studio/ui/theme.py` | **Toutes** les couleurs, tailles et espacements de l'interface (§9) |
| `ugc_studio/ecriture/` | Le module Script, sans interface : lecture de la page produit, brief, consignes du modèle, relecture, exemples |
| `ugc_studio/ui/` | L'interface : fenêtre principale, pages, composants réutilisables |
| `ugc_studio/ressources/` | Police Inter, icônes (Lucide) et icône de l'app, embarquées dans le `.exe` |
| `tests/` | Tests automatiques, lancés à chaque envoi de code |
| `packaging/ugc_studio.spec` | Recette de fabrication du `.exe` (PyInstaller) |
| `.github/workflows/fabrication.yml` | Fabrication automatique sur une machine Windows de GitHub |
| `outils/` | Petits outils de développement (ex. génération de l'icône) |

## Comment une nouvelle version est fabriquée

Rien n'est à faire à la main : à chaque envoi de code, GitHub lance les tests, fabrique `UGC-Studio.exe`, le démarre pour vérifier qu'il fonctionne et fait des captures d'écran (onglet **Actions**). Quand le numéro de version change sur la branche `main`, une Release est publiée avec le `.exe`.
