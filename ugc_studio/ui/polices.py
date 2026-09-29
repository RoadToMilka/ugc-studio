"""Police Inter (§9.5), embarquée dans l'app : rien à installer sur l'ordinateur."""

from __future__ import annotations

import logging

from PySide6.QtGui import QFont, QFontDatabase

from ..chemins import dossier_ressources
from .theme import Typo

journal = logging.getLogger(__name__)

_GRAISSES = {
    Typo.GRAISSE_NORMALE: QFont.Weight.Normal,
    Typo.GRAISSE_MOYENNE: QFont.Weight.Medium,
    Typo.GRAISSE_FORTE: QFont.Weight.DemiBold,
}


def charger_polices() -> list[str]:
    """Déclare à Qt les fichiers de police embarqués. Renvoie les familles chargées."""
    familles: list[str] = []
    for fichier in sorted((dossier_ressources() / "polices").glob("*.ttf")):
        identifiant = QFontDatabase.addApplicationFont(str(fichier))
        if identifiant < 0:
            journal.warning("Police non chargée : %s", fichier.name)
            continue
        for famille in QFontDatabase.applicationFontFamilies(identifiant):
            if famille not in familles:
                familles.append(famille)
    journal.info("Polices chargées : %s", ", ".join(familles) or "aucune")
    return familles


def police(taille: int = Typo.COURANT, graisse: int = Typo.GRAISSE_NORMALE) -> QFont:
    """Police Inter à la taille (en pixels) et à la graisse demandées."""
    resultat = QFont(Typo.FAMILLE)
    resultat.setPixelSize(taille)
    resultat.setWeight(_GRAISSES.get(graisse, QFont.Weight.Normal))
    return resultat
