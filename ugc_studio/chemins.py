"""Emplacements des fichiers de l'app (cahier des charges §10).

- Données de l'app (styles, préréglages, prix, historique des coûts, préférences) :
  %APPDATA%\\UGC Studio\\
- Journal d'erreurs : %APPDATA%\\UGC Studio\\journal\\
- Ressources embarquées dans le .exe (police Inter, icônes) : dossier « ressources » du code.
- Programmes recopiés par l'app (FFmpeg, V3) : %LOCALAPPDATA%\\UGC Studio\\

Pour les tests automatiques, la variable d'environnement UGC_STUDIO_DOSSIER_DONNEES
permet d'utiliser un dossier temporaire au lieu du vrai dossier de données.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import NOM_APP

VARIABLE_DOSSIER_DONNEES = "UGC_STUDIO_DOSSIER_DONNEES"
VARIABLE_DOSSIER_PROGRAMMES = "UGC_STUDIO_DOSSIER_PROGRAMMES"  # autotest : FFmpeg recopié hors du rapport


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


def dossier_programmes() -> Path:
    """Programmes recopiés par l'app (FFmpeg, V3) : %LOCALAPPDATA%\\UGC Studio\\.

    Pas dans %APPDATA% (les données), qui peut suivre l'utilisateur d'un ordinateur à l'autre dans
    une entreprise : 100 Mo de programme n'ont rien à y faire. Tests : dans leur dossier temporaire."""
    force = os.environ.get(VARIABLE_DOSSIER_PROGRAMMES)
    if force:
        return _creer(Path(force))
    force = os.environ.get(VARIABLE_DOSSIER_DONNEES)
    if force:
        return _creer(Path(force) / "programmes")
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        return _creer(Path(os.environ["LOCALAPPDATA"]) / NOM_APP)
    return _creer(Path.home() / ".cache" / NOM_APP)


def dossier_documents() -> Path:
    """Dossier « Documents » de l'utilisateur, même s'il a été déplacé (ex. vers OneDrive)."""
    if sys.platform == "win32":
        try:
            import ctypes
            import uuid
            from ctypes import wintypes

            # Identifiant Windows du dossier Documents (FOLDERID_Documents).
            identifiant = uuid.UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")

            class GUID(ctypes.Structure):
                _fields_ = [("donnees", ctypes.c_byte * 16)]

            guid = GUID()
            ctypes.memmove(guid.donnees, identifiant.bytes_le, 16)
            chemin = ctypes.c_wchar_p()
            fonction = ctypes.windll.shell32.SHGetKnownFolderPath
            fonction.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
            if fonction(ctypes.byref(guid), 0, None, ctypes.byref(chemin)) == 0 and chemin.value:
                resultat = Path(chemin.value)
                ctypes.windll.ole32.CoTaskMemFree(chemin)
                return resultat
        except (AttributeError, OSError, ValueError):
            pass
    return Path.home() / "Documents"


def dossier_projets_defaut() -> Path:
    """Emplacement proposé pour les nouveaux projets (§10) : Documents\\UGC Studio\\Projets."""
    force = os.environ.get(VARIABLE_DOSSIER_DONNEES)
    if force:  # tests automatiques : tout reste dans le dossier temporaire
        return Path(force) / "Projets"
    return dossier_documents() / NOM_APP / "Projets"


def dossier_ressources() -> Path:
    """Ressources embarquées (polices, icônes).

    Dans le .exe, PyInstaller les place au même endroit relatif qu'ici,
    à côté du code : ce chemin fonctionne donc dans les deux cas.
    """
    return Path(__file__).absolute().parent / "ressources"


# « Espace de largeur nulle » : invisible, il indique seulement qu'une ligne peut se couper là.
COUPURE_INVISIBLE = "​"


def chemin_a_afficher(chemin: str | Path) -> str:
    """Un chemin de fichier à afficher dans un texte qui passe à la ligne (3.2.2) : la ligne peut se
    couper après chaque « \\ » ou « / », sans que rien ne se voie. Qt ne coupe une ligne qu'aux
    espaces et aux tirets : d'un seul tenant, un long chemin élargissait sa colonne (une vidéo
    introuvable décalait ainsi la vidéo de l'aperçu par rapport au titre du bloc). Pour un texte
    qu'on peut sélectionner et copier, garder le chemin tel quel."""
    texte = str(chemin)
    for separateur in ("\\", "/"):
        texte = texte.replace(separateur, separateur + COUPURE_INVISIBLE)
    return texte
