"""Bandeau du haut (§9.6) : projet ouvert à gauche (cliquable : menu Projet), coût de la session à droite."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMenu, QVBoxLayout

from ...montants import Montant
from ..theme import Espacements, Typo
from .bouton import Bouton
from .elements import libelle
from .montant_label import MontantLabel

TEXTE_SANS_PROJET = "Aucun projet ouvert"


class Entete(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("entete")
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.M, Espacements.XL, Espacements.M)
        disposition.setSpacing(Espacements.L)

        # À gauche : projet ouvert. Un clic ouvre le menu Projet (nouveau, ouvrir, récents…).
        gauche = QVBoxLayout()
        gauche.setSpacing(0)
        gauche.addWidget(libelle("Projet", "legende", retour_a_la_ligne=False))
        # Flèche après le nom, séparée par le même écart que partout (Dimensions.ECART_ICONE_TEXTE).
        self.bouton_projet = Bouton(TEXTE_SANS_PROJET, "projet", "chevron-down", icone_a_droite=True)
        self.bouton_projet.setToolTip("Nouveau projet, ouvrir un projet, projets récents…")
        self.menu_projet = QMenu(self.bouton_projet)
        self.bouton_projet.setMenu(self.menu_projet)
        gauche.addWidget(self.bouton_projet, 0, Qt.AlignmentFlag.AlignLeft)
        disposition.addLayout(gauche)
        disposition.addStretch(1)

        # À droite : coût de la session
        droite = QVBoxLayout()
        droite.setSpacing(0)
        legende_cout = libelle("Coût de la session", "legende", retour_a_la_ligne=False)
        legende_cout.setAlignment(Qt.AlignmentFlag.AlignRight)
        droite.addWidget(legende_cout)
        self.cout_session = MontantLabel(0, Typo.TITRE_PAGE)
        self.cout_session.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.cout_session.setToolTip("Total des appels API depuis l'ouverture de l'app")
        droite.addWidget(self.cout_session)
        disposition.addLayout(droite)

        self.definir_projet(None)

    @property
    def nom_projet(self):
        return self.bouton_projet

    def definir_projet(self, nom: str | None) -> None:
        self.bouton_projet.setText(nom or TEXTE_SANS_PROJET)
        self.bouton_projet.definir_attenue(not nom)  # texte grisé quand aucun projet n'est ouvert

    def definir_cout_session(self, montant: Montant) -> None:
        self.cout_session.definir_montant(montant)
