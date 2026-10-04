"""Fenêtre principale (§9.6) : barre latérale à gauche (le projet ouvert en haut), bandeau en haut
(titre du module affiché, « Conseils », coût de la session), module au centre."""

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
from .composants.elements import titre_avec
from .composants.entete import Entete
from .pages.base import Page
from .pages.images import PageImages
from .pages.reglages import PageReglages
from .pages.renommer import PageRenommer
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
# V4 : les outils, des modules sans projet, dans leur groupe sous les modules d'une pub.
MODULES_OUTILS = (Module("images", "Images", "image"), Module("renommer", "Renommer", "list-ordered"))


def _creer_pages(services: Services) -> dict[str, QWidget]:
    return {
        "script": PageScript(services),
        "voix": PageVoix(services),
        "transcription": PageTranscription(services),
        "sous-titres": PageSousTitres(services),
        "images": PageImages(services),
        "renommer": PageRenommer(services),
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

        self.barre_laterale = BarreLaterale(MODULES_HAUT, MODULES_BAS, MODULES_OUTILS)
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
            self._confier_les_entetes(page)
        self.pages.currentChanged.connect(lambda _index: self._montrer_l_entete())

        # Compteur de coût de la session (bandeau du haut) : mis à jour à chaque appel payant.
        services.couts.abonner(lambda _appel: self.entete.definir_cout_session(services.couts.cout_session))
        self.entete.definir_cout_session(services.couts.cout_session)

        # Menu « Projet » (haut de la barre latérale), reconstruit à chaque ouverture (projets récents).
        menu_projet = self.barre_laterale.menu_projet
        menu_projet.aboutToShow.connect(lambda: remplir_menu_projet(menu_projet, self, services))
        services.projets.abonner(self._projet_change)

        # « Créer les sous-titres » d'une prise (§3.3) : depuis la liste des prises du module Voix.
        self.page("voix").atelier.prises.sous_titres_demandes.connect(self.creer_sous_titres)
        # « Corriger les mots » des sous-titres : dans le module Transcription (sur le premier mot d'un
        # sous-titre, depuis la frise du studio).
        self.page("sous-titres").atelier.corriger_demande.connect(self.corriger_les_mots)
        # Zone Source des sous-titres (V3.1, lot 6) : le module Transcription importe et transcrit pour
        # elle, avec ses options ; les deux modules montrent la même vidéo.
        self.page("sous-titres").atelier.relier_transcription(self.page("transcription").atelier)
        # « Envoyer dans Voix » d'un script (V2) : ses répliques remplacent celles du module Voix.
        self.page("script").atelier.envoi_demande.connect(self.envoyer_dans_voix)
        # Accroches d'une série « Accroches seulement » (V2, lot 2) : en variantes A/B de voix.
        self.page("script").atelier.variantes_voix_demandees.connect(self.envoyer_accroches_en_variantes)
        # « Trier et renommer » (V4, lot 2) : à la fin du module Images, le module Renommer sur les
        # images faites.
        self.page("images").renommer_demande.connect(self.trier_et_renommer)

        self.barre_laterale.module_selectionne.connect(self.afficher_module)
        self._restaurer_etat()
        self._rouvrir_dernier_projet()
        self._montrer_l_entete()  # le module affiché au départ n'a pas forcément changé de page

    # --- Projet ------------------------------------------------------------------------------

    def _projet_change(self, projet: Projet | None) -> None:
        self.barre_laterale.definir_projet(projet.nom if projet else None)
        self.setWindowTitle(titre_avec(NOM_APP, projet.nom) if projet else NOM_APP)

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

    # --- En-têtes des pages (bandeau) ---------------------------------------------------------

    def _confier_les_entetes(self, module: QWidget) -> None:
        """Les en-têtes (titre, sous-titre, « Conseils ») des pages d'un module passent dans le
        bandeau. Un module avec et sans projet ouvert a deux pages (ex. Voix : « Commence par un
        projet », puis l'atelier) : le bandeau montre celui de la page affichée."""
        pages = [module] if isinstance(module, Page) else []
        pages += module.findChildren(Page)
        for page in pages:
            self.entete.ajouter(page.detacher_entete())
        if isinstance(module, QStackedWidget):
            module.currentChanged.connect(lambda _index: self._montrer_l_entete())

    def page_affichee(self) -> Page | None:
        """La page visible : celle du module affiché (avec ou sans projet ouvert)."""
        page = self.pages.currentWidget()
        while isinstance(page, QStackedWidget):
            page = page.currentWidget()
        return page if isinstance(page, Page) else None

    def _montrer_l_entete(self) -> None:
        page = self.page_affichee()
        self.entete.montrer(page.entete if page is not None else None)

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

    def trier_et_renommer(self, dossier) -> None:
        """« Trier et renommer » (module Images) : le module Renommer s'ouvre sur ce dossier."""
        self.afficher_module("renommer")
        self.page("renommer").ouvrir(dossier)

    def corriger_les_mots(self, temps: float = -1.0) -> None:
        """« Corriger les mots » : le module Transcription s'ouvre ; depuis la frise des sous-titres,
        le mot qui commence à `temps` y est choisi (-1 : aucun)."""
        self.afficher_module("transcription")
        if temps >= 0:
            self.page("transcription").atelier.choisir_mot_au_temps(temps)

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
        self.page("images").arreter()  # images pas encore commencées : elles ne le seront plus
        self.page("renommer").arreter()  # vignettes pas encore faites : elles ne le seront plus
        self._preferences.ecrire("geometrie_fenetre", bytes(self.saveGeometry().toBase64()).decode("ascii"))
        self._preferences.ecrire("module", self.module_actuel())
        try:
            self._preferences.enregistrer()
        except OSError:
            journal.exception("Impossible d'enregistrer les préférences")
        super().closeEvent(evenement)
