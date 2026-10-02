"""Disposition « en flux » : les éléments se placent côte à côte et passent à la ligne quand
la largeur manque (comme des mots dans un paragraphe). Utilisée pour la palette de balises, les
onglets et les boutons qui passent à la ligne, et les réglages du studio des sous-titres (V3.1 : des
champs sous leur nom, côte à côte).

Adaptation en Python de l'exemple officiel « Flow Layout » de Qt, avec trois ajouts :
- un espace entre les rangées qui peut différer de l'espace entre deux éléments d'une rangée ;
- des éléments « sur toute la largeur » (ex. une glissière, une case à cocher qui ouvre un groupe de
  réglages) : ils prennent une rangée à eux seuls ;
- un élément caché ne prend ni place ni espace.
"""

from __future__ import annotations

from PySide6.QtCore import QMargins, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QWidget

from ..theme import Espacements


class DispositionFlux(QLayout):
    def __init__(self, parent=None, espacement: int = Espacements.S, espacement_vertical: int | None = None):
        super().__init__(parent)
        self._elements: list[QLayoutItem] = []
        self._espacement = espacement
        self._espacement_vertical = espacement if espacement_vertical is None else espacement_vertical
        self._larges: list[QWidget] = []  # éléments qui prennent toute la largeur
        self.setContentsMargins(QMargins(0, 0, 0, 0))

    def addItem(self, element: QLayoutItem) -> None:
        self._elements.append(element)

    def ajouter_sur_toute_la_largeur(self, element: QWidget) -> None:
        """Ajoute un élément qui prend une rangée à lui seul, sur toute la largeur."""
        self.addWidget(element)
        self._larges.append(element)

    def count(self) -> int:
        return len(self._elements)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._elements[index] if 0 <= index < len(self._elements) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        if not 0 <= index < len(self._elements):
            return None
        element = self._elements.pop(index)
        if element.widget() in self._larges:
            self._larges.remove(element.widget())
        return element

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
            if not element.isEmpty():
                taille = taille.expandedTo(element.minimumSize())
        marges = self.contentsMargins()
        return taille + QSize(marges.left() + marges.right(), marges.top() + marges.bottom())

    def _est_large(self, element: QLayoutItem) -> bool:
        return element.widget() is not None and element.widget() in self._larges

    def _placer(self, zone: QRect, simulation: bool) -> int:
        marges = self.contentsMargins()
        utile = zone.adjusted(marges.left(), marges.top(), -marges.right(), -marges.bottom())
        x, y = utile.x(), utile.y()
        hauteur_ligne = 0  # hauteur de la rangée en cours (0 : rien n'y est encore placé)
        bas = utile.y()  # bas de ce qui est déjà placé
        for element in self._elements:
            if element.isEmpty():  # élément caché : ni place, ni espace
                continue
            if self._est_large(element):
                if hauteur_ligne > 0:
                    y += hauteur_ligne + self._espacement_vertical
                    hauteur_ligne = 0
                largeur = max(utile.width(), element.minimumSize().width())
                if element.hasHeightForWidth():
                    hauteur = element.heightForWidth(largeur)
                else:
                    hauteur = element.sizeHint().height()
                if not simulation:
                    element.setGeometry(QRect(utile.x(), y, largeur, hauteur))
                bas = y + hauteur
                y = bas + self._espacement_vertical
                x = utile.x()
                continue
            taille = element.sizeHint()
            # Jamais plus large que la place (un champ peut se resserrer jusqu'à sa largeur minimale).
            largeur = min(taille.width(), max(utile.width(), element.minimumSize().width()))
            if hauteur_ligne > 0 and x + largeur > utile.right() + 1:
                x = utile.x()
                y += hauteur_ligne + self._espacement_vertical
                hauteur_ligne = 0
            if not simulation:
                element.setGeometry(QRect(x, y, largeur, taille.height()))
            x += largeur + self._espacement
            hauteur_ligne = max(hauteur_ligne, taille.height())
            bas = max(bas, y + hauteur_ligne)
        return bas - zone.y() + marges.bottom()
