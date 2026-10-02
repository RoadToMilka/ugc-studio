"""Zone qui défile (pages, onglets, fenêtres) : la même partout dans l'app, avec un fondu en haut
et en bas (V1.1, §9.4 sexies).

Le fondu : quand du contenu est caché en haut ou en bas, un dégradé de 24 px de la couleur du fond
adoucit ce bord, pour qu'on devine qu'il y a une suite. Il n'apparaît que de ce côté-là (pas de
fondu en haut quand on est tout en haut), et il laisse passer les clics.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRect, QSize, Qt
from PySide6.QtGui import QLinearGradient, QPainter
from PySide6.QtWidgets import QAbstractScrollArea, QDialog, QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ..theme import Couleurs, Dimensions, Espacements, qcolor


def couleur_du_fond(element: QWidget) -> str:
    """Couleur du fond derrière `element` : celle des fenêtres de dialogue, sinon celle de l'app
    (voir QDialog et QMainWindow dans la feuille de style)."""
    parent = element
    while parent is not None:
        if isinstance(parent, QDialog):
            return Couleurs.SURFACE_ELEVEE
        parent = parent.parentWidget()
    return Couleurs.FOND


class _Degrade(QWidget):
    """Le dégradé d'un bord (haut ou bas), posé par-dessus le contenu qui défile."""

    def __init__(self, zone: QAbstractScrollArea, en_haut: bool, fondus: Fondus):
        super().__init__(zone)
        self._en_haut = en_haut
        self._fondus = fondus
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # ne bloque aucun clic
        self.hide()

    def paintEvent(self, _evenement) -> None:  # noqa: N802 — nom imposé par Qt
        couleur = self._fondus.couleur()
        opaque, invisible = qcolor(couleur), qcolor(couleur, 0)
        degrade = QLinearGradient(0, 0, 0, self.height())
        degrade.setColorAt(0, opaque if self._en_haut else invisible)
        degrade.setColorAt(1, invisible if self._en_haut else opaque)
        peintre = QPainter(self)
        peintre.fillRect(self.rect(), degrade)
        peintre.end()


class Fondus(QObject):
    """Fondus en haut et en bas d'une zone qui défile (page, fenêtre, liste déroulante).

    `couleur` : couleur du fond de la zone ; par défaut, celle de la fenêtre qui la contient."""

    def __init__(self, zone: QAbstractScrollArea, couleur: str | None = None):
        super().__init__(zone)
        self._zone = zone
        self._couleur = couleur
        self.haut = _Degrade(zone, True, self)
        self.bas = _Degrade(zone, False, self)
        barre = zone.verticalScrollBar()
        barre.valueChanged.connect(self.placer)
        barre.rangeChanged.connect(self.placer)
        # La partie visible change de taille avec la zone, et quand la barre de défilement apparaît.
        zone.installEventFilter(self)
        zone.viewport().installEventFilter(self)

    def couleur(self) -> str:
        return self._couleur or couleur_du_fond(self._zone)

    def eventFilter(self, _objet, evenement) -> bool:  # noqa: N802 — nom imposé par Qt
        if evenement.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.placer()
        return False

    def placer(self, *_args) -> None:
        visible = self._zone.viewport().geometry()
        hauteur = min(Dimensions.FONDU, visible.height() // 2)
        self.haut.setGeometry(QRect(visible.left(), visible.top(), visible.width(), hauteur))
        self.bas.setGeometry(QRect(visible.left(), visible.bottom() + 1 - hauteur, visible.width(), hauteur))
        barre = self._zone.verticalScrollBar()
        self.haut.setVisible(barre.value() > barre.minimum())  # du contenu est caché au-dessus
        self.bas.setVisible(barre.value() < barre.maximum())  # … ou en dessous
        self.haut.raise_()
        self.bas.raise_()


class ZoneDefilante(QScrollArea):
    """Zone qui défile, avec ses fondus, et dont la hauteur « souhaitée » reste modeste.

    Sans cela, Qt prend la hauteur du contenu (jusqu'à 24 lignes de texte) comme hauteur
    souhaitée. Dans une fenêtre à onglets contenant des textes sur plusieurs lignes, Qt en déduit
    même une hauteur *minimale* de fenêtre, qui peut dépasser l'écran d'un ordinateur portable
    (les boutons du bas deviennent inaccessibles). Le contenu, lui, défile comme avant."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.fondus = Fondus(self)

    def sizeHint(self) -> QSize:  # noqa: N802 — nom imposé par Qt
        taille = super().sizeHint()
        return QSize(taille.width(), min(taille.height(), Dimensions.ZONE_DEFILANTE_HAUTEUR_SOUHAITEE))


def zone_defilante(
    largeur_max: int | None = None,
    marges: tuple[int, int, int, int] = (0, 0, 0, 0),
    remplir_la_hauteur: bool = False,
    barre_dans_la_marge: bool = False,
) -> tuple[QScrollArea, QVBoxLayout]:
    """Zone qui défile verticalement quand son contenu est trop haut.

    Renvoie la zone et la disposition verticale où ajouter le contenu. La colonne de contenu
    occupe toute la largeur disponible (en plein écran, les blocs s'étirent jusqu'au bord droit),
    sauf si `largeur_max` la limite ; elle reste alors calée à gauche.

    `remplir_la_hauteur` : la colonne prend toute la hauteur visible (un élément ajouté avec un
    facteur d'étirement la remplit, ex. le tableau du suivi des coûts) ; sinon, le contenu reste en
    haut et la place en trop est en bas.

    `barre_dans_la_marge` (pages, V3.1) : la barre de défilement prend place dans la marge de droite
    quand elle apparaît. Ainsi, l'espace entre les blocs et le bord de la fenêtre reste le même avec
    ou sans barre, et les blocs ne changent pas de largeur quand elle apparaît.
    """
    zone = ZoneDefilante()
    zone.setWidgetResizable(True)
    zone.setFrameShape(QFrame.Shape.NoFrame)
    zone.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    interieur = QWidget()
    interieur.setObjectName("contenuDefilant")
    zone.setWidget(interieur)
    # setWidget() rend le fond du contenu opaque (couleur « fenêtre » de la palette) :
    # on le remet transparent pour voir le fond de l'app, comme dans le reste de l'interface.
    interieur.setAutoFillBackground(False)
    zone.viewport().setAutoFillBackground(False)

    disposition = QVBoxLayout(interieur)
    disposition.setContentsMargins(*marges)
    disposition.setSpacing(0)
    if barre_dans_la_marge:
        gauche, haut, droite, bas = marges
        barre = zone.verticalScrollBar()

        def placer_la_barre(*_bornes) -> None:
            # La barre est visible dès qu'il y a quelque chose à faire défiler (« si besoin »).
            visible = barre.maximum() > barre.minimum()
            reste = max(0, droite - Dimensions.BARRE_DEFILEMENT) if visible else droite
            disposition.setContentsMargins(gauche, haut, reste, bas)

        barre.rangeChanged.connect(placer_la_barre)

    colonne = QWidget()
    if largeur_max is not None:
        colonne.setMaximumWidth(largeur_max)
    contenu = QVBoxLayout(colonne)
    contenu.setContentsMargins(0, 0, 0, 0)
    contenu.setSpacing(Espacements.L)
    ligne = QHBoxLayout()
    ligne.setContentsMargins(0, 0, 0, 0)
    ligne.addWidget(colonne, 1)
    ligne.addStretch(0)
    if remplir_la_hauteur:
        disposition.addLayout(ligne, 1)
    else:
        disposition.addLayout(ligne)
        disposition.addStretch(1)
    return zone, contenu
