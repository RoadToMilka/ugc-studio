"""Fichiers d'un dossier, dans l'ordre de l'Explorateur Windows (V4 : modules Images et Renommer).

Deux règles, les mêmes dans les deux modules :
- seuls les fichiers du dossier lui-même comptent, pas ceux de ses sous-dossiers ; les fichiers cachés
  de Windows (Thumbs.db, desktop.ini, et tout fichier marqué « caché » ou « système ») sont ignorés ;
- l'ordre est celui de l'Explorateur : les nombres d'un nom comptent comme des nombres (« photo2 »
  avant « photo10 », alors qu'un tri alphabétique simple mettrait « photo10 » avant « photo2 »), sans
  tenir compte des majuscules. Sous Windows, c'est la fonction même de l'Explorateur (StrCmpLogicalW)
  qui compare les noms ; ailleurs (tests), un tri qui la reproduit.
"""

from __future__ import annotations

import os
import re
import stat
import sys
from collections.abc import Iterable
from functools import cmp_to_key
from pathlib import Path

# Formats d'image que les modules Images et Renommer savent lire (Pillow). Pas le GIF : une image
# animée perdrait son animation.
EXTENSIONS_IMAGES = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".tif", ".tiff", ".bmp")

# Fichiers que Windows range lui-même dans les dossiers (aperçus, réglages d'affichage).
FICHIERS_DE_WINDOWS = {"thumbs.db", "desktop.ini", "ehthumbs.db", ".ds_store"}

_CACHE_OU_SYSTEME = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 2) | getattr(stat, "FILE_ATTRIBUTE_SYSTEM", 4)
_MORCEAUX = re.compile(r"(\d+)")


def est_cache(chemin: Path) -> bool:
    """Fichier caché ou système (attribut de Windows), ou fichier rangé là par Windows ou macOS."""
    if chemin.name.lower() in FICHIERS_DE_WINDOWS or chemin.name.startswith("."):
        return True
    try:
        attributs = getattr(chemin.stat(), "st_file_attributes", 0)
    except OSError:
        return True  # illisible : on n'y touche pas
    return bool(attributs & _CACHE_OU_SYSTEME)


def _cle_naturelle(nom: str) -> tuple:
    """« Photo10.jpg » → ("photo", 10, ".jpg") : les nombres comparés comme des nombres."""
    morceaux = _MORCEAUX.split(nom.casefold())
    return tuple(int(morceau) if index % 2 else morceau for index, morceau in enumerate(morceaux))


def _comparer_comme_l_explorateur():
    """La comparaison de l'Explorateur Windows (StrCmpLogicalW), ou None hors de Windows."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        fonction = ctypes.windll.shlwapi.StrCmpLogicalW
        fonction.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p)
        fonction.restype = ctypes.c_int
        return fonction
    except (AttributeError, OSError):
        return None


def trier_comme_l_explorateur(chemins: Iterable[Path]) -> list[Path]:
    """Les chemins dans l'ordre de l'Explorateur Windows (voir en haut du fichier)."""
    chemins = list(chemins)
    comparer = _comparer_comme_l_explorateur()
    if comparer is not None:
        return sorted(chemins, key=cmp_to_key(lambda a, b: comparer(a.name, b.name)))
    return sorted(chemins, key=lambda chemin: (_cle_naturelle(chemin.name), chemin.name))


def fichiers_du_dossier(dossier: Path, extensions: Iterable[str] | None = None) -> list[Path]:
    """Les fichiers du dossier (pas ceux de ses sous-dossiers, pas les fichiers cachés), dans l'ordre
    de l'Explorateur. `extensions` : seulement ceux-là (ex. EXTENSIONS_IMAGES), en minuscules."""
    acceptees = {extension.lower() for extension in extensions} if extensions is not None else None
    trouves = []
    try:
        entrees = list(os.scandir(dossier))
    except OSError:
        return []
    for entree in entrees:
        try:
            if not entree.is_file(follow_symlinks=False):
                continue
        except OSError:
            continue
        chemin = Path(entree.path)
        if acceptees is not None and chemin.suffix.lower() not in acceptees:
            continue
        if est_cache(chemin):
            continue
        trouves.append(chemin)
    return trier_comme_l_explorateur(trouves)


def images_du_dossier(dossier: Path) -> list[Path]:
    """Les images du dossier (voir EXTENSIONS_IMAGES), dans l'ordre de l'Explorateur."""
    return fichiers_du_dossier(dossier, EXTENSIONS_IMAGES)
