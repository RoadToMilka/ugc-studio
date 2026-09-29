"""Bandeau du haut (§9.6) : projet ouvert à gauche (cliquable : menu Projet), coût de la session à droite."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMenu, QPushButton, QVBoxLayout

from ...montants import Montant
from ..icones import icone
from ..theme import Couleurs, Dimensions, Espacements, Typo
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
        self.bouton_projet = QPushButton(TEXTE_SANS_PROJET)
        self.bouton_projet.setProperty("variante", "projet")
        self.bouton_projet.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_projet.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.bouton_projet.setIcon(icone("chevron-down", Couleurs.TEXTE_SECONDAIRE))
        self.bouton_projet.setIconSize(QSize(Dimensions.ICONE_PETITE, Dimensions.ICONE_PETITE))
        self.bouton_projet.setLayoutDirection(Qt.LayoutDirection.RightToLeft)  # flèche après le nom
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
        # Propriété « vide » : grise le texte quand aucun projet n'est ouvert (voir theme.py).
        self.bouton_projet.setProperty("vide", not nom)
        self.bouton_projet.style().unpolish(self.bouton_projet)
        self.bouton_projet.style().polish(self.bouton_projet)

    def definir_cout_session(self, montant: Montant) -> None:
        self.cout_session.definir_montant(montant)
