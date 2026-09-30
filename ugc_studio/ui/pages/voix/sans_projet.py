"""Écran affiché quand aucun projet n'est ouvert : créer un projet, en ouvrir un, ou un récent."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout

from ....services import Services
from ...actions_projet import nouveau_projet, ouvrir_projet
from ...composants.elements import bloc, bouton, libelle, vider_disposition
from ...theme import Espacements
from ..base import Page


class SansProjet(Page):
    """Affiché par les modules qui travaillent dans un projet (Voix, Transcription…)."""

    def __init__(self, services: Services, titre: str = "Voix", sous_titre: str = "Voix off générée par IA (TTS)."):
        super().__init__(titre, sous_titre)
        self._services = services

        cadre, d = bloc("Commence par un projet")
        d.addWidget(
            libelle(
                "Un projet regroupe le script, les prises audio, la transcription et les réglages d'une pub. "
                "Tout est enregistré automatiquement dans son dossier.",
                "secondaire",
            )
        )
        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        boutons.addWidget(
            bouton("Nouveau projet", variante="principal", nom_icone="folder-plus", action=lambda: nouveau_projet(self, services))
        )
        boutons.addWidget(bouton("Ouvrir un projet…", nom_icone="folder-open", action=lambda: ouvrir_projet(self, services)))
        boutons.addStretch(1)
        d.addLayout(boutons)
        self.contenu.addWidget(cadre)

        self._cadre_recents, self._recents = bloc("Projets récents")
        self.contenu.addWidget(self._cadre_recents)
        self.rafraichir()

    def rafraichir(self) -> None:
        vider_disposition(self._recents)
        self._recents.addWidget(libelle("Projets récents", "titre-bloc"))
        recents = self._services.projets.recents()
        self._cadre_recents.setVisible(bool(recents))
        for nom, dossier in recents:
            ligne = QHBoxLayout()
            ligne.addWidget(
                bouton(nom, variante="discret", nom_icone="folder-open", action=lambda _coche=False, d=dossier: ouvrir_projet(self, self._services, d))
            )
            ligne.addWidget(libelle(str(dossier), "legende"), 1)
            self._recents.addLayout(ligne)
