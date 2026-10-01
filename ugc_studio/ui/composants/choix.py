"""Choix en boutons (V2, lot 3) : quelques choix exclusifs côte à côte, par exemple « Haut, Centre,
Bas » ou « Ajusté, 100 % ».

Le bouton choisi a l'allure « sélectionné » des boutons (contour mauve, fond mauve très léger),
comme un onglet actif ou le module actif de la barre latérale ; les autres ont le style
« contour ». Pourquoi pas une liste déroulante ? Pour deux ou trois choix, tous restent visibles et
se changent d'un seul clic.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QWidget

from ..theme import Espacements
from .bouton import Bouton


class ChoixEnBoutons(QWidget):
    change = Signal(str)  # la valeur choisie (seulement quand on clique : pas avec definir())

    def __init__(self, choix: dict[str, str], info: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.XS)
        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        self._valeurs = list(choix)
        self._boutons: dict[str, Bouton] = {}
        for rang, (valeur, texte) in enumerate(choix.items()):
            bouton = Bouton(texte, "contour")
            bouton.setCheckable(True)
            self._groupe.addButton(bouton, rang)
            disposition.addWidget(bouton)
            self._boutons[valeur] = bouton
        if self._valeurs:
            self._boutons[self._valeurs[0]].setChecked(True)
        if info:
            self.setToolTip(info)
        self._groupe.idClicked.connect(lambda rang: self.change.emit(self._valeurs[rang]))

    def valeur(self) -> str:
        rang = self._groupe.checkedId()
        return self._valeurs[rang] if 0 <= rang < len(self._valeurs) else ""

    def definir(self, valeur: str) -> None:
        """Coche ce choix sans prévenir (valeur relue dans le projet, par exemple)."""
        if valeur in self._boutons:
            self._boutons[valeur].setChecked(True)

    def bouton(self, valeur: str) -> Bouton:
        """Le bouton d'un choix (pour les tests, ou pour griser un choix impossible)."""
        return self._boutons[valeur]
