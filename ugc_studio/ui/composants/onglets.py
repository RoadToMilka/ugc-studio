"""Onglets en boutons (§9.4 bis) : une rangée de boutons au-dessus du contenu.

L'onglet actif a l'allure « sélectionné » des boutons (contour mauve, fond mauve très léger, comme
le module actif de la barre latérale) ; les autres ont le style « contour ». De haut en bas : une
ligne de séparation, un espace, la rangée de boutons, puis le contenu de l'onglet.

Pourquoi pas les onglets standard de Qt (QTabWidget) ? Ils soulignaient l'onglet actif d'un trait
mauve qui effaçait la ligne de séparation au-dessus de lui, et ils se règlent mal dans la feuille
de style. Ce composant garde les fonctions de QTabWidget dont l'app se sert : addTab,
setCurrentIndex, currentIndex, currentChanged, count, widget, tabText, setTabEnabled.

Hauteur : comme chez Qt, le contenu prend la hauteur de l'onglet le plus haut (les boutons ne
bougent pas d'un onglet à l'autre). Avec hauteur_selon_l_onglet, il prend celle de l'onglet affiché :
pas de grand vide sous un onglet court quand un autre est très long (studio des sous-titres).
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from ..theme import Espacements
from .bouton import Bouton
from .elements import separateur


class PileAjustee(QStackedWidget):
    """Pile de pages dont la taille demandée est celle de la page affichée (QStackedWidget prend celle
    de la plus grande)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.currentChanged.connect(lambda _index: self.updateGeometry())  # nouvelle hauteur à placer

    def sizeHint(self) -> QSize:  # noqa: N802 — nom imposé par Qt
        page = self.currentWidget()
        return page.sizeHint() if page is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        page = self.currentWidget()
        return page.minimumSizeHint() if page is not None else super().minimumSizeHint()

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        page = self.currentWidget()
        return page.hasHeightForWidth() if page is not None else False

    def heightForWidth(self, largeur: int) -> int:  # noqa: N802
        page = self.currentWidget()
        return page.heightForWidth(largeur) if page is not None else -1


class Onglets(QWidget):
    currentChanged = Signal(int)  # même nom que chez QTabWidget

    def __init__(self, parent: QWidget | None = None, hauteur_selon_l_onglet: bool = False):
        super().__init__(parent)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)
        disposition.addWidget(separateur())
        disposition.addSpacing(Espacements.L)  # de l'air entre la ligne et les boutons
        self._rangee = QHBoxLayout()
        self._rangee.setContentsMargins(0, 0, 0, 0)
        self._rangee.setSpacing(Espacements.S)
        self._rangee.addStretch(1)
        disposition.addLayout(self._rangee)
        self._pile = PileAjustee() if hauteur_selon_l_onglet else QStackedWidget()
        disposition.addWidget(self._pile, 1)
        self._boutons: list[Bouton] = []
        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)  # un seul onglet actif à la fois
        self._groupe.idClicked.connect(self.setCurrentIndex)
        self._pile.currentChanged.connect(self.currentChanged.emit)

    # --- Fonctions de QTabWidget utilisées par l'app -------------------------------------------

    def addTab(self, page: QWidget, titre: str) -> int:  # noqa: N802 — même nom que chez Qt
        index = len(self._boutons)
        bouton = Bouton(titre, "contour")
        bouton.setCheckable(True)
        self._groupe.addButton(bouton, index)
        self._rangee.insertWidget(index, bouton)
        self._boutons.append(bouton)
        self._pile.addWidget(page)
        if index == 0:
            bouton.setChecked(True)
        return index

    def count(self) -> int:
        return len(self._boutons)

    def currentIndex(self) -> int:  # noqa: N802
        return self._pile.currentIndex()

    def currentWidget(self) -> QWidget | None:  # noqa: N802
        return self._pile.currentWidget()

    def widget(self, index: int) -> QWidget | None:
        return self._pile.widget(index)

    def tabText(self, index: int) -> str:  # noqa: N802
        return self._boutons[index].text()

    def setTabEnabled(self, index: int, actif: bool) -> None:  # noqa: N802
        self._boutons[index].setEnabled(actif)

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if not 0 <= index < len(self._boutons):
            return
        self._boutons[index].setChecked(True)
        self._pile.setCurrentIndex(index)

    # --- Pour les tests et l'autotest -----------------------------------------------------------

    def bouton(self, index: int) -> Bouton:
        """Le bouton de l'onglet `index` (ex. pour cliquer dessus dans un test)."""
        return self._boutons[index]
