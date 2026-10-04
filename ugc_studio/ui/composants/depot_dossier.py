"""Zone où déposer un dossier (V4 : modules Images et Renommer) : un cadre en pointillés, « Glisse un
dossier d'images ici », et « Choisir un dossier… ». Le dépôt marche sur toute la page (voir
dossier_depose et les pages qui l'utilisent) : le cadre s'éclaire quand un dossier passe au-dessus."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout

from ..theme import Espacements
from .elements import bouton, libelle


class ZoneDepotDossier(QFrame):
    """Cadre en pointillés (rôle « depot ») : `texte` (« Glisse un dossier d'images ici »), `legende`
    (les formats acceptés) et le bouton « Choisir un dossier… »."""

    def __init__(self, texte: str, legende: str, choisir_dossier: Callable[[], None], parent=None):
        super().__init__(parent)
        self.setProperty("role", "depot")
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.S)
        disposition.addWidget(libelle(texte, "intitule"), 0, Qt.AlignmentFlag.AlignHCenter)
        disposition.addWidget(libelle(legende, "legende"), 0, Qt.AlignmentFlag.AlignHCenter)
        ligne = QHBoxLayout()
        ligne.addStretch(1)
        self.bouton_choisir = bouton("Choisir un dossier…", nom_icone="folder-open", action=choisir_dossier)
        ligne.addWidget(self.bouton_choisir)
        ligne.addStretch(1)
        disposition.addLayout(ligne)

    def survol(self, actif: bool) -> None:
        self.setProperty("survol", actif)
        self.style().unpolish(self)
        self.style().polish(self)


def dossier_depose(donnees, extensions: Iterable[str]) -> Path | None:
    """Le dossier glissé sur une page (ou celui d'un fichier glissé, s'il a l'une de ces extensions)."""
    acceptees = {extension.lower() for extension in extensions}
    for url in donnees.urls():
        if not url.isLocalFile():
            continue
        chemin = Path(url.toLocalFile())
        if chemin.is_dir():
            return chemin
        if chemin.suffix.lower() in acceptees:
            return chemin.parent
    return None
