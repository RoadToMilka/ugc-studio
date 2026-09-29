"""Petites préférences d'interface (taille de la fenêtre, dernier module ouvert…).

Elles sont rangées dans %APPDATA%\\UGC Studio\\preferences.json.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .stockage import ecrire_json, lire_json


class Preferences:
    VERSION_FORMAT = 1  # à augmenter si la structure du fichier change un jour

    def __init__(self, chemin: Path):
        self._chemin = chemin
        donnees = lire_json(chemin, {})
        self._donnees: dict[str, Any] = donnees if isinstance(donnees, dict) else {}

    def lire(self, cle: str, defaut: Any = None) -> Any:
        return self._donnees.get(cle, defaut)

    def ecrire(self, cle: str, valeur: Any) -> None:
        self._donnees[cle] = valeur

    def enregistrer(self) -> None:
        self._donnees["version_format"] = self.VERSION_FORMAT
        ecrire_json(self._chemin, self._donnees)
