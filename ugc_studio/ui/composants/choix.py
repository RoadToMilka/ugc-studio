"""Choix en boutons (V2, lot 3) : quelques choix exclusifs côte à côte, par exemple « Haut, Centre,
Bas ».

Le bouton choisi a l'allure « sélectionné » des boutons (contour mauve, fond mauve très léger),
comme un onglet actif ou le module actif de la barre latérale ; les autres ont le style
« contour ». Pourquoi pas une liste déroulante ? Pour deux ou trois choix, tous restent visibles et
se changent d'un seul clic.

Choix en liste (V3.2, 3.2.2) : les mêmes choix exclusifs dans une liste déroulante, quand la place
manque pour les boutons (« Fond » et « Zoom » sous l'aperçu des sous-titres : en boutons, ils
élargissaient la colonne de l'aperçu, et la vidéo y flottait avec trop d'espace sur les côtés).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QWidget

from ..theme import Espacements
from .bouton import Bouton
from .elements import ListeDeroulante


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


class ChoixEnListe(ListeDeroulante):
    """Choix exclusifs dans une liste déroulante de l'app (voir en haut du fichier), qui se règle comme
    ChoixEnBoutons : valeur(), definir(), et le signal `change` quand on choisit dans la liste."""

    change = Signal(str)  # la valeur choisie (seulement quand on choisit : pas avec definir())

    def __init__(self, choix: dict[str, str], info: str | None = None):
        super().__init__()
        # Ses choix sont courts et connus d'avance : la liste a la largeur du plus long, sans le
        # minimum de 10 caractères des autres listes (prévu pour des choix qui peuvent être longs,
        # comme le nom d'une voix). Avec lui, « Fond » et « Zoom » ne tenaient pas côte à côte sous
        # une vidéo de 304 px. La molette ne change le choix qu'après un clic, comme liste_deroulante().
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if info:
            self.setToolTip(info)
        for valeur, texte in choix.items():
            self.addItem(texte, valeur)
        self.activated.connect(lambda rang: self.change.emit(self.itemData(rang)))

    def valeur(self) -> str:
        return self.currentData() or ""

    def definir(self, valeur: str) -> None:
        """Choisit cette valeur sans prévenir (valeur relue dans les préférences, par exemple)."""
        rang = self.findData(valeur)
        if rang >= 0:
            self.setCurrentIndex(rang)

    def choisir(self, valeur: str) -> None:
        """Comme un choix fait dans la liste : la valeur change, et `change` prévient (autotest, tests)."""
        rang = self.findData(valeur)
        if rang >= 0 and self.est_actif(valeur):
            self.setCurrentIndex(rang)
            self.change.emit(valeur)

    def activer(self, valeur: str, actif: bool) -> None:
        """Grise un choix impossible (ex. « Vidéo » sans vidéo), ou le rend à nouveau possible."""
        modele, rang = self.model(), self.findData(valeur)
        if isinstance(modele, QStandardItemModel) and rang >= 0:
            modele.item(rang).setEnabled(actif)

    def est_actif(self, valeur: str) -> bool:
        modele, rang = self.model(), self.findData(valeur)
        if isinstance(modele, QStandardItemModel) and rang >= 0:
            return modele.item(rang).isEnabled()
        return rang >= 0
