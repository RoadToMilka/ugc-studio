"""Page Sous-titres (§7) : sans projet ouvert, propose d'en créer un ; sinon, l'atelier."""

from __future__ import annotations

from PySide6.QtWidgets import QStackedWidget

from ....projets import Projet
from ....services import Services
from ..voix.sans_projet import SansProjet
from .atelier import SOUS_TITRE, TITRE, AtelierSousTitres


class PageSousTitres(QStackedWidget):
    def __init__(self, services: Services):
        super().__init__()
        self.sans_projet = SansProjet(services, TITRE, SOUS_TITRE, "sous-titres")
        self.atelier = AtelierSousTitres(services)
        self.addWidget(self.sans_projet)
        self.addWidget(self.atelier)
        services.projets.abonner(self._projet_change)
        self._projet_change(services.projets.projet)

    def _projet_change(self, projet: Projet | None) -> None:
        self.setCurrentWidget(self.atelier if projet is not None else self.sans_projet)
        if projet is None:
            self.sans_projet.rafraichir()

    def quitter(self) -> None:
        """Appelé quand on passe à un autre module."""
        self.atelier.quitter()
