"""Atelier du module Script (V2, §3.1 et §10) : page produit, brief, accroches, scripts écrits et
relus, envoi dans le module Voix.

Lot 2 : bibliothèque de briefs (« Charger un brief », « Enregistrer »), « Mes meilleurs scripts… »,
variantes de script (trois modes), retouche, copie, note ★ et « Retenir », comparaison, accroches
envoyées en variantes de voix, vitesse de parole mesurée sur les prises de la voix du projet.

Les appels au modèle partent en tâche de fond, un à la fois. Chaque appel terminé est noté tout de
suite dans le suivi des coûts (même si l'étape suivante échoue), et son coût est estimé avant de
lancer. Tout est enregistré automatiquement dans le projet (format 6).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QMessageBox, QWidget

from ....ecriture.brief import Brief
from ....ecriture.briefs import nom_propose
from ....ecriture.controles import controle_duree, controler
from ....ecriture.exemples import ExempleScript, choisir_exemples
from ....ecriture.fiche import FicheProduit
from ....ecriture.page_produit import (
    ErreurLecture,
    PageLue,
    lire_page,
    normaliser_adresse,
    page_collee,
)
from ....ecriture.redaction import (
    Appel,
    accroches_pour_corps,
    analyser_page,
    ecrire_script,
    estimer_accroches,
    estimer_lecture,
    estimer_script,
    lire_par_google,
    proposer_accroches,
    retoucher_script,
    variantes_d_accroches,
)
from ....ecriture.scripts import ScriptEcrit, dupliquer, repliques_pour_modele
from ....ecriture.variantes import ACCROCHES, LETTRES, MEMES, PAR_VARIANTE, ReglagesScript, nouvelle_serie
from ....fournisseurs.capacites import Capacite, deviner_capacites
from ....fournisseurs.google_voix import VOIX_PAR_DEFAUT
from ....modeles_charges import SCRIPT
from ....projets import Projet
from ....services import Services
from ....vitesses import Vitesse
from ... import taches
from ...composants.bouton import Bouton, BoutonOccupe, montrer_occupe
from ...composants.elements import BoutonInfo, bloc, bouton, libelle, ligne_avec_aide
from ...composants.lecteur import Lecteur
from ...composants.montant_label import MontantLabel
from ...connexion_ia import FOURNISSEUR, adaptateur_par_defaut, message_erreur
from ...dialogues.briefs import DialogueBibliothequeBriefs
from ...dialogues.comparer_scripts import DialogueComparerScripts
from ...dialogues.meilleurs_scripts import DialogueMeilleursScripts
from ...dialogues.prononciation import DialoguePrononciation
from ...dialogues.retouche import DialogueRetouche
from ...dialogues.variantes_script import DialogueVariantesScript
from ...extraits import EcouteVoix, fichier_prononciation
from ...theme import Espacements, Typo
from ..base import Page
from .formulaire import AIDE_BRIEF, FormulaireBrief
from .produit import BlocProduit, etat_de_la_page
from .resultats import ListeAccroches, ListeScripts

journal = logging.getLogger(__name__)

TITRE = "Script"
SOUS_TITRE = "Écris des scripts de pub UGC à partir de ta page produit, puis envoie-les dans le module Voix."
DELAI_ENREGISTREMENT_MS = 800
CLE_OPTIONS = "script_options"  # options d'écriture retenues d'une fois sur l'autre (préférences)
OPTIONS_RETENUES = ("balises", "styles", "accents", "modele", "nombre_accroches")
TEXTE_PAGE_TYPIQUE = 15_000  # caractères d'une page produit, pour estimer l'analyse avant la lecture
GENRES_DES_VOIX = {"female": "femme", "male": "homme"}


def copie(brief: Brief) -> Brief:
    """Copie indépendante du brief : la tâche de fond la lit pendant que tu continues à le modifier."""
    return Brief.depuis_dict(brief.en_dict())


@dataclass
class Travail:
    """Un script à écrire (ou, en mode « Accroches seulement », un script puis ses autres accroches)."""

    brief: Brief
    accroche: str = ""
    serie: str = ""
    lettre: str = ""
    mode: str = ""
    nombre: int = 1  # « Accroches seulement » : nombre de variantes (le script compris)


class AtelierScript(Page):
    envoi_demande = Signal(object)  # ScriptEcrit à envoyer dans le module Voix
    variantes_voix_demandees = Signal(object)  # scripts d'une série « Accroches seulement »

    def __init__(self, services: Services):
        super().__init__(TITRE, SOUS_TITRE, conseils="script")
        self._services = services
        self._projet: Projet | None = None
        self._occupe = False
        self._bouton_occupe = BoutonOccupe()  # le bouton où tourne le cercle pendant le travail (V3.1)
        self._travaux: list[Travail] = []  # scripts qui restent à écrire
        self._ecrits = 0
        self._serie_en_cours = ""  # mode de la série en cours d'écriture (message de fin)
        self._arret_demande = False
        self._cout_tache = Decimal(0)
        self._cout_commun = Decimal(0)  # accroches d'une série « Mêmes réglages », réparties entre ses scripts
        self._vitesse_affichee: float | None = None
        self.lecteur = Lecteur(self)
        self.ecoute = EcouteVoix(services, self.lecteur, self._afficher)

        self._minuterie = QTimer(self)
        self._minuterie.setSingleShot(True)
        self._minuterie.setInterval(DELAI_ENREGISTREMENT_MS)
        self._minuterie.timeout.connect(self._enregistrer)

        # --- Produit ---
        self.produit = BlocProduit()
        self.produit.lire_demande.connect(self.lire_la_page)
        self.produit.texte_colle.connect(self.analyser_texte)
        self.produit.adresse_modifiee.connect(self._adresse_modifiee)
        self.produit.prononciation_demandee.connect(self.ouvrir_prononciation)
        self.contenu.addWidget(self.produit)

        # --- Brief (avec la bibliothèque de briefs), puis les actions ---
        cadre, d = bloc()
        entete = QHBoxLayout()
        entete.setSpacing(Espacements.S)
        # « Brief », et ce qu'il faut y mettre au survol de l'icône « i » (V3.1).
        entete.addLayout(ligne_avec_aide(libelle("Brief", "titre-bloc", retour_a_la_ligne=False), BoutonInfo(AIDE_BRIEF)), 1)
        self.bouton_charger_brief = bouton("Charger un brief", variante="contour", nom_icone="folder-open", action=self.charger_brief)
        self.bouton_charger_brief.setToolTip("Reprendre un brief enregistré (d'un autre projet, par exemple)")
        entete.addWidget(self.bouton_charger_brief)
        self.bouton_enregistrer_brief = bouton("Enregistrer", variante="contour", nom_icone="save", action=self.enregistrer_brief)
        self.bouton_enregistrer_brief.setToolTip("Ranger ce brief (et la page produit lue) dans ta bibliothèque de briefs")
        entete.addWidget(self.bouton_enregistrer_brief)
        d.addLayout(entete)
        self.formulaire = FormulaireBrief(services)
        self.formulaire.modifie.connect(self._brief_modifie)
        self.formulaire.langue_projet_demandee.connect(self._changer_langue_projet)
        self.formulaire.exemples_demandes.connect(self.ouvrir_exemples)
        d.addWidget(self.formulaire)
        actions = QHBoxLayout()
        actions.setSpacing(Espacements.S)
        self.bouton_accroches = bouton("Proposer des accroches", nom_icone="message-square-quote", action=self.demander_accroches)
        self.bouton_accroches.setToolTip("Le modèle propose des accroches : coche ensuite celles à développer")
        actions.addWidget(self.bouton_accroches)
        self.bouton_ecrire = bouton("Écrire le script", variante="principal", nom_icone="pen-line", action=self.ecrire)
        self.bouton_ecrire.setToolTip("Écrit un script complet (un par accroche cochée), relu avant d'arriver")
        actions.addWidget(self.bouton_ecrire)
        self.bouton_variantes = bouton("Variantes…", nom_icone="git-compare-arrows", action=self.ouvrir_variantes)
        self.bouton_variantes.setToolTip("Plusieurs scripts en un seul lancement : mêmes réglages, réglages par variante, accroches seulement")
        actions.addWidget(self.bouton_variantes)
        self.bouton_arreter = bouton("Arrêter", nom_icone="square", action=self.arreter)
        self.bouton_arreter.setToolTip("Arrête après le script en cours (ceux déjà écrits sont gardés)")
        self.bouton_arreter.hide()
        actions.addWidget(self.bouton_arreter)
        actions.addStretch(1)
        d.addLayout(actions)
        estimations = QHBoxLayout()
        estimations.setSpacing(Espacements.XS)
        estimations.addWidget(libelle("Accroches ≈", "legende", retour_a_la_ligne=False))
        self.cout_accroches = MontantLabel(0, Typo.LEGENDE)
        self.cout_accroches.setProperty("role", "legende")
        estimations.addWidget(self.cout_accroches)
        estimations.addSpacing(Espacements.S)
        estimations.addWidget(libelle("·", "legende", retour_a_la_ligne=False))
        estimations.addSpacing(Espacements.S)
        self.libelle_cout_script = libelle("Script ≈", "legende", retour_a_la_ligne=False)
        estimations.addWidget(self.libelle_cout_script)
        self.cout_script = MontantLabel(0, Typo.LEGENDE)
        self.cout_script.setProperty("role", "legende")
        estimations.addWidget(self.cout_script)
        estimations.addStretch(1)
        d.addLayout(estimations)
        self.statut = libelle("", "secondaire")
        self.statut.hide()  # visible seulement quand il y a quelque chose à dire
        d.addWidget(self.statut)
        self.contenu.addWidget(cadre)

        # --- Accroches et scripts ---
        self.accroches = ListeAccroches()
        self.accroches.cochees_changees.connect(self._accroches_cochees)
        self.contenu.addWidget(self.accroches)
        self.barre_scripts = QWidget()
        barre = QHBoxLayout(self.barre_scripts)
        barre.setContentsMargins(0, 0, 0, 0)
        barre.setSpacing(Espacements.S)
        self.bouton_comparer = bouton("Comparer…", nom_icone="columns-3", action=self.comparer)
        self.bouton_comparer.setToolTip("2 ou 3 scripts côte à côte : accroche, répliques, durée, relecture")
        barre.addWidget(self.bouton_comparer)
        barre.addStretch(1)
        self.barre_scripts.hide()
        self.contenu.addWidget(self.barre_scripts)
        self.scripts = ListeScripts()
        self.scripts.envoyer.connect(self.envoi_demande.emit)
        self.scripts.retoucher.connect(self.retoucher)
        self.scripts.retenir.connect(self.retenir_script)
        self.scripts.noter.connect(self.noter_script)
        self.scripts.dupliquer.connect(self.dupliquer_script)
        self.scripts.garder.connect(self.garder_comme_exemple)
        self.scripts.accroches_en_variantes.connect(self.accroches_en_variantes)
        self.scripts.supprimer.connect(self.supprimer_script)
        self.scripts.modifie.connect(self._script_modifie)
        self.contenu.addWidget(self.scripts)

        services.projets.abonner(self._projet_change)
        services.prix.abonner(self._mettre_a_jour_estimations)
        services.vitesses.abonner(self._vitesse_changee)  # une prise générée affine la vitesse
        self._projet_change(services.projets.projet)

    # --- Projet ---------------------------------------------------------------------------------

    def _projet_change(self, projet: Projet | None) -> None:
        if self._minuterie.isActive():
            self._minuterie.stop()
            self._enregistrer()
        self.lecteur.arreter()
        self._projet = projet
        if projet is None:
            self._services.modeles.choisir(SCRIPT, None)
            return
        etat = projet.ecriture
        if not etat.scripts and etat.page is None:
            self._options_retenues(etat.brief)
        self._genre_d_apres_la_voix(projet)
        self.titre.setText(f"{TITRE} / {projet.nom}")
        self.produit.definir(etat.adresse, etat.page, etat.fiche)
        self.formulaire.definir(etat.brief)
        self.formulaire.definir_langue_projet(projet.langue)
        self.accroches.definir(etat.accroches)
        self._vitesse_affichee = None
        self._vitesse_changee()  # durées à jour, puis les cartes des scripts
        self._afficher_scripts()
        self._services.modeles.choisir(SCRIPT, etat.brief.modele)
        self._mettre_a_jour_estimations()
        self._libelle_ecrire()
        if not self._occupe:
            self._afficher("", "secondaire")

    def _options_retenues(self, brief: Brief) -> None:
        """Nouveau brief : les options d'écriture choisies la dernière fois (cases, modèle…)."""
        options = self._services.preferences.lire(CLE_OPTIONS, {})
        if isinstance(options, dict):
            valeurs = {**brief.en_dict(), **{k: v for k, v in options.items() if k in OPTIONS_RETENUES}}
            relu = Brief.depuis_dict(valeurs)
            for nom in OPTIONS_RETENUES:
                setattr(brief, nom, getattr(relu, nom))

    def _retenir_options(self, brief: Brief) -> None:
        self._services.preferences.ecrire(CLE_OPTIONS, {nom: getattr(brief, nom) for nom in OPTIONS_RETENUES})

    def _genre_d_apres_la_voix(self, projet: Projet) -> None:
        """« Personne qui parle » : genre pré-rempli d'après la voix du projet (il change les accords)."""
        voix = self._services.voix.voix(projet.voix.voix)
        genre = GENRES_DES_VOIX.get(voix.genre if voix else "", "")
        if genre:
            projet.ecriture.brief.pre_remplir({"genre": genre})

    def enregistrer_maintenant(self) -> None:
        self._minuterie.stop()
        self._enregistrer()

    def _enregistrer(self) -> None:
        if self._projet is not None:
            self._services.projets.enregistrer(self._projet)

    def _modifie(self) -> None:
        if self._projet is not None:
            self._minuterie.start()

    def _brief_modifie(self) -> None:
        if self._projet is None:
            return
        brief = self._projet.ecriture.brief
        self._services.modeles.choisir(SCRIPT, brief.modele)
        self._retenir_options(brief)
        self._modifie()
        self._mettre_a_jour_estimations()

    def _adresse_modifiee(self, adresse: str) -> None:
        if self._projet is not None:
            self._projet.ecriture.adresse = adresse.strip()
            self._modifie()

    def _changer_langue_projet(self, langue: str) -> None:
        self.enregistrer_maintenant()
        self._services.projets.changer_langue(langue)
        self._afficher("Langue du projet changée : elle sert à la bibliothèque de voix et à la transcription.", "secondaire")

    # --- Vitesse de parole (mesurée sur les prises de la voix du projet) -------------------------

    def _vitesse(self) -> Vitesse:
        voix = self._projet.voix.voix if self._projet is not None else VOIX_PAR_DEFAUT
        return self._services.vitesses.vitesse(voix or VOIX_PAR_DEFAUT)

    def _mots_par_seconde(self) -> float:
        return self._vitesse().mots_par_seconde

    def _vitesse_changee(self) -> None:
        """Vitesse de la voix du projet : nombre de mots visé, durées estimées et contrôles de durée."""
        if self._projet is None:
            return
        vitesse = self._vitesse()
        nom = self._services.voix.nom(self._projet.voix.voix or VOIX_PAR_DEFAUT)
        self.formulaire.definir_vitesse(vitesse.mots_par_seconde, vitesse.texte(nom))
        if self._vitesse_affichee == vitesse.mots_par_seconde:
            return
        self._vitesse_affichee = vitesse.mots_par_seconde
        changes = False
        for script in self._projet.ecriture.scripts:
            nouveau = controle_duree(script, vitesse.mots_par_seconde)
            for rang, point in enumerate(script.relecture):
                if point.critere == "duree" and point.par == "app" and point != nouveau:
                    script.relecture[rang] = nouveau
                    changes = True
        self.scripts.definir_vitesse(vitesse.mots_par_seconde)
        self._mettre_a_jour_estimations()
        if changes:
            self._modifie()

    def showEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        # La voix du projet a pu changer dans le module Voix : la vitesse aussi.
        super().showEvent(evenement)
        self._vitesse_changee()

    # --- Estimations ----------------------------------------------------------------------------

    def _exemples(self, brief: Brief) -> list[ExempleScript]:
        return choisir_exemples(self._services.exemples.exemples(), brief)

    def _texte_page(self) -> str:
        page = self._projet.ecriture.page if self._projet else None
        return page.texte if page is not None else ""

    def _mettre_a_jour_estimations(self) -> None:
        if self._projet is None:
            return
        etat = self._projet.ecriture
        brief = etat.brief
        prix = self._services.prix
        exemples = self._exemples(brief)
        page = self._texte_page()
        accroches = estimer_accroches(brief, page, exemples)
        self._montant(self.cout_accroches, prix.cout_eur(brief.modele, accroches.tokens_entree, accroches.tokens_sortie))
        script = estimer_script(brief, page, exemples, "", self._mots_par_seconde())
        nombre = max(1, len(etat.accroches_cochees()))
        cout = prix.cout_eur(brief.modele, script.tokens_entree, script.tokens_sortie)
        self._montant(self.cout_script, None if cout is None else cout * nombre)
        self.libelle_cout_script.setText(f"{nombre} scripts ≈" if nombre > 1 else "Script ≈")
        lecture = estimer_lecture(page or "x" * TEXTE_PAGE_TYPIQUE, brief.modele, brief.langue)
        self.produit.definir_estimation(prix.cout_eur(brief.modele, lecture.tokens_entree, lecture.tokens_sortie))

    @staticmethod
    def _montant(etiquette: MontantLabel, montant: Decimal | None) -> None:
        if montant is None:
            etiquette.setText("prix inconnu")
        else:
            etiquette.definir_montant(montant)

    # --- Tâches de fond -------------------------------------------------------------------------

    def _occuper(self, occupe: bool, message: str = "", bouton: Bouton | None = None) -> None:
        """Pendant un travail : le cercle tourne dans `bouton` (celui qui l'a lancé), qui garde son
        aspect ; les autres actions sont grisées. Le message dit où en est le travail."""
        self._occupe = occupe
        if occupe:
            self._bouton_occupe.occuper(bouton)
        else:
            self._bouton_occupe.liberer()
        actif = self._bouton_occupe.est
        self.produit.occupe(occupe, self._bouton_occupe.bouton)
        for element in (
            self.bouton_accroches,
            self.bouton_ecrire,
            self.bouton_variantes,
            self.bouton_charger_brief,
            self.bouton_comparer,
        ):
            element.setEnabled(not occupe or actif(element))
        for carte in self.scripts.cartes():
            carte.bouton_retoucher.setEnabled(not occupe or actif(carte.bouton_retoucher))
        if message or not occupe:
            self._afficher(message, "secondaire")

    def _afficher(self, message: str, role: str) -> None:
        self.statut.setText(message)
        self.statut.setVisible(bool(message))
        self.statut.setProperty("role", role)
        self.statut.style().unpolish(self.statut)
        self.statut.style().polish(self.statut)

    def _adaptateur(self):
        """Adaptateur de la clé par défaut, ou None (message affiché) si aucune clé n'est enregistrée."""
        try:
            return adaptateur_par_defaut(self._services)
        except Exception as erreur:  # noqa: BLE001 — message clair affiché
            self._afficher(message_erreur(erreur), "erreur")
            return None

    def _nouvelles(self, projet: Projet):
        """Nouvelles d'une tâche : étape en cours (texte), appel terminé (coût), page lue par l'app."""

        def recevoir(nouvelle) -> None:
            if isinstance(nouvelle, Appel):
                appel = self._services.couts.enregistrer(
                    FOURNISSEUR, nouvelle.modele, nouvelle.operation, nouvelle.tokens_entree, nouvelle.tokens_sortie,
                    projet=projet.nom,
                )
                if appel.cout_eur is not None:
                    self._cout_tache += appel.cout_eur
            elif isinstance(nouvelle, PageLue):
                if self._projet is projet:
                    self._page_lue(nouvelle, None, enregistrer=False)
            elif isinstance(nouvelle, str) and self._projet is projet:
                self._afficher(nouvelle, "secondaire")

        return recevoir

    def _modeles_lecture(self, choisi: str) -> list[str]:
        """Pour une lecture par Google : le modèle du brief d'abord, puis les autres modèles chargés qui
        savent lire une page web (si Google refuse l'outil pour le premier)."""
        autres = [
            m for m in self._services.modeles.charges()
            if m != choisi and Capacite.TEXTE_PAGES_WEB in deviner_capacites(m)
        ]
        return [choisi, *autres]

    # --- Page produit ---------------------------------------------------------------------------

    def lire_la_page(self, adresse: str) -> None:
        if self._projet is None or self._occupe:
            return
        projet = self._projet
        projet.ecriture.adresse = adresse
        brief = copie(projet.ecriture.brief)
        try:
            adaptateur = adaptateur_par_defaut(self._services)
        except Exception:  # noqa: BLE001 — sans clé, l'app lit quand même la page (gratuit)
            adaptateur = None
        modeles = self._modeles_lecture(brief.modele)

        def travail(signaler):
            try:
                page = lire_page(adresse, brief.langue, brief.devise())
            except ErreurLecture as erreur:
                if not erreur.google_peut_essayer or adaptateur is None:
                    raise
                signaler(f"L'app n'a pas pu lire cette page ({erreur.message.rstrip('.')}) : Google essaie.")
                return lire_par_google(adaptateur, modeles, normaliser_adresse(adresse), brief.langue, signaler)
            signaler(page)
            if adaptateur is None:
                return page, None
            return page, analyser_page(adaptateur, brief.modele, page, brief.langue, signaler)

        def fin(resultat) -> None:
            self._occuper(False)
            if self._projet is not projet:
                return
            page, fiche = resultat
            self._page_lue(page, fiche)
            if fiche is None:
                self._afficher(
                    "Page lue. Pour que le modèle l'analyse et pré-remplisse le brief, ajoute ta clé Google "
                    "dans Réglages → Connexions API.",
                    "avertissement",
                )

        def echec(erreur: Exception) -> None:
            self._occuper(False)
            if isinstance(erreur, ErreurLecture):
                suite = (
                    " Ajoute ta clé Google pour que Google essaie de la lire, ou colle le texte de la page (bouton "
                    "« Coller le texte du produit »)."
                    if adaptateur is None and erreur.google_peut_essayer
                    else " Colle le texte de la page : bouton « Coller le texte du produit »."
                )
                self.produit.afficher_etat(erreur.message + suite, erreur=True)
                self._afficher("", "secondaire")
            else:
                self._afficher(f"Lecture impossible : {message_erreur(erreur)}", "erreur")

        self._cout_tache = Decimal(0)
        self._occuper(True, "Lecture de la page…", self.produit.bouton_lire)
        taches.lancer_avec_progres(travail, fin, echec, self._nouvelles(projet))

    def analyser_texte(self, texte: str) -> None:
        """« Analyser ce texte » : le texte de la page collé à la main."""
        if self._projet is None or self._occupe:
            return
        adaptateur = self._adaptateur()
        if adaptateur is None:
            return
        projet = self._projet
        brief = copie(projet.ecriture.brief)
        page = page_collee(texte, projet.ecriture.adresse)

        def fin(fiche: FicheProduit) -> None:
            self._occuper(False)
            if self._projet is projet:
                self._page_lue(page, fiche)

        def echec(erreur: Exception) -> None:
            self._occuper(False)
            self._afficher(f"Analyse impossible : {message_erreur(erreur)}", "erreur")

        self._cout_tache = Decimal(0)
        self._occuper(True, "Analyse du texte collé…", self.produit.bouton_analyser)
        taches.lancer_avec_progres(
            lambda signaler: analyser_page(adaptateur, brief.modele, page, brief.langue, signaler),
            fin,
            echec,
            self._nouvelles(projet),
        )

    def _page_lue(self, page: PageLue, fiche: FicheProduit | None, enregistrer: bool = True) -> None:
        """Page lue (et comprise) : la fiche pré-remplit les champs vides du brief."""
        etat = self._projet.ecriture
        etat.page = page
        etat.fiche = fiche  # None tant que le modèle n'a pas analysé la page
        if fiche is not None:
            valeurs = fiche.valeurs_du_brief()
        else:
            valeurs = {"produit": page.nom, "prix": page.prix, "promo": f"au lieu de {page.prix_barre}" if page.prix_barre else ""}
        etat.brief.pre_remplir({nom: valeur for nom, valeur in valeurs.items() if valeur})
        self.formulaire.rafraichir_champs()
        self.produit.definir(etat.adresse or page.adresse, page, fiche)
        if fiche is not None:
            self.produit.afficher_etat(etat_de_la_page(page) + " La fiche a pré-rempli les champs vides du brief.")
        if enregistrer:
            self._enregistrer()
            self._mettre_a_jour_estimations()

    def ouvrir_prononciation(self, noms: list[str]) -> None:
        dialogue = DialoguePrononciation(self._services, self.tester_prononciation, self.window(), mots_proposes=noms)
        dialogue.exec()

    def tester_prononciation(self, texte: str, bouton=None) -> None:
        """▶ du dictionnaire : la voix du projet dit la prononciation (gardée en cache) ; le cercle
        tourne dans ce ▶ pendant la préparation."""
        if self._projet is None:
            return
        modele, voix = self._projet.voix.modele, self._projet.voix.voix
        self.ecoute.dire(
            texte, voix, modele, "essai de prononciation", fichier_prononciation(voix, modele, texte),
            f"Prononciation de « {texte} »…", bouton,
        )

    # --- Bibliothèque de briefs et exemples ------------------------------------------------------

    def charger_brief(self) -> None:
        """« Charger un brief » : un brief enregistré remplace celui du projet (les options d'écriture,
        elles, restent) ; la page produit lue revient aussi si la case est cochée."""
        if self._projet is None or self._occupe:
            return
        dialogue = DialogueBibliothequeBriefs(self._services, self.window())
        if not dialogue.exec() or dialogue.brief_choisi is None:
            return
        enregistre = dialogue.brief_choisi
        etat = self._projet.ecriture
        brief = copie(enregistre.brief)
        for nom in OPTIONS_RETENUES:
            setattr(brief, nom, getattr(etat.brief, nom))
        etat.brief = brief
        if dialogue.reprendre_page and enregistre.page is not None:
            etat.adresse = enregistre.adresse or enregistre.page.adresse
            etat.page = PageLue.depuis_dict(enregistre.page.en_dict())
            etat.fiche = FicheProduit.depuis_dict(enregistre.fiche.en_dict()) if enregistre.fiche else None
        self._genre_d_apres_la_voix(self._projet)
        self.produit.definir(etat.adresse, etat.page, etat.fiche)
        self.formulaire.definir(etat.brief)
        self.formulaire.definir_langue_projet(self._projet.langue)
        self._services.modeles.choisir(SCRIPT, etat.brief.modele)
        self._enregistrer()
        self._mettre_a_jour_estimations()
        self._afficher(f"Brief « {enregistre.nom} » chargé.", "succes")

    def enregistrer_brief(self) -> None:
        """« Enregistrer » : le brief (et la page produit lue) rejoint la bibliothèque de briefs."""
        if self._projet is None:
            return
        etat = self._projet.ecriture
        nom, ok = QInputDialog.getText(
            self, "Enregistrer le brief", "Nom du brief :", text=nom_propose(etat.brief, self._projet.nom)
        )
        nom = " ".join(nom.split())
        if not ok or not nom:
            return
        if self._services.briefs.existe(nom):
            reponse = QMessageBox.question(
                self,
                "Enregistrer le brief",
                f"Un brief s'appelle déjà « {nom} » : le remplacer ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reponse != QMessageBox.StandardButton.Yes:
                return
        enregistre = self._services.briefs.enregistrer(nom, etat.brief, etat.adresse, etat.page, etat.fiche)
        self._afficher(f"Brief enregistré dans ta bibliothèque : « {enregistre.nom} ».", "succes")

    def ouvrir_exemples(self) -> None:
        """« Mes meilleurs scripts… » ; ensuite, la marque « Exemple » des scripts suit la bibliothèque."""
        brief = self._projet.ecriture.brief if self._projet is not None else None
        DialogueMeilleursScripts(self._services, brief, self.window()).exec()
        if self._projet is None:
            return
        changes = False
        for script in self._projet.ecriture.scripts:
            garde = self._services.exemples.contient(f"script-{script.identifiant}")
            if garde != script.garde_comme_exemple:
                script.garde_comme_exemple, changes = garde, True
        if changes:
            for carte in self.scripts.cartes():
                carte.rafraichir()
            self._enregistrer()
        self._mettre_a_jour_estimations()  # les exemples font partie des demandes

    # --- Accroches ------------------------------------------------------------------------------

    def demander_accroches(self) -> None:
        """« Proposer des accroches » : le modèle en propose, tu coches celles à développer."""
        if self._projet is None or self._occupe:
            return
        adaptateur = self._adaptateur()
        if adaptateur is None:
            return
        projet = self._projet
        brief = copie(projet.ecriture.brief)
        page = self._texte_page()
        exemples = self._exemples(brief)

        def fin(accroches) -> None:
            self._occuper(False)
            if self._projet is not projet:
                return
            projet.ecriture.accroches = accroches
            self.accroches.definir(accroches)
            self._libelle_ecrire()
            self._afficher(f"{len(accroches)} accroches proposées : coche celles à développer.", "succes")
            self._enregistrer()
            self._mettre_a_jour_estimations()

        def echec(erreur: Exception) -> None:
            self._occuper(False)
            self._afficher(f"Accroches impossibles : {message_erreur(erreur)}", "erreur")

        self._cout_tache = Decimal(0)
        self._occuper(True, "Le modèle cherche des accroches…", self.bouton_accroches)
        taches.lancer_avec_progres(
            lambda signaler: proposer_accroches(adaptateur, brief, page, exemples, signaler),
            fin,
            echec,
            self._nouvelles(projet),
        )

    def _accroches_cochees(self) -> None:
        self._libelle_ecrire()
        self._mettre_a_jour_estimations()
        self._modifie()

    def _libelle_ecrire(self) -> None:
        nombre = len(self._projet.ecriture.accroches_cochees()) if self._projet else 0
        self.bouton_ecrire.setText(f"Écrire les {nombre} scripts" if nombre > 1 else "Écrire le script")

    # --- Écriture -------------------------------------------------------------------------------

    def ecrire(self) -> None:
        """Un script par accroche cochée (sans accroche cochée, le modèle choisit lui-même)."""
        if self._projet is None or self._occupe:
            return
        brief = self._projet.ecriture.brief
        cochees = self._projet.ecriture.accroches_cochees()
        self._lancer([Travail(copie(brief), a.texte) for a in cochees] or [Travail(copie(brief))])

    def ouvrir_variantes(self) -> None:
        """« Variantes… » : plusieurs scripts en un seul lancement (trois modes)."""
        if self._projet is None or self._occupe:
            return
        brief = self._projet.ecriture.brief
        dialogue = DialogueVariantesScript(
            self._services, brief, self._texte_page(), self._exemples(brief), self._mots_par_seconde(), self.window()
        )
        if dialogue.exec():
            self.ecrire_variantes(dialogue.mode(), dialogue.nombre(), dialogue.variantes())

    def ecrire_variantes(self, mode: str, nombre: int, variantes: list[ReglagesScript] | None = None) -> None:
        """Une série de scripts : chacun reçoit l'identifiant de la série et sa lettre (A, B…)."""
        if self._projet is None or self._occupe:
            return
        brief = self._projet.ecriture.brief
        serie = nouvelle_serie()
        nombre = max(2, min(nombre, len(LETTRES)))
        if mode == PAR_VARIANTE:
            travaux = [
                Travail(v.brief(brief), v.accroche, serie, LETTRES[rang], PAR_VARIANTE)
                for rang, v in enumerate((variantes or [])[: len(LETTRES)])
            ]
            self._lancer(travaux, PAR_VARIANTE)
        elif mode == ACCROCHES:
            self._lancer([Travail(copie(brief), "", serie, LETTRES[0], ACCROCHES, nombre)], ACCROCHES)
        else:
            self._accroches_de_la_serie(copie(brief), serie, nombre)

    def _accroches_de_la_serie(self, brief: Brief, serie: str, nombre: int) -> None:
        """« Mêmes réglages » : d'abord une accroche par variante (angles différents), puis un script
        complet par accroche. Le coût des accroches est réparti entre les scripts de la série."""
        adaptateur = self._adaptateur()
        if adaptateur is None:
            return
        projet = self._projet
        page = self._texte_page()
        exemples = self._exemples(brief)

        def fin(accroches) -> None:
            travaux = [Travail(copie(brief), a.texte, serie, LETTRES[rang], MEMES) for rang, a in enumerate(accroches)]
            if self._projet is not projet or not travaux:
                self._occuper(False)
                return
            # Le cercle continue de tourner dans « Écrire le script » : l'écriture enchaîne.
            self._lancer(travaux, MEMES, cout_commun=self._cout_tache)

        def echec(erreur: Exception) -> None:
            self._occuper(False)
            self._afficher(f"Variantes impossibles : {message_erreur(erreur)}", "erreur")

        self._cout_tache = Decimal(0)
        self._occuper(True, f"Le modèle cherche {nombre} accroches différentes…", self.bouton_ecrire)
        taches.lancer_avec_progres(
            lambda signaler: proposer_accroches(adaptateur, brief, page, exemples, signaler, nombre, une_par_angle=True),
            fin,
            echec,
            self._nouvelles(projet),
        )

    def _lancer(self, travaux: list[Travail], mode: str = "", cout_commun: Decimal = Decimal(0)) -> None:
        if not travaux:
            return
        self._travaux = list(travaux)
        self._ecrits = 0
        self._serie_en_cours = mode
        self._cout_commun = cout_commun / len(travaux) if travaux else Decimal(0)
        self._arret_demande = False
        self._ecrire_suivant()

    def arreter(self) -> None:
        self._arret_demande = True
        # Le cercle tourne aussi dans « Arrêter », le temps que le script en cours se termine.
        montrer_occupe(self.bouton_arreter, True)
        self._afficher("Arrêt demandé : le script en cours se termine.", "secondaire")

    def _ecrire_suivant(self) -> None:
        if self._projet is None or not self._travaux or self._arret_demande:
            self._fin_ecriture()
            return
        adaptateur = self._adaptateur()
        if adaptateur is None:
            self._fin_ecriture(garder_message=True)
            return
        projet = self._projet
        page = self._texte_page()
        mots_par_seconde = self._mots_par_seconde()
        travail = self._travaux.pop(0)
        exemples = self._exemples(travail.brief)
        total = self._ecrits + len(self._travaux) + 1

        def ecrire(signaler) -> list[ScriptEcrit]:
            script = ecrire_script(adaptateur, travail.brief, page, exemples, travail.accroche, signaler, mots_par_seconde)
            if travail.mode != ACCROCHES:
                return [script]
            accroches = accroches_pour_corps(adaptateur, travail.brief, page, script, travail.nombre - 1, signaler)
            return [script, *variantes_d_accroches(script, accroches, travail.brief, mots_par_seconde)]

        def fin(scripts: list[ScriptEcrit]) -> None:
            # Le coût de la tâche (et la part des accroches communes) est réparti entre ses scripts.
            part = self._cout_tache / len(scripts) + self._cout_commun
            for rang, script in enumerate(scripts):
                script.cout_eur = format(part.quantize(Decimal("0.0000001")).normalize(), "f")
                if travail.serie:
                    script.serie, script.mode = travail.serie, travail.mode
                    script.lettre = LETTRES[rang] if travail.mode == ACCROCHES else travail.lettre
            self._ecrits += len(scripts)
            if self._projet is projet:
                for script in scripts:
                    projet.ecriture.ajouter(script)
                self._afficher_scripts()
                self._enregistrer()
            # Le script suivant, ou la fin (qui arrête le cercle) : sans pause entre deux scripts.
            self._ecrire_suivant()

        def echec(erreur: Exception) -> None:
            self._travaux = []
            self._fin_ecriture()
            self._afficher(f"Écriture impossible : {message_erreur(erreur)}", "erreur")

        self._cout_tache = Decimal(0)
        if travail.mode == ACCROCHES:
            message = f"Écriture du script, puis de {travail.nombre - 1} autres accroches…"
        elif total > 1:
            message = f"Script {self._ecrits + 1} sur {total}…"
        else:
            message = "Écriture du script…"
        self._occuper(True, message, self.bouton_ecrire)
        # « Arrêter » prend la place de « Variantes… » (désactivé pendant l'écriture) : la ligne de
        # boutons tient ainsi dans une fenêtre de 960 px.
        self.bouton_variantes.setVisible(total <= 1)
        self.bouton_arreter.setVisible(total > 1)
        taches.lancer_avec_progres(ecrire, fin, echec, self._nouvelles(projet))

    def _fin_ecriture(self, garder_message: bool = False) -> None:
        montrer_occupe(self.bouton_arreter, False)
        self.bouton_arreter.hide()
        self.bouton_variantes.show()
        self._occuper(False)
        if garder_message or not self._ecrits:
            return
        if self._serie_en_cours == ACCROCHES:
            texte = (
                f"{self._ecrits} variantes écrites (même corps, accroches différentes) : menu ⋯ d'un script, « Envoyer "
                "les accroches en variantes » pour les tester dans le module Voix."
            )
        elif self._serie_en_cours:
            texte = f"{self._ecrits} variantes écrites et relues : « Comparer… » les met côte à côte."
        elif self._ecrits > 1:
            texte = f"{self._ecrits} scripts écrits et relus : relis-les, puis « Envoyer dans Voix »."
        else:
            texte = "Script écrit et relu : relis-le, puis « Envoyer dans Voix »."
        self._afficher(texte, "succes")

    # --- Scripts ----------------------------------------------------------------------------------

    def _afficher_scripts(self) -> None:
        scripts = self._projet.ecriture.scripts if self._projet is not None else []
        self.scripts.definir(scripts, self._mots_par_seconde())
        self.barre_scripts.setVisible(len(scripts) >= 2)
        if self._occupe:
            for carte in self.scripts.cartes():
                carte.bouton_retoucher.setEnabled(False)

    def _script_modifie(self, script: ScriptEcrit) -> None:
        """Texte modifié à la main : l'app revérifie ce qui se compte (durée, mots interdits…)."""
        if self._projet is None:
            return
        gardes = [p for p in script.relecture if p.par == "modele" or p.critere == "balises"]
        script.relecture = controler(script, self._projet.ecriture.brief, None, self._mots_par_seconde()) + gardes
        carte = self.scripts.carte(script)
        if carte is not None:
            carte.rafraichir()
        self._modifie()

    def _rafraichir_carte(self, script: ScriptEcrit) -> None:
        carte = self.scripts.carte(script)
        if carte is not None:
            carte.rafraichir()
        self._enregistrer()

    def script_envoye(self, script: ScriptEcrit) -> None:
        """Appelé par la fenêtre principale quand le module Voix a reçu les répliques du script."""
        script.envoye_le = datetime.now().astimezone().isoformat(timespec="seconds")
        self._rafraichir_carte(script)

    def retenir_script(self, script: ScriptEcrit) -> None:
        """« Retenir » : marque (ou démarque) un script gardé pour tes pubs."""
        script.retenu = not script.retenu
        self._rafraichir_carte(script)

    def noter_script(self, script: ScriptEcrit, note: int) -> None:
        script.note = note
        self._rafraichir_carte(script)

    def dupliquer_script(self, script: ScriptEcrit) -> None:
        """« Dupliquer » : une copie à modifier à la main, l'original reste tel quel."""
        if self._projet is None:
            return
        nouveau = self._projet.ecriture.ajouter(dupliquer(script))
        self._afficher_scripts()
        self._enregistrer()
        self._afficher(f"{nouveau.nom()} : copie du {script.nom()[:1].lower()}{script.nom()[1:]}, à modifier à la main.", "succes")

    def retoucher(self, script: ScriptEcrit) -> None:
        """« Retoucher… » : une consigne donne un nouveau script, relu comme les autres ; l'ancien reste."""
        if self._projet is None or self._occupe:
            return
        dialogue = DialogueRetouche(
            self._services, script, self._projet.ecriture.brief, self._texte_page(), self._mots_par_seconde(), self.window()
        )
        if not dialogue.exec():
            return
        adaptateur = self._adaptateur()
        if adaptateur is None:
            return
        projet = self._projet
        brief = dialogue.brief_de_retouche()
        consigne = dialogue.texte_consigne()
        page = self._texte_page()
        mots_par_seconde = self._mots_par_seconde()

        def fin(nouveau: ScriptEcrit) -> None:
            nouveau.cout_eur = format(self._cout_tache, "f")
            self._occuper(False)
            if self._projet is not projet:
                return
            projet.ecriture.ajouter(nouveau)
            self._afficher_scripts()
            self._enregistrer()
            self._afficher(f"{nouveau.nom()} : retouche relue, en haut de la liste. L'ancien script reste.", "succes")

        def echec(erreur: Exception) -> None:
            self._occuper(False)
            self._afficher(f"Retouche impossible : {message_erreur(erreur)}", "erreur")

        self._cout_tache = Decimal(0)
        carte = self.scripts.carte(script)
        self._occuper(True, "Retouche du script…", carte.bouton_retoucher if carte is not None else None)
        taches.lancer_avec_progres(
            lambda signaler: retoucher_script(adaptateur, brief, page, script, consigne, signaler, mots_par_seconde),
            fin,
            echec,
            self._nouvelles(projet),
        )

    def comparer(self) -> None:
        """« Comparer… » : 2 ou 3 scripts côte à côte ; « Envoyer dans Voix » depuis une colonne."""
        if self._projet is None or len(self._projet.ecriture.scripts) < 2:
            return
        dialogue = DialogueComparerScripts(self._projet.ecriture.scripts, None, self._mots_par_seconde(), self.window())
        if dialogue.exec() and dialogue.script_a_envoyer is not None:
            self.envoi_demande.emit(dialogue.script_a_envoyer)

    def accroches_en_variantes(self, script: ScriptEcrit) -> None:
        """Série « Accroches seulement » : ses accroches partent dans le module Voix, une variante de
        voix par accroche (la fenêtre principale s'en charge)."""
        if self._projet is None:
            return
        serie = self._projet.ecriture.serie(script.serie)
        if len(serie) >= 2:
            self.enregistrer_maintenant()
            self.variantes_voix_demandees.emit(serie)

    def garder_comme_exemple(self, script: ScriptEcrit) -> None:
        if self._projet is None:
            return
        brief = self._projet.ecriture.brief
        resume = " ; ".join(v for v in (brief.produit, brief.prix, brief.promo, brief.offre.replace("\n", ", ")) if v)
        exemple = ExempleScript(
            identifiant=f"script-{script.identifiant}",
            titre=brief.produit or self._projet.nom,
            langue=script.langue,
            reseau=script.reseau,
            angle=script.angle,
            tutoiement=script.tutoiement,
            duree_s=script.duree_visee_s,
            brief=resume,
            repliques=repliques_pour_modele(script.repliques),
        )
        self._services.exemples.ajouter(exemple)
        script.garde_comme_exemple = True
        self._rafraichir_carte(script)
        self._mettre_a_jour_estimations()
        self._afficher("Script gardé comme exemple : le modèle s'en inspirera pour les prochains scripts.", "succes")

    def supprimer_script(self, script: ScriptEcrit, confirmer: bool = True) -> None:
        if self._projet is None or script not in self._projet.ecriture.scripts:
            return
        if confirmer:
            reponse = QMessageBox.question(
                self,
                "Supprimer le script",
                f"Supprimer le {script.nom()[:1].lower()}{script.nom()[1:]} ? (S'il a été gardé comme exemple, "
                "l'exemple reste.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reponse != QMessageBox.StandardButton.Yes:
                return
        self._projet.ecriture.scripts.remove(script)
        self._afficher_scripts()
        self._enregistrer()

    def quitter(self) -> None:
        """Quand on passe à un autre module : la lecture d'un essai de prononciation s'arrête."""
        self.lecteur.arreter()
        self.enregistrer_maintenant()
