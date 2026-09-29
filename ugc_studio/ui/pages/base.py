"""Structure commune des pages : titre, sous-titre, puis le contenu (qui défile si besoin)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ..composants.elements import libelle
from ..theme import Dimensions, Espacements


class Page(QWidget):
    """Page avec un en-tête (titre + sous-titre) et une zone de contenu défilante.

    Les pages ajoutent leurs éléments dans `self.contenu` (une disposition verticale).
    """

    def __init__(self, titre: str, sous_titre: str, largeur_max: int | None = Dimensions.CONTENU_LARGEUR_MAX):
        super().__init__()
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)

        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setFrameShape(QFrame.Shape.NoFrame)
        zone.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        disposition.addWidget(zone)

        interieur = QWidget()
        interieur.setObjectName("contenuDefilant")
        zone.setWidget(interieur)
        marges = QVBoxLayout(interieur)
        marges.setContentsMargins(Espacements.XXL, Espacements.XL, Espacements.XXL, Espacements.XXL)
        marges.setSpacing(0)

        # La colonne de contenu occupe toute la largeur disponible, sans dépasser `largeur_max`
        # (au-delà, les lignes de texte deviennent trop longues à lire) ; elle reste calée à gauche.
        colonne = QWidget()
        if largeur_max is not None:
            colonne.setMaximumWidth(largeur_max)
        self.contenu = QVBoxLayout(colonne)
        self.contenu.setContentsMargins(0, 0, 0, 0)
        self.contenu.setSpacing(Espacements.L)
        ligne = QHBoxLayout()
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.addWidget(colonne, 1)
        ligne.addStretch(0)
        marges.addLayout(ligne)
        marges.addStretch(1)

        entete = QVBoxLayout()
        entete.setSpacing(Espacements.XS)
        self.titre = libelle(titre, "titre-page")
        entete.addWidget(self.titre)
        entete.addWidget(libelle(sous_titre, "secondaire"))
        self.contenu.addLayout(entete)
        self.contenu.addSpacing(Espacements.S)
