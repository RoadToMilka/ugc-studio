"""Disposition « en flux » : les éléments se placent côte à côte et passent à la ligne quand
la largeur manque (comme des mots dans un paragraphe). Utilisée pour la palette de balises.

Adaptation en Python de l'exemple officiel « Flow Layout » de Qt.
"""

from __future__ import annotations

from PySide6.QtCore import QMargins, QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem

from ..theme import Espacements


class DispositionFlux(QLayout):
    def __init__(self, parent=None, espacement: int = Espacements.S):
        super().__init__(parent)
        self._elements: list[QLayoutItem] = []
        self._espacement = espacement
        self.setContentsMargins(QMargins(0, 0, 0, 0))

    def addItem(self, element: QLayoutItem) -> None:
        self._elements.append(element)

    def count(self) -> int:
        return len(self._elements)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._elements[index] if 0 <= index < len(self._elements) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        return self._elements.pop(index) if 0 <= index < len(self._elements) else None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, largeur: int) -> int:
        return self._placer(QRect(0, 0, largeur, 0), simulation=True)

    def setGeometry(self, zone: QRect) -> None:
        super().setGeometry(zone)
        self._placer(zone, simulation=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        taille = QSize()
        for element in self._elements:
            taille = taille.expandedTo(element.minimumSize())
        marges = self.contentsMargins()
        return taille + QSize(marges.left() + marges.right(), marges.top() + marges.bottom())

    def _placer(self, zone: QRect, simulation: bool) -> int:
        marges = self.contentsMargins()
        utile = zone.adjusted(marges.left(), marges.top(), -marges.right(), -marges.bottom())
        x, y = utile.x(), utile.y()
        hauteur_ligne = 0
        for element in self._elements:
            taille = element.sizeHint()
            prochain_x = x + taille.width() + self._espacement
            if prochain_x - self._espacement > utile.right() + 1 and hauteur_ligne > 0:
                x = utile.x()
                y += hauteur_ligne + self._espacement
                prochain_x = x + taille.width() + self._espacement
                hauteur_ligne = 0
            if not simulation:
                element.setGeometry(QRect(QPoint(x, y), taille))
            x = prochain_x
            hauteur_ligne = max(hauteur_ligne, taille.height())
        return y + hauteur_ligne - zone.y() + marges.bottom()
