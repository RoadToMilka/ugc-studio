"""Zone qui défile (pages, onglets, fenêtres) : la même partout dans l'app."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ..theme import Dimensions, Espacements


class ZoneDefilante(QScrollArea):
    """Zone qui défile, dont la hauteur « souhaitée » reste modeste.

    Sans cela, Qt prend la hauteur du contenu (jusqu'à 24 lignes de texte) comme hauteur
    souhaitée. Dans une fenêtre à onglets contenant des textes sur plusieurs lignes, Qt en déduit
    même une hauteur *minimale* de fenêtre, qui peut dépasser l'écran d'un ordinateur portable
    (les boutons du bas deviennent inaccessibles). Le contenu, lui, défile comme avant."""

    def sizeHint(self) -> QSize:  # noqa: N802 — nom imposé par Qt
        taille = super().sizeHint()
        return QSize(taille.width(), min(taille.height(), Dimensions.ZONE_DEFILANTE_HAUTEUR_SOUHAITEE))


def zone_defilante(
    largeur_max: int | None = None,
    marges: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> tuple[QScrollArea, QVBoxLayout]:
    """Zone qui défile verticalement quand son contenu est trop haut.

    Renvoie la zone et la disposition verticale où ajouter le contenu. La colonne de contenu
    occupe toute la largeur disponible (en plein écran, les blocs s'étirent jusqu'au bord droit),
    sauf si `largeur_max` la limite ; elle reste alors calée à gauche.
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
    disposition.addLayout(ligne)
    disposition.addStretch(1)
    return zone, contenu
