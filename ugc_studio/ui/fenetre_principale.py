"""Fenêtre principale (§9.6) : barre latérale à gauche, bandeau en haut, module au centre."""

from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from .. import NOM_APP
from ..ecriture.scripts import ScriptEcrit
from ..nombres import FRANCE, VARIANTE_DE_LANGUE
from ..projets import ErreurProjet, Projet, RepliqueProjet
from ..services import Services
from .actions_projet import remplir_menu_projet
from .composants.barre_laterale import BarreLaterale, Module
from .composants.entete import Entete
from .pages.reglages import PageReglages
from .pages.script import PageScript
from .pages.sous_titres import PageSousTitres
from .pages.transcription import PageTranscription
from .pages.voix import PageVoix
from .theme import Dimensions

journal = logging.getLogger(__name__)

# Le module Script vient en tête (V2) : c'est la première étape d'une pub.
MODULES_HAUT = (
    Module("script", "Script", "scroll-text"),
    Module("voix", "Voix", "mic"),
    Module("transcription", "Transcription", "audio-lines"),
    Module("sous-titres", "Sous-titres", "captions"),
)
MODULES_BAS = (Module("reglages", "Réglages", "settings"),)


def _creer_pages(services: Services) -> dict[str, QWidget]:
    return {
        "script": PageScript(services),
        "voix": PageVoix(services),
        "transcription": PageTranscription(services),
        "sous-titres": PageSousTitres(services),
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

        # « Créer les sous-titres » d'une prise (§3.3) : depuis la liste des prises du module Voix.
        self.page("voix").atelier.prises.sous_titres_demandes.connect(self.creer_sous_titres)
        # « Corriger les mots » des sous-titres : dans le module Transcription.
        self.page("sous-titres").atelier.corriger_demande.connect(lambda: self.afficher_module("transcription"))
        # « Envoyer dans Voix » d'un script (V2) : ses répliques remplacent celles du module Voix.
        self.page("script").atelier.envoi_demande.connect(self.envoyer_dans_voix)
        # Accroches d'une série « Accroches seulement » (V2, lot 2) : en variantes A/B de voix.
        self.page("script").atelier.variantes_voix_demandees.connect(self.envoyer_accroches_en_variantes)

        self.barre_laterale.module_selectionne.connect(self.afficher_module)
        self._restaurer_etat()
        self._rouvrir_dernier_projet()

    # --- Projet ------------------------------------------------------------------------------

    def _projet_change(self, projet: Projet | None) -> None:
        self.entete.definir_projet(projet.nom if projet else None)
        self.setWindowTitle(f"{NOM_APP} / {projet.nom}" if projet else NOM_APP)

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
        precedente = self.pages.currentWidget()
        if precedente is not None and precedente is not self.page(identifiant) and hasattr(precedente, "quitter"):
            precedente.quitter()  # ex. la lecture de la page quittée s'arrête
        self.pages.setCurrentIndex(self._index_pages[identifiant])
        self.barre_laterale.selectionner(identifiant)

    def creer_sous_titres(self, identifiant_prise: str) -> None:
        """« Créer les sous-titres de cette prise » : ouvre le module Sous-titres et s'en charge."""
        self.afficher_module("sous-titres")
        self.page("sous-titres").atelier.creer_depuis_prise(identifiant_prise)

    def envoyer_dans_voix(self, script: ScriptEcrit) -> bool:
        """« Envoyer dans Voix » : les répliques du script (styles, balises, mots accentués) remplacent
        celles du module Voix, après confirmation s'il contient déjà un script ; puis le module Voix
        s'ouvre, prêt pour « Générer l'audio ». Un script en français de Belgique ou de Suisse règle
        aussi les nombres dits (septante, nonante…). Renvoie True si c'est fait."""
        atelier_script = self.page("script").atelier
        atelier_script.enregistrer_maintenant()
        repliques = [RepliqueProjet([dict(s) for s in r.script], r.style, r.style_fr) for r in script.repliques]
        nombres = VARIANTE_DE_LANGUE.get(script.langue, FRANCE) if script.langue.startswith("fr") else None
        if not self.page("voix").atelier.remplacer_repliques(repliques, nombres=nombres):
            return False
        atelier_script.script_envoye(script)
        self.afficher_module("voix")
        return True

    def envoyer_accroches_en_variantes(self, scripts: list[ScriptEcrit]) -> None:
        """« Envoyer les accroches en variantes » : le script de la variante A part dans le module Voix,
        puis la fenêtre Variantes s'ouvre sur « Réglages par variante », une variante par accroche."""
        if len(scripts) < 2 or not self.envoyer_dans_voix(scripts[0]):
            return
        accroches = [
            RepliqueProjet([dict(s) for s in script.repliques[0].script], script.repliques[0].style, script.repliques[0].style_fr)
            for script in scripts
            if script.repliques
        ]
        atelier_script = self.page("script").atelier
        for script in scripts[1:]:
            atelier_script.script_envoye(script)
        self.page("voix").atelier.ouvrir_variantes_d_accroches(accroches)

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
        self.page("script").atelier.enregistrer_maintenant()
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
