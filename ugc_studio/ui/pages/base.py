"""Structure commune des pages : titre, sous-titre, puis le contenu (qui défile si besoin)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ..composants.elements import libelle
from ..theme import Dimensions, Espacements


def zone_defilante(
    largeur_max: int | None = Dimensions.CONTENU_LARGEUR_MAX,
    marges: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> tuple[QScrollArea, QVBoxLayout]:
    """Zone qui défile verticalement quand son contenu est trop haut.

    Renvoie la zone et la disposition verticale où ajouter le contenu. La colonne de contenu
    occupe toute la largeur disponible sans dépasser `largeur_max` (au-delà, les lignes de
    texte deviennent trop longues à lire), et reste calée à gauche.
    """
    zone = QScrollArea()
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


def entete_de_page(titre: str, sous_titre: str) -> QVBoxLayout:
    """Titre + sous-titre d'une page. Les deux textes restent accessibles : `entete.titre`, `entete.sous_titre`."""
    entete = QVBoxLayout()
    entete.setContentsMargins(0, 0, 0, 0)
    entete.setSpacing(Espacements.XS)
    entete.titre = libelle(titre, "titre-page")
    entete.sous_titre = libelle(sous_titre, "secondaire")
    entete.addWidget(entete.titre)
    entete.addWidget(entete.sous_titre)
    return entete


class Page(QWidget):
    """Page avec un en-tête (titre + sous-titre) et une zone de contenu défilante.

    Les pages ajoutent leurs éléments dans `self.contenu` (une disposition verticale).
    """

    def __init__(self, titre: str, sous_titre: str, largeur_max: int | None = Dimensions.CONTENU_LARGEUR_MAX):
        super().__init__()
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)
        zone, self.contenu = zone_defilante(
            largeur_max, (Espacements.XXL, Espacements.XL, Espacements.XXL, Espacements.XXL)
        )
        disposition.addWidget(zone)
        entete = entete_de_page(titre, sous_titre)
        self.titre, self.sous_titre = entete.titre, entete.sous_titre
        self.contenu.addLayout(entete)
        self.contenu.addSpacing(Espacements.S)
