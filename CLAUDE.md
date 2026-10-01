# Consignes pour Claude : UGC Studio

- La référence du projet est `docs/CAHIER_DES_CHARGES.md`. Le lire avant tout travail ; le mettre à jour quand une décision change.
- L'utilisateur débute en programmation et n'utilise pas de terminal : expliquer le pourquoi de chaque étape, en français, sans jargon non expliqué.
- Présenter les changements de code de façon ciblée (ce qui change et pourquoi).
- Corriger la cause d'un problème plutôt que le contourner.
- Ne jamais écrire de clé API dans le code, les fichiers de projet, les logs ou le dépôt.
- Toutes les valeurs d'interface (couleurs, espacements, tailles) viennent de `ugc_studio/ui/theme.py`.
- Avant d'écrire ou modifier un adaptateur d'API, vérifier la documentation officielle à jour du fournisseur.

## Façon de travailler (voir aussi §12.1 et §14 du cahier des charges)

- Une étape = une branche + une Pull Request dont la description explique ce qui change et pourquoi. Claude fusionne lui-même la PR quand la fabrication automatique est verte, publie l'étape et enchaîne sans attendre la validation de l'utilisateur (il teste quand il est disponible).
- Chaque étape augmente la version dans `ugc_studio/__init__.py` : la fusion sur `main` publie alors automatiquement une Release avec le `.exe`.
- La fabrication automatique (`.github/workflows/fabrication.yml`, Windows) lance les tests, fabrique le `.exe`, le démarre en mode `--autotest` et joint un artifact « rapport » (captures d'écran, `autotest.json`, versions). Regarder les captures avant de fusionner.
- Le test `tests/test_regles_design.py` refuse toute couleur, taille ou marge écrite hors de `theme.py`.
- Dépendances figées dans `requirements*.txt` (versions exactes).
