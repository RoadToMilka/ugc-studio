"""Page Réglages (§4) : quatre onglets."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from ....services import Services
from ...composants.onglets import Onglets
from ...theme import Espacements
from ..base import entete_de_page
from .onglet_connexions import OngletConnexions
from .onglet_couts import OngletCouts
from .onglet_donnees import OngletDonnees
from .onglet_modeles import OngletModeles


class PageReglages(QWidget):
    def __init__(self, services: Services):
        super().__init__()
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XXL, Espacements.XL, Espacements.XXL, 0)
        disposition.setSpacing(Espacements.L)
        entete = entete_de_page(
            "Réglages", "Connexions API, modèles et prix, suivi des coûts, journal et données.", "reglages"
        )
        self.bouton_conseils = entete.conseils
        disposition.addLayout(entete)

        self.onglets = Onglets()
        self.connexions = OngletConnexions(services)
        self.modeles = OngletModeles(services)
        self.couts = OngletCouts(services)
        self.donnees = OngletDonnees()
        self.onglets.addTab(self.connexions, "Connexions API")
        self.onglets.addTab(self.modeles, "Modèles et prix")
        self.onglets.addTab(self.couts, "Suivi des coûts")
        self.onglets.addTab(self.donnees, "Journal et données")
        disposition.addWidget(self.onglets, 1)
