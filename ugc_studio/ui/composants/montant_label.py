"""MontantLabel : affichage d'un montant en euros au format du cahier des charges (§4.4).

Exemple : 0.007 € s'affiche « 0.0 » en taille normale, puis « 07 » plus petit (~70 %), puis « € ».
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from ...montants import Montant, decouper_montant, en_decimal, formater_montant
from ..theme import RATIO_PETITES_DECIMALES, Typo


class MontantLabel(QLabel):
    def __init__(self, montant: Montant = 0, taille: int = Typo.COURANT, parent=None):
        super().__init__(parent)
        self._taille = taille
        self._montant = en_decimal(montant)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setProperty("role", "montant")
        self.definir_montant(montant)

    @property
    def montant(self):
        return self._montant

    def definir_montant(self, montant: Montant) -> None:
        self._montant = en_decimal(montant)
        principal, petites = decouper_montant(self._montant)
        petite_taille = round(self._taille * RATIO_PETITES_DECIMALES)
        # Texte « riche » (mini-HTML) : chaque morceau a sa propre taille de police.
        self.setText(
            f'<span style="font-size:{self._taille}px">{principal}</span>'
            f'<span style="font-size:{petite_taille}px">{petites}</span>'
            f'<span style="font-size:{self._taille}px">&nbsp;€</span>'
        )
        self.setAccessibleName(formater_montant(self._montant))
