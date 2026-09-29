"""Lecture et écriture des fichiers JSON de l'app (cahier des charges §2 : données locales en JSON).

Deux règles de sécurité :
- l'écriture est « atomique » : on écrit d'abord un fichier temporaire, puis on le met à la
  place de l'ancien en une seule opération. Si l'app ou l'ordinateur s'arrête pendant
  l'écriture, l'ancien fichier reste intact au lieu d'être à moitié écrit ;
- un fichier illisible n'est jamais écrasé : il est renommé « .illisible-<date> » pour
  pouvoir le récupérer, et l'app repart des valeurs par défaut.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

journal = logging.getLogger(__name__)

_ESSAIS_REMPLACEMENT = 5
_PAUSE_ENTRE_ESSAIS = 0.1  # secondes


def lire_json(chemin: Path, defaut: Any) -> Any:
    """Contenu du fichier, ou `defaut` si le fichier n'existe pas ou est illisible."""
    try:
        with open(chemin, encoding="utf-8") as fichier:
            return json.load(fichier)
    except FileNotFoundError:
        return defaut
    except (json.JSONDecodeError, UnicodeDecodeError) as erreur:
        horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
        copie = chemin.with_name(f"{chemin.name}.illisible-{horodatage}")
        with contextlib.suppress(OSError):
            os.replace(chemin, copie)
        journal.warning("Fichier illisible mis de côté : %s → %s (%s)", chemin, copie.name, erreur)
        return defaut


def ecrire_json(chemin: Path, donnees: Any) -> None:
    """Écrit `donnees` dans le fichier, de façon atomique (voir en haut du fichier)."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    descripteur, temporaire = tempfile.mkstemp(prefix=f".{chemin.name}.", suffix=".tmp", dir=chemin.parent)
    try:
        with os.fdopen(descripteur, "w", encoding="utf-8") as fichier:
            json.dump(donnees, fichier, ensure_ascii=False, indent=2)
            fichier.flush()
            os.fsync(fichier.fileno())
        _remplacer(Path(temporaire), chemin)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporaire)
        raise


def _remplacer(source: Path, cible: Path) -> None:
    # Sous Windows, un antivirus ou l'indexation peut bloquer le fichier un court instant :
    # on réessaie quelques fois avant d'abandonner.
    for essai in range(_ESSAIS_REMPLACEMENT):
        try:
            os.replace(source, cible)
            return
        except PermissionError:
            if essai == _ESSAIS_REMPLACEMENT - 1:
                raise
            time.sleep(_PAUSE_ENTRE_ESSAIS)
