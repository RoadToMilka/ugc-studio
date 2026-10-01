"""Polices des sous-titres (V2, lot 4 ; cahier des charges §7.4) : fournies avec l'app, importées, ou
installées sur Windows.

- Fournies (licence SIL OFL, libres pour un usage commercial) : Montserrat, Poppins, Anton, Bebas
  Neue et Inter, dans ressources/polices (chargées au démarrage avec Inter, voir ui/polices.py).
- Importées (« Importer une police… », .ttf ou .otf) : copiées dans le dossier de l'app
  (%APPDATA%\\UGC Studio\\polices\\), pour qu'un projet les garde même si le fichier d'origine est
  déplacé ; chargées à chaque démarrage.
- De Windows : celles que Qt trouve sur l'ordinateur.

Particularité de Windows (comme pour Inter) : selon la façon dont il lit les fichiers, les graisses
d'une police peuvent être rangées sous des familles à part (« Montserrat ExtraBold »). Le style
retient toujours la famille de base (« Montserrat ») et sa graisse (800) ; famille_pour() retrouve
la famille à demander à Qt.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from PySide6.QtGui import QFontDatabase

from ..chemins import dossier_donnees
from ..ui.polices import declarer_police

journal = logging.getLogger(__name__)

POLICES_FOURNIES = ("Montserrat", "Poppins", "Anton", "Bebas Neue", "Inter")
POLICE_DE_SECOURS = "Inter"  # remplace une police introuvable (autre ordinateur, police désinstallée)
EXTENSIONS = (".ttf", ".otf")
NOMS_GRAISSES = {
    100: "Fine",
    200: "Très légère",
    300: "Légère",
    400: "Normale",
    500: "Moyenne",
    600: "Demi-grasse",
    700: "Grasse",
    800: "Extra-grasse",
    900: "Noire",
}


class ErreurPolice(Exception):
    """Police impossible à importer, avec un message clair."""


def dossier_polices_importees() -> Path:
    return dossier_donnees() / "polices"


def _ajouter(fichier: Path) -> list[str]:
    return declarer_police(fichier)  # une seule fois par lancement (voir ui/polices.py)


def charger_polices_importees() -> list[str]:
    """Charge les polices importées (au démarrage). Renvoie leurs familles."""
    dossier = dossier_polices_importees()
    familles: list[str] = []
    for fichier in sorted(dossier.glob("*")) if dossier.is_dir() else []:
        if fichier.suffix.lower() in EXTENSIONS:
            for famille in _ajouter(fichier):
                if famille not in familles:
                    familles.append(famille)
    if familles:
        journal.info("Polices importées chargées : %s", ", ".join(familles))
    return familles


def importer_police(source: Path) -> str:
    """Copie la police dans le dossier de l'app et la charge. Renvoie sa famille."""
    if source.suffix.lower() not in EXTENSIONS:
        raise ErreurPolice("Choisis un fichier de police .ttf ou .otf.")
    dossier = dossier_polices_importees()
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        copie = dossier / source.name
        numero = 2
        while copie.exists() and copie.read_bytes() != source.read_bytes():
            copie = dossier / f"{source.stem} ({numero}){source.suffix}"
            numero += 1
        if not copie.exists():
            shutil.copyfile(source, copie)
    except OSError as erreur:
        raise ErreurPolice(f"Police non copiée dans le dossier de l'app : {erreur}") from erreur
    familles = _ajouter(copie)
    if not familles:
        copie.unlink(missing_ok=True)
        raise ErreurPolice("Ce fichier n'est pas une police lisible.")
    journal.info("Police importée : %s (%s)", familles[0], copie.name)
    return familles[0]


def _visible(famille: str) -> bool:
    return bool(famille) and not famille.startswith("@") and not QFontDatabase.isPrivateFamily(famille)


def existe(famille: str) -> bool:
    return famille in QFontDatabase.families()


def familles() -> list[str]:
    """Familles proposées : les fournies d'abord, puis toutes les autres (importées et de Windows),
    sans les familles « à part » d'une graisse quand la famille de base existe."""
    toutes = [f for f in QFontDatabase.families() if _visible(f)]
    presentes = set(toutes)
    autres = sorted(
        (f for f in toutes if f not in POLICES_FOURNIES and not _famille_d_une_graisse(f, presentes)),
        key=str.casefold,
    )
    return [f for f in POLICES_FOURNIES if f in presentes] + autres


def _famille_d_une_graisse(famille: str, presentes: set[str]) -> bool:
    """« Montserrat ExtraBold » quand « Montserrat » existe aussi (voir en haut du fichier)."""
    base, _espace, suffixe = famille.rpartition(" ")
    return bool(base) and base in presentes and suffixe.replace("-", "").lower() in {
        "thin", "extralight", "ultralight", "light", "regular", "medium", "semibold", "demibold", "bold",
        "extrabold", "ultrabold", "black", "heavy",
    }


def _graisses_de(famille: str) -> set[int]:
    return {
        _arrondie(QFontDatabase.weight(famille, style))
        for style in QFontDatabase.styles(famille)
        if not QFontDatabase.italic(famille, style)
    }


def _arrondie(graisse: int) -> int:
    return int(min(max(round(graisse / 100) * 100, 100), 900))


def graisses(famille: str) -> list[int]:
    """Graisses de la police (familles « à part » comprises), de la plus fine à la plus grasse."""
    trouvees = _graisses_de(famille)
    for autre in QFontDatabase.families():
        if autre.startswith(famille + " ") and _famille_d_une_graisse(autre, {famille}):
            trouvees |= _graisses_de(autre)
    return sorted(trouvees) or [400]


def famille_pour(famille: str, graisse: int) -> str | None:
    """Famille à demander à Qt pour cette police à cette graisse (None : police introuvable)."""
    if not existe(famille):
        return None
    if _arrondie(graisse) in _graisses_de(famille):
        return famille
    for autre in QFontDatabase.families():
        if autre.startswith(famille + " ") and _famille_d_une_graisse(autre, {famille}) and _arrondie(graisse) in _graisses_de(autre):
            return autre
    return famille  # Qt prendra la graisse la plus proche


def graisse_proche(famille: str, graisse: int) -> int:
    """La graisse disponible la plus proche (ex. Anton n'existe qu'en 400)."""
    disponibles = graisses(famille)
    return min(disponibles, key=lambda g: (abs(g - graisse), g))


def police_remplacee(style) -> bool:
    """La police du style est-elle introuvable sur cet ordinateur (elle sera remplacée par Inter) ?"""
    return style.police != POLICE_DE_SECOURS and not existe(style.police)
