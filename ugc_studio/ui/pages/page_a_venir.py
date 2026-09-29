"""Page provisoire d'un module pas encore construit : elle annonce ce qui arrive et quand."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel

from ..composants.elements import bloc, libelle, pastille
from ..icones import icone
from ..theme import Couleurs, Dimensions, Espacements
from .base import Page


class PageAVenir(Page):
    def __init__(self, titre: str, sous_titre: str, etapes: str, fonctions: list[str]):
        super().__init__(titre, sous_titre)

        cadre, disposition = bloc()
        ligne_titre = QHBoxLayout()
        ligne_titre.setSpacing(0)
        sablier = QLabel()
        sablier.setPixmap(
            icone("hourglass", Couleurs.ACCENT_SURVOL).pixmap(
                Dimensions.ICONE, Dimensions.ICONE
            )
        )
        ligne_titre.addWidget(sablier)
        ligne_titre.addSpacing(Dimensions.ECART_ICONE_TEXTE)  # même écart icône → texte que partout
        ligne_titre.addWidget(libelle("Ce module arrive bientôt", "titre-bloc", retour_a_la_ligne=False))
        ligne_titre.addSpacing(Espacements.S)
        ligne_titre.addWidget(pastille(etapes), 0, Qt.AlignmentFlag.AlignVCenter)
        ligne_titre.addStretch(1)
        disposition.addLayout(ligne_titre)

        for fonction in fonctions:
            disposition.addWidget(libelle(f"•  {fonction}", "secondaire"))

        self.contenu.addWidget(cadre)
