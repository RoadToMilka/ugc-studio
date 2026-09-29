"""Page Voix (§5) : sans projet ouvert, propose d'en créer un ; sinon, l'atelier de voix off."""

from __future__ import annotations

from PySide6.QtWidgets import QStackedWidget

from ....projets import Projet
from ....services import Services
from .atelier import AtelierVoix
from .sans_projet import SansProjet


class PageVoix(QStackedWidget):
    def __init__(self, services: Services):
        super().__init__()
        self.sans_projet = SansProjet(services)
        self.atelier = AtelierVoix(services)
        self.addWidget(self.sans_projet)
        self.addWidget(self.atelier)
        services.projets.abonner(self._projet_change)
        self._projet_change(services.projets.projet)

    def _projet_change(self, projet: Projet | None) -> None:
        self.setCurrentWidget(self.atelier if projet is not None else self.sans_projet)
        if projet is None:
            self.sans_projet.rafraichir()
