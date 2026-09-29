"""Palette de balises (§5.2) : un bouton-pastille par balise, rangés par famille et par couleur.

Un clic insère la balise à l'endroit du curseur dans l'éditeur de script.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QFontMetrics, QPainter, QPen, QTextOption
from PySide6.QtWidgets import QAbstractButton, QGridLayout, QVBoxLayout, QWidget

from ...balises import FAMILLES
from ..polices import police
from ..theme import CouleursBalises, Dimensions, Espacements, Hauteurs, Opacites, Typo, qcolor
from .elements import libelle
from .flux import DispositionFlux


class BoutonBalise(QAbstractButton):
    def __init__(self, nom: str, couleur: str, parent=None):
        super().__init__(parent)
        self.setText(nom)
        self._couleur = couleur
        self._police = police(Typo.LEGENDE, Typo.GRAISSE_MOYENNE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # le focus reste dans l'éditeur de script
        self.setToolTip(f"Insérer <{nom}> à l'endroit du curseur")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def sizeHint(self) -> QSize:
        largeur = QFontMetrics(self._police).horizontalAdvance(self.text())
        return QSize(largeur + 2 * Dimensions.BADGE_MARGE_HORIZONTALE, Hauteurs.PASTILLE)

    def enterEvent(self, evenement) -> None:
        self.update()
        super().enterEvent(evenement)

    def leaveEvent(self, evenement) -> None:
        self.update()
        super().leaveEvent(evenement)

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        demi = Dimensions.BORDURE / 2
        zone = QRectF(self.rect()).adjusted(demi, demi, -demi, -demi)
        opacite = Opacites.FOND_BADGE_SURVOL if self.underMouse() else Opacites.FOND_BADGE
        peintre.setPen(QPen(qcolor(self._couleur, Opacites.CONTOUR_BADGE), Dimensions.BORDURE))
        peintre.setBrush(QBrush(qcolor(self._couleur, opacite)))
        peintre.drawRoundedRect(zone, zone.height() / 2, zone.height() / 2)
        peintre.setFont(self._police)
        peintre.setPen(qcolor(self._couleur))
        peintre.drawText(zone, self.text(), QTextOption(Qt.AlignmentFlag.AlignCenter))
        peintre.end()


class PaletteBalises(QWidget):
    balise_choisie = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        grille = QGridLayout(self)
        grille.setContentsMargins(0, 0, 0, 0)
        grille.setHorizontalSpacing(Espacements.XL)
        grille.setVerticalSpacing(Espacements.M)
        self.boutons: dict[str, BoutonBalise] = {}
        for index, famille in enumerate(FAMILLES):
            case = QVBoxLayout()
            case.setSpacing(Espacements.XS)
            case.addWidget(libelle(famille.nom, "legende", retour_a_la_ligne=False))
            flux = DispositionFlux(espacement=Espacements.XS)
            for balise in famille.balises:
                bouton = BoutonBalise(balise, CouleursBalises.de(famille.identifiant))
                bouton.clicked.connect(lambda _coche=False, nom=balise: self.balise_choisie.emit(nom))
                flux.addWidget(bouton)
                self.boutons[balise] = bouton
            case.addLayout(flux)
            grille.addLayout(case, index // 2, index % 2)
        grille.setColumnStretch(0, 1)
        grille.setColumnStretch(1, 1)
