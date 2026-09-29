"""Bandeau du haut (§9.6) : nom du projet à gauche, coût de la session à droite (format §4.4)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout

from ...montants import Montant
from ..theme import Espacements, Typo
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

        # À gauche : projet ouvert
        gauche = QVBoxLayout()
        gauche.setSpacing(0)
        gauche.addWidget(libelle("Projet", "legende", retour_a_la_ligne=False))
        self.nom_projet = libelle(TEXTE_SANS_PROJET, "titre-bloc", retour_a_la_ligne=False)
        gauche.addWidget(self.nom_projet)
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

    def definir_projet(self, nom: str | None) -> None:
        self.nom_projet.setText(nom or TEXTE_SANS_PROJET)
        # Propriété « vide » : grise le texte quand aucun projet n'est ouvert (voir theme.py).
        self.nom_projet.setProperty("vide", not nom)
        self.nom_projet.style().unpolish(self.nom_projet)
        self.nom_projet.style().polish(self.nom_projet)

    def definir_cout_session(self, montant: Montant) -> None:
        self.cout_session.definir_montant(montant)
