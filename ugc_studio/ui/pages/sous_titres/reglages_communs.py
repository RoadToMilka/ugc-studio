"""Petits outils communs aux onglets du studio des sous-titres (V2) : grille « libellé : champ » et
nombres écrits à la française."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QWidget

from ...composants.elements import libelle
from ...theme import Espacements


def nombre_lisible(valeur: float, decimales: int = 1) -> str:
    """2.5 → « 2,5 » ; 3.0 → « 3 »."""
    texte = f"{valeur:.{decimales}f}".rstrip("0").rstrip(".")
    return texte.replace(".", ",").replace("-", "−") or "0"


def grille(lignes, etirees: tuple[int, ...] = ()) -> QGridLayout:
    """Libellés à gauche, champs à droite, à leur largeur naturelle (sauf les lignes `etirees`, qui
    prennent toute la largeur de la colonne : une glissière, par exemple)."""
    disposition = QGridLayout()
    disposition.setHorizontalSpacing(Espacements.M)
    disposition.setVerticalSpacing(Espacements.S)
    for rang, (texte, element) in enumerate(lignes):
        disposition.addWidget(libelle(texte, "legende", retour_a_la_ligne=False), rang, 0)
        alignement = Qt.AlignmentFlag(0) if rang in etirees else Qt.AlignmentFlag.AlignLeft
        if isinstance(element, QWidget):
            disposition.addWidget(element, rang, 1, alignement)
        else:
            disposition.addLayout(element, rang, 1, alignement)
    disposition.setColumnStretch(1, 1)
    return disposition
