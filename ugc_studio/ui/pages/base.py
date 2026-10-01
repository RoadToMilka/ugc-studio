"""Structure commune des pages : titre, sous-titre, puis le contenu (qui défile si besoin)."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ..composants.conseils import bouton_conseils
from ..composants.defilement import zone_defilante
from ..composants.elements import libelle
from ..theme import Espacements


def entete_de_page(titre: str, sous_titre: str, conseils: str | None = None) -> QVBoxLayout:
    """Titre + sous-titre d'une page, et le bouton « Conseils » en haut à droite, sur la ligne du
    titre (`conseils` : la page de conseils_des_pages.PAGES à ouvrir). Les éléments restent
    accessibles : `entete.titre`, `entete.sous_titre`, `entete.conseils` (ou None)."""
    entete = QVBoxLayout()
    entete.setContentsMargins(0, 0, 0, 0)
    entete.setSpacing(Espacements.XS)
    ligne = QHBoxLayout()
    ligne.setContentsMargins(0, 0, 0, 0)
    ligne.setSpacing(Espacements.S)
    entete.titre = libelle(titre, "titre-page")
    ligne.addWidget(entete.titre, 1)
    entete.conseils = bouton_conseils(conseils) if conseils else None
    if entete.conseils is not None:
        ligne.addWidget(entete.conseils)
    entete.addLayout(ligne)
    entete.sous_titre = libelle(sous_titre, "secondaire")
    entete.addWidget(entete.sous_titre)
    return entete


class Page(QWidget):
    """Page avec un en-tête (titre + sous-titre) et une zone de contenu défilante.

    Les pages ajoutent leurs éléments dans `self.contenu` (une disposition verticale).
    """

    def __init__(self, titre: str, sous_titre: str, largeur_max: int | None = None, conseils: str | None = None):
        super().__init__()
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)
        zone, self.contenu = zone_defilante(
            largeur_max, (Espacements.XXL, Espacements.XL, Espacements.XXL, Espacements.XXL)
        )
        self.defilement = zone  # pour amener un élément à l'écran (ensureWidgetVisible)
        disposition.addWidget(zone)
        entete = entete_de_page(titre, sous_titre, conseils)
        self.titre, self.sous_titre, self.bouton_conseils = entete.titre, entete.sous_titre, entete.conseils
        self.contenu.addLayout(entete)
        self.contenu.addSpacing(Espacements.S)
