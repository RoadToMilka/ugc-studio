"""Page Transcription (§6) : sans projet ouvert, propose d'en créer un ; sinon, l'atelier."""

from __future__ import annotations

from PySide6.QtWidgets import QStackedWidget

from ....projets import Projet
from ....services import Services
from ..voix.sans_projet import SansProjet
from .atelier import AtelierTranscription

TITRE = "Transcription"
SOUS_TITRE = "Le texte d'une vidéo ou d'un audio, mot par mot, pour créer les sous-titres."


class PageTranscription(QStackedWidget):
    def __init__(self, services: Services):
        super().__init__()
        self.sans_projet = SansProjet(services, TITRE, SOUS_TITRE, "transcription")
        self.atelier = AtelierTranscription(services)
        self.addWidget(self.sans_projet)
        self.addWidget(self.atelier)
        services.projets.abonner(self._projet_change)
        self._projet_change(services.projets.projet)

    def _projet_change(self, projet: Projet | None) -> None:
        self.setCurrentWidget(self.atelier if projet is not None else self.sans_projet)
        if projet is None:
            self.sans_projet.rafraichir()

    def quitter(self) -> None:
        """Appelé quand on passe à un autre module : la lecture s'arrête et libère la piste son
        (la page Sous-titres peut la remplacer par l'audio d'une prise)."""
        self.atelier.lecteur.arreter()
