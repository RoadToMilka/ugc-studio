"""Fenêtre principale (§9.6) : barre latérale à gauche, bandeau en haut, module au centre."""

from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from .. import NOM_APP
from ..projets import ErreurProjet, Projet
from ..services import Services
from .actions_projet import remplir_menu_projet
from .composants.barre_laterale import BarreLaterale, Module
from .composants.entete import Entete
from .pages.page_a_venir import PageAVenir
from .pages.reglages import PageReglages
from .pages.voix import PageVoix
from .theme import Dimensions

journal = logging.getLogger(__name__)

MODULES_HAUT = (
    Module("voix", "Voix", "mic"),
    Module("transcription", "Transcription", "audio-lines"),
    Module("sous-titres", "Sous-titres", "captions"),
)
MODULES_BAS = (Module("reglages", "Réglages", "settings"),)


def _creer_pages(services: Services) -> dict[str, QWidget]:
    return {
        "voix": PageVoix(services),
        "transcription": PageAVenir(
            "Transcription",
            "Texte horodaté mot par mot à partir d'une vidéo ou d'un audio (STT).",
            "Étape 7",
            [
                "Import d'une vidéo ou d'un audio par glisser-déposer",
                "Transcription mot par mot avec horodatage",
                "Séparation des voix et dictionnaire de remplacements",
                "Éditeur de transcription synchronisé avec la lecture",
            ],
        ),
        "sous-titres": PageAVenir(
            "Sous-titres",
            "Découpage, style et export des sous-titres.",
            "Étape 8",
            [
                "« Créer les sous-titres de cette prise » : alignement sur le script",
                "Règles de découpage : caractères, mots, lignes, marges",
                "Export SRT pour Premiere Pro",
            ],
        ),
        "reglages": PageReglages(services),
    }


class FenetrePrincipale(QMainWindow):
    def __init__(self, services: Services):
        super().__init__()
        self.services = services
        self._preferences = services.preferences
        self.setWindowTitle(NOM_APP)
        self.setMinimumSize(Dimensions.FENETRE_LARGEUR_MIN, Dimensions.FENETRE_HAUTEUR_MIN)

        racine = QFrame()
        racine.setObjectName("racine")
        # À l'ouverture, le « focus » clavier est posé sur le fond de la fenêtre plutôt que sur
        # le premier bouton : aucun contour de focus n'apparaît tant qu'on n'utilise pas Tab.
        racine.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        racine.setFocus()
        disposition = QHBoxLayout(racine)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)

        self.barre_laterale = BarreLaterale(MODULES_HAUT, MODULES_BAS)
        disposition.addWidget(self.barre_laterale)

        colonne = QVBoxLayout()
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(0)
        self.entete = Entete()
        colonne.addWidget(self.entete)
        self.pages = QStackedWidget()
        colonne.addWidget(self.pages, 1)
        disposition.addLayout(colonne, 1)
        self.setCentralWidget(racine)

        self._index_pages: dict[str, int] = {}
        for identifiant, page in _creer_pages(services).items():
            self._index_pages[identifiant] = self.pages.addWidget(page)

        # Compteur de coût de la session (bandeau du haut) : mis à jour à chaque appel payant.
        services.couts.abonner(lambda _appel: self.entete.definir_cout_session(services.couts.cout_session))
        self.entete.definir_cout_session(services.couts.cout_session)

        # Menu « Projet » du bandeau, reconstruit à chaque ouverture (pour les projets récents).
        self.entete.menu_projet.aboutToShow.connect(
            lambda: remplir_menu_projet(self.entete.menu_projet, self, services)
        )
        services.projets.abonner(self._projet_change)

        self.barre_laterale.module_selectionne.connect(self.afficher_module)
        self._restaurer_etat()
        self._rouvrir_dernier_projet()

    # --- Projet ------------------------------------------------------------------------------

    def _projet_change(self, projet: Projet | None) -> None:
        self.entete.definir_projet(projet.nom if projet else None)
        self.setWindowTitle(f"{projet.nom} — {NOM_APP}" if projet else NOM_APP)

    def _rouvrir_dernier_projet(self) -> None:
        """Au démarrage, le dernier projet utilisé est rouvert automatiquement."""
        if self.services.projets.projet is not None:
            self._projet_change(self.services.projets.projet)
            return
        dernier = self.services.projets.dernier_projet()
        if dernier is None:
            return
        try:
            self.services.projets.ouvrir(dernier)
        except ErreurProjet:
            journal.warning("Dernier projet non rouvert : %s", dernier, exc_info=True)

    # --- Navigation -------------------------------------------------------------------------

    def page(self, identifiant: str) -> QWidget:
        return self.pages.widget(self._index_pages[identifiant])

    def identifiants_modules(self) -> list[str]:
        return list(self._index_pages)

    def module_actuel(self) -> str:
        index = self.pages.currentIndex()
        return next(ident for ident, i in self._index_pages.items() if i == index)

    def afficher_module(self, identifiant: str) -> None:
        if identifiant not in self._index_pages:
            return
        self.pages.setCurrentIndex(self._index_pages[identifiant])
        self.barre_laterale.selectionner(identifiant)

    # --- Mémoire de la fenêtre (taille, position, dernier module) ----------------------------

    def _restaurer_etat(self) -> None:
        geometrie = self._preferences.lire("geometrie_fenetre")
        restauree = False
        if isinstance(geometrie, str):
            restauree = self.restoreGeometry(QByteArray.fromBase64(geometrie.encode("ascii")))
        if not restauree:
            self._taille_par_defaut()
        self.afficher_module(self._preferences.lire("module", MODULES_HAUT[0].identifiant))
        if self.pages.currentIndex() < 0:
            self.afficher_module(MODULES_HAUT[0].identifiant)
        self.barre_laterale.selectionner(self.module_actuel())

    def _taille_par_defaut(self) -> None:
        """Premier lancement : fenêtre confortable, jamais plus grande que l'écran, centrée."""
        ecran = self.screen().availableGeometry()
        largeur = min(Dimensions.FENETRE_LARGEUR, int(ecran.width() * Dimensions.FENETRE_PART_ECRAN_MAX))
        hauteur = min(Dimensions.FENETRE_HAUTEUR, int(ecran.height() * Dimensions.FENETRE_PART_ECRAN_MAX))
        self.resize(max(largeur, Dimensions.FENETRE_LARGEUR_MIN), max(hauteur, Dimensions.FENETRE_HAUTEUR_MIN))
        cadre = self.frameGeometry()
        cadre.moveCenter(ecran.center())
        self.move(cadre.topLeft())

    def closeEvent(self, evenement) -> None:
        voix = self.page("voix")
        voix.atelier.lecteur.arreter()
        voix.atelier.enregistrer_maintenant()
        self._preferences.ecrire("geometrie_fenetre", bytes(self.saveGeometry().toBase64()).decode("ascii"))
        self._preferences.ecrire("module", self.module_actuel())
        try:
            self._preferences.enregistrer()
        except OSError:
            journal.exception("Impossible d'enregistrer les préférences")
        super().closeEvent(evenement)
