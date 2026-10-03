"""Zone qui défile (pages, onglets, fenêtres) : la même partout dans l'app, avec un fondu en haut
et en bas (V1.1, §9.4 sexies).

Le fondu : quand du contenu est caché en haut ou en bas, un dégradé de 24 px de la couleur du fond
adoucit ce bord, pour qu'on devine qu'il y a une suite. Il n'apparaît que de ce côté-là (pas de
fondu en haut quand on est tout en haut), et il laisse passer les clics. Sa couleur est celle du
fond derrière la zone (couleur_du_fond) : le contenu se fond dans le bloc ou dans le fond de l'app.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRect, QSize, Qt
from PySide6.QtGui import QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..theme import Couleurs, Dimensions, Espacements, qcolor


def couleur_du_fond(element: QWidget) -> str:
    """Couleur du fond derrière `element` (la couleur de ses fondus) : celle des blocs quand il est
    dans un bloc (une liste dans le bloc d'une fenêtre ou d'une page), sinon celle de l'app, fenêtres
    comprises (voir QFrame[role="bloc"], QDialog et QMainWindow dans la feuille de style).

    V3.2 (3.2.1) : les fenêtres ont le fond de l'app, et leur contenu est dans un bloc. Jusqu'à la
    3.2.0, toute zone d'une fenêtre prenait le gris des menus (le fond des fenêtres jusqu'à la 3.1.2) :
    ses fondus ne se fondaient plus dans rien."""
    parent = element
    while parent is not None:
        if parent.property("role") == "bloc":
            return Couleurs.SURFACE
        if parent.isWindow():
            break
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


class ColonneDefilante(QScrollArea):
    """Contenu d'un bloc qui défile seul, ou pas (V3.1, lot 5 : colonnes Apparence et Sous-titres du
    studio des sous-titres).

    - Avec `definir_defilement(True)` (grande fenêtre), la zone prend la hauteur que le bloc lui
      laisse et son contenu défile dedans, avec une barre fine et les fondus. Quand il reste de la
      place, le contenu s'étire : un élément ajouté avec un facteur d'étirement la prend (ex. la liste
      des sous-titres).
    - Avec `definir_defilement(False)`, la zone prend toute la hauteur de son contenu, comme si elle
      n'était pas là : c'est la page qui défile.

    La barre prend place dans la marge de droite du bloc, comme celle des pages (lot 1) : le bloc ne
    garde que `Espacements.S` de marge à droite, et le contenu `marge_droite` de plus quand la barre
    est cachée, `marge_droite` moins la barre quand elle est visible. Le contenu garde donc la même
    largeur : rien ne passe à la ligne quand la barre apparaît."""

    def __init__(self, contenu: QWidget, marge_droite: int = 0, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("colonneDefilante")  # barre fine : voir la feuille de style
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        interieur = QWidget()
        self._disposition = QVBoxLayout(interieur)
        self._disposition.setContentsMargins(0, 0, marge_droite, 0)
        self._disposition.setSpacing(0)
        self._disposition.addWidget(contenu)
        self.setWidget(interieur)
        # Comme zone_defilante : le fond reste celui du bloc.
        interieur.setAutoFillBackground(False)
        self.viewport().setAutoFillBackground(False)
        self.contenu = contenu
        self._marge_droite = marge_droite
        self.fondus = Fondus(self, Couleurs.SURFACE)  # le fond d'un bloc
        self._defile = True
        self.verticalScrollBar().rangeChanged.connect(self._placer_la_barre)
        self.definir_defilement(False)

    @property
    def defile(self) -> bool:
        return self._defile

    def definir_defilement(self, defile: bool) -> None:
        if defile == self._defile:
            return
        self._defile = defile
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded if defile else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        politique = QSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding if defile else QSizePolicy.Policy.Preferred
        )
        politique.setHeightForWidth(not defile)
        self.setSizePolicy(politique)
        if not defile:
            self.verticalScrollBar().setValue(0)
        self._placer_la_barre()
        self.updateGeometry()

    def _placer_la_barre(self, *_bornes) -> None:
        barre = self.verticalScrollBar()
        visible = self._defile and barre.maximum() > barre.minimum()
        reste = max(0, self._marge_droite - Dimensions.BARRE_DEFILEMENT_FINE) if visible else self._marge_droite
        if self._disposition.contentsMargins().right() != reste:
            self._disposition.setContentsMargins(0, 0, reste, 0)

    # --- Taille : toute la hauteur du contenu quand la zone ne défile pas ------------------------

    def eventFilter(self, objet, evenement) -> bool:  # noqa: N802 — nom imposé par Qt
        # QScrollArea surveille déjà son contenu (setWidget) : quand la disposition du contenu change
        # (groupe ouvert, onglet, texte plus long…), la zone qui ne défile pas change de hauteur avec
        # lui. Sans cela, le bloc qui la contient garderait l'ancienne hauteur (contenu coupé).
        if objet is self.widget() and evenement.type() == QEvent.Type.LayoutRequest and not self._defile:
            self.updateGeometry()
        return super().eventFilter(objet, evenement)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 — nom imposé par Qt
        return not self._defile

    def heightForWidth(self, largeur: int) -> int:  # noqa: N802
        interieur = self.widget()
        if interieur.hasHeightForWidth():
            return interieur.heightForWidth(largeur)
        return interieur.sizeHint().height()

    def sizeHint(self) -> QSize:  # noqa: N802
        taille = self.widget().sizeHint()
        if self._defile:
            return QSize(taille.width(), min(taille.height(), Dimensions.ZONE_DEFILANTE_HAUTEUR_SOUHAITEE))
        return taille

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        minimum = self.widget().minimumSizeHint()
        # Qui défile : sa hauteur est celle que le bloc lui laisse ; sinon, toute celle du contenu
        # (donnée par heightForWidth à la disposition qui la contient).
        return QSize(minimum.width(), 0 if self._defile else minimum.height())
