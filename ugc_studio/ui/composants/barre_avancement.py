"""Barre d'avancement (V3) : où en est un export (dessin des sous-titres, encodage).

Un rail arrondi, de la couleur des bordures, rempli de mauve (l'accent de l'app) selon l'avancée.
Pourquoi pas la barre standard de Qt ? Son allure change d'un style à l'autre (dégradés, texte
« 42 % » collé dessus) ; celle-ci reprend les arrondis et les couleurs du thème, comme la barre de
lecture des prises. L'avancée en chiffres s'écrit à côté, en français (« 412 images sur 930 »).
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..theme import Couleurs, Dimensions, qcolor


class BarreAvancement(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._avancee = 0.0
        self.setFixedHeight(Dimensions.BARRE_AVANCEMENT_HAUTEUR)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def avancee(self) -> float:
        return self._avancee

    def definir(self, avancee: float) -> None:
        """Avancée de 0 (rien de fait) à 1 (fini)."""
        avancee = min(max(float(avancee), 0.0), 1.0)
        if avancee != self._avancee:
            self._avancee = avancee
            self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 (nom imposé par Qt)
        return QSize(Dimensions.CHAMP_STYLE_LARGEUR_MIN, Dimensions.BARRE_AVANCEMENT_HAUTEUR)

    def paintEvent(self, _evenement) -> None:  # noqa: N802 (nom imposé par Qt)
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        peintre.setPen(Qt.PenStyle.NoPen)
        rail = QRectF(self.rect())
        rayon = rail.height() / 2
        peintre.setBrush(qcolor(Couleurs.BORDURE))
        peintre.drawRoundedRect(rail, rayon, rayon)
        if self._avancee > 0:
            # Jamais plus court qu'un rond : le début de l'avancée se voit tout de suite.
            rempli = QRectF(rail.left(), rail.top(), max(rail.height(), rail.width() * self._avancee), rail.height())
            peintre.setBrush(qcolor(Couleurs.ACCENT))
            peintre.drawRoundedRect(rempli, rayon, rayon)
        peintre.end()
