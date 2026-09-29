"""Emplacements des fichiers de l'app (cahier des charges §10).

- Données de l'app (styles, préréglages, prix, historique des coûts, préférences) :
  %APPDATA%\\UGC Studio\\
- Journal d'erreurs : %APPDATA%\\UGC Studio\\journal\\
- Ressources embarquées dans le .exe (police Inter, icônes) : dossier « ressources » du code.

Pour les tests automatiques, la variable d'environnement UGC_STUDIO_DOSSIER_DONNEES
permet d'utiliser un dossier temporaire au lieu du vrai dossier de données.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import NOM_APP

VARIABLE_DOSSIER_DONNEES = "UGC_STUDIO_DOSSIER_DONNEES"


def _creer(dossier: Path) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def dossier_donnees() -> Path:
    """Dossier des données de l'app, créé s'il n'existe pas encore."""
    force = os.environ.get(VARIABLE_DOSSIER_DONNEES)
    if force:
        return _creer(Path(force))
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        return _creer(Path(os.environ["APPDATA"]) / NOM_APP)
    # Hors Windows (développement, tests automatiques) : ~/.config/UGC Studio
    return _creer(Path.home() / ".config" / NOM_APP)


def dossier_journal() -> Path:
    return _creer(dossier_donnees() / "journal")


def fichier_journal() -> Path:
    return dossier_journal() / "ugc-studio.log"


def fichier_preferences() -> Path:
    return dossier_donnees() / "preferences.json"


def dossier_cache() -> Path:
    """Fichiers recréables à tout moment (ex. icônes recolorées pour le thème)."""
    return _creer(dossier_donnees() / "cache")


def dossier_ressources() -> Path:
    """Ressources embarquées (polices, icônes).

    Dans le .exe, PyInstaller les place au même endroit relatif qu'ici,
    à côté du code : ce chemin fonctionne donc dans les deux cas.
    """
    return Path(__file__).absolute().parent / "ressources"
