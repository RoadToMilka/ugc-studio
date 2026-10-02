"""Bandeau du haut (§9.6, V3.1) : le titre du module affiché à gauche, avec son sous-titre et le
bouton « Conseils » au bout ; une fine ligne verticale, puis le coût de la session à droite.

Chaque page garde son propre en-tête (titre, sous-titre, « Conseils ») : la fenêtre le confie au
bandeau, qui montre celui de la page affichée. Pourquoi ? Le titre ne prend plus de place en haut de
chaque page (les blocs commencent plus haut), et il reste toujours visible quand la page défile.
Jusqu'à la 3.0.0, le bandeau montrait le projet ouvert, qui est maintenant en haut de la barre
latérale.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from ...montants import Montant
from ..theme import Espacements, Hauteurs, Typo
from .conseils import bouton_conseils
from .elements import libelle, libelle_abrege, separateur_vertical
from .montant_label import MontantLabel


class EnteteDePage(QWidget):
    """Titre d'une page (« Voix • Sérum Glowzy »), son sous-titre dessous et, au bout de la ligne,
    le bouton « Conseils » de la page (`conseils` : la page de conseils_des_pages.PAGES à ouvrir).
    Titre et sous-titre s'abrègent par « … » quand la place manque, texte complet au survol."""

    def __init__(self, titre: str, sous_titre: str, conseils: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.L)
        # Titre et sous-titre serrés l'un sous l'autre, centrés ensemble dans la hauteur du bandeau.
        textes = QVBoxLayout()
        textes.setContentsMargins(0, 0, 0, 0)
        textes.setSpacing(Espacements.XS)
        self.titre = libelle_abrege(titre, "titre-page")
        self.sous_titre = libelle_abrege(sous_titre, "secondaire")
        textes.addStretch(1)
        textes.addWidget(self.titre)
        textes.addWidget(self.sous_titre)
        textes.addStretch(1)
        disposition.addLayout(textes, 1)
        self.conseils = bouton_conseils(conseils) if conseils else None
        if self.conseils is not None:
            disposition.addWidget(self.conseils, 0, Qt.AlignmentFlag.AlignVCenter)


class Entete(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("entete")
        self.setFixedHeight(Hauteurs.BANDEAU)
        disposition = QHBoxLayout(self)
        # Le titre s'aligne sur le bord gauche des blocs de la page, le coût sur leur bord droit.
        disposition.setContentsMargins(Espacements.L, 0, Espacements.L, 0)
        disposition.setSpacing(Espacements.L)

        # À gauche : l'en-tête de la page affichée (voir EnteteDePage) ; une place vide pour une page
        # qui n'en a pas : le coût reste à droite.
        self._pages = QStackedWidget()
        self._vide = QWidget()
        self._pages.addWidget(self._vide)
        disposition.addWidget(self._pages, 1)

        disposition.addWidget(separateur_vertical(), 0, Qt.AlignmentFlag.AlignVCenter)

        # À droite : coût de la session (légende et montant serrés, centrés en hauteur)
        droite = QVBoxLayout()
        droite.setSpacing(0)
        droite.addStretch(1)
        legende_cout = libelle("Coût de la session", "legende", retour_a_la_ligne=False)
        legende_cout.setAlignment(Qt.AlignmentFlag.AlignRight)
        droite.addWidget(legende_cout)
        self.cout_session = MontantLabel(0, Typo.TITRE_PAGE)
        self.cout_session.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.cout_session.setToolTip("Total des appels API depuis l'ouverture de l'app")
        droite.addWidget(self.cout_session)
        droite.addStretch(1)
        disposition.addLayout(droite)

    # --- En-têtes des pages ------------------------------------------------------------------

    def ajouter(self, entete: EnteteDePage) -> None:
        """Le bandeau prend en charge l'en-tête d'une page (il quitte la page)."""
        self._pages.addWidget(entete)

    def montrer(self, entete: EnteteDePage | None) -> None:
        """Montre l'en-tête de la page affichée (rien, si elle n'en a pas)."""
        if entete is not None and self._pages.indexOf(entete) >= 0:
            self._pages.setCurrentWidget(entete)
        else:
            self._pages.setCurrentWidget(self._vide)

    def entete_affichee(self) -> EnteteDePage | None:
        entete = self._pages.currentWidget()
        return entete if isinstance(entete, EnteteDePage) else None

    # --- Coût de la session ------------------------------------------------------------------

    def definir_cout_session(self, montant: Montant) -> None:
        self.cout_session.definir_montant(montant)
