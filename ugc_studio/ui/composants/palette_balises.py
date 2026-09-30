"""Palette de balises (§5.2) : un bouton-pastille par balise, rangés par famille et par couleur.

Un clic insère la balise à l'endroit du curseur dans l'éditeur de script. Chaque pastille montre
le nom français de la balise ; son vrai nom, celui envoyé à Google (ex. <laugh>), apparaît au survol.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QGridLayout, QVBoxLayout, QWidget

from ...balises import FAMILLES, info_balise, nom_affiche
from ..polices import police
from ..theme import CouleursBalises, Dimensions, Espacements, Hauteurs, Opacites, Typo, qcolor
from .bouton import dessiner_texte_centre_a_l_oeil
from .elements import libelle
from .flux import DispositionFlux


class BoutonBalise(QAbstractButton):
    """Pastille d'une balise. `balise` : son nom anglais (envoyé à Google) ; le texte affiché est
    son nom français."""

    def __init__(self, balise: str, couleur: str, parent=None):
        super().__init__(parent)
        self.balise = balise
        self.setText(nom_affiche(balise))
        self._couleur = couleur
        self._police = police(Typo.LEGENDE, Typo.GRAISSE_MOYENNE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # le focus reste dans l'éditeur de script
        self.setToolTip(info_balise(balise))
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
        dessiner_texte_centre_a_l_oeil(peintre, QRectF(self.rect()), self.text(), self._police, qcolor(self._couleur))
        peintre.end()


class PaletteBalises(QWidget):
    balise_choisie = Signal(str)  # nom anglais de la balise

    def __init__(self, parent=None):
        super().__init__(parent)
        grille = QGridLayout(self)
        grille.setContentsMargins(0, 0, 0, 0)
        grille.setHorizontalSpacing(Espacements.XL)
        grille.setVerticalSpacing(Espacements.M)
        self.boutons: dict[str, BoutonBalise] = {}  # par nom anglais
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
