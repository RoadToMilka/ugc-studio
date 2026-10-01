"""Police Inter (§9.5), embarquée dans l'app : rien à installer sur l'ordinateur.

Particularité de Windows : selon la façon dont il lit les fichiers de police, les graisses
intermédiaires d'Inter (Medium, SemiBold) sont rangées soit dans la famille « Inter »,
soit dans des familles séparées « Inter Medium » et « Inter SemiBold ». Dans le second cas,
demander « Inter en SemiBold » afficherait du gras (Bold) à la place. On détecte donc le cas au
démarrage, et on indique à chaque texte la bonne famille (voir `famille_pour_graisse`).
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QFont, QFontDatabase

from ..chemins import dossier_ressources
from .theme import Typo

journal = logging.getLogger(__name__)

_POIDS_QT = {
    Typo.GRAISSE_NORMALE: QFont.Weight.Normal,
    Typo.GRAISSE_MOYENNE: QFont.Weight.Medium,
    Typo.GRAISSE_FORTE: QFont.Weight.DemiBold,
}
# Graisse → nom du style dans les fichiers Inter.
_STYLES = {Typo.GRAISSE_MOYENNE: "Medium", Typo.GRAISSE_FORTE: "SemiBold"}

_familles_par_graisse: dict[int, str] = {}


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
    _reperer_familles(familles)
    journal.info("Polices chargées : %s — graisses : %s", ", ".join(familles) or "aucune", _familles_par_graisse)
    return familles


def _reperer_familles(familles_chargees: list[str]) -> None:
    styles_inter = {s.replace(" ", "").lower() for s in QFontDatabase.styles(Typo.FAMILLE)}
    _familles_par_graisse.clear()
    for graisse, style in _STYLES.items():
        famille_separee = f"{Typo.FAMILLE} {style}"
        if style.lower() not in styles_inter and famille_separee in familles_chargees:
            _familles_par_graisse[graisse] = famille_separee
        else:
            _familles_par_graisse[graisse] = Typo.FAMILLE


def famille_pour_graisse(graisse: int) -> str:
    """Nom de famille à utiliser pour afficher Inter à cette graisse (voir en haut du fichier)."""
    return _familles_par_graisse.get(graisse, Typo.FAMILLE)


def familles_par_graisse() -> dict[int, str]:
    return {graisse: famille_pour_graisse(graisse) for graisse in _POIDS_QT}


def poids_qt(graisse: int) -> QFont.Weight:
    """Graisse (100 à 900) → graisse de Qt (arrondie à la centaine)."""
    if graisse in _POIDS_QT:
        return _POIDS_QT[graisse]
    return QFont.Weight(int(min(max(round(graisse / 100) * 100, 100), 900)))


def police(taille: int = Typo.COURANT, graisse: int = Typo.GRAISSE_NORMALE) -> QFont:
    """Police Inter à la taille (en pixels) et à la graisse demandées."""
    resultat = QFont(famille_pour_graisse(graisse))
    resultat.setPixelSize(taille)
    resultat.setWeight(poids_qt(graisse))
    return resultat
