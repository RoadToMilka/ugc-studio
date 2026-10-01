"""Atelier du module Script (V2, §3.1 et §10) : page produit, brief, accroches, scripts écrits et
relus, envoi dans le module Voix.

Les appels au modèle partent en tâche de fond, un à la fois. Chaque appel terminé est noté tout de
suite dans le suivi des coûts (même si l'étape suivante échoue), et son coût est estimé avant de
lancer. Tout est enregistré automatiquement dans le projet (format 6).
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QMessageBox

from ....ecriture.brief import Brief
from ....ecriture.controles import controler
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
    analyser_page,
    ecrire_script,
    estimer_accroches,
    estimer_lecture,
    estimer_script,
    lire_par_google,
    proposer_accroches,
)
from ....ecriture.scripts import ScriptEcrit, repliques_pour_modele
from ....fournisseurs.capacites import Capacite, deviner_capacites
from ....modeles_charges import SCRIPT
from ....projets import Projet
from ....services import Services
from ... import taches
from ...composants.elements import bloc, bouton, libelle
from ...composants.lecteur import Lecteur
from ...composants.montant_label import MontantLabel
from ...connexion_ia import FOURNISSEUR, adaptateur_par_defaut, message_erreur
from ...dialogues.prononciation import DialoguePrononciation
from ...extraits import EcouteVoix, fichier_prononciation
from ...theme import Espacements, Typo
from ..base import Page
from .formulaire import FormulaireBrief
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


class AtelierScript(Page):
    envoi_demande = Signal(object)  # ScriptEcrit à envoyer dans le module Voix

    def __init__(self, services: Services):
        super().__init__(TITRE, SOUS_TITRE, conseils="script")
        self._services = services
        self._projet: Projet | None = None
        self._occupe = False
        self._a_ecrire: list[str] = []  # accroches des scripts qui restent à écrire (vide : le modèle choisit)
        self._ecrits = 0
        self._arret_demande = False
        self._cout_tache = Decimal(0)
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

        # --- Brief, puis les actions ---
        cadre, d = bloc("Brief")
        self.formulaire = FormulaireBrief(services)
        self.formulaire.modifie.connect(self._brief_modifie)
        self.formulaire.langue_projet_demandee.connect(self._changer_langue_projet)
        d.addWidget(self.formulaire)
        actions = QHBoxLayout()
        actions.setSpacing(Espacements.S)
        self.bouton_accroches = bouton("Proposer des accroches", nom_icone="message-square-quote", action=self.proposer_accroches)
        self.bouton_accroches.setToolTip("Le modèle propose des accroches : coche ensuite celles à développer")
        actions.addWidget(self.bouton_accroches)
        self.bouton_ecrire = bouton("Écrire le script", variante="principal", nom_icone="pen-line", action=self.ecrire)
        self.bouton_ecrire.setToolTip("Écrit un script complet (un par accroche cochée), relu avant d'arriver")
        actions.addWidget(self.bouton_ecrire)
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
        self.libelle_cout_script = libelle("  ·  Script ≈", "legende", retour_a_la_ligne=False)
        estimations.addWidget(self.libelle_cout_script)
        self.cout_script = MontantLabel(0, Typo.LEGENDE)
        self.cout_script.setProperty("role", "legende")
        estimations.addWidget(self.cout_script)
        estimations.addStretch(1)
        d.addLayout(estimations)
        self.statut = libelle("", "secondaire")
        d.addWidget(self.statut)
        self.contenu.addWidget(cadre)

        # --- Accroches et scripts ---
        self.accroches = ListeAccroches()
        self.accroches.cochees_changees.connect(self._accroches_cochees)
        self.contenu.addWidget(self.accroches)
        self.scripts = ListeScripts()
        self.scripts.envoyer.connect(self.envoi_demande.emit)
        self.scripts.garder.connect(self.garder_comme_exemple)
        self.scripts.supprimer.connect(self.supprimer_script)
        self.scripts.modifie.connect(self._script_modifie)
        self.contenu.addWidget(self.scripts)

        services.projets.abonner(self._projet_change)
        services.prix.abonner(self._mettre_a_jour_estimations)
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
        self.scripts.definir(etat.scripts)
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
        script = estimer_script(brief, page, exemples)
        nombre = max(1, len(etat.accroches_cochees()))
        cout = prix.cout_eur(brief.modele, script.tokens_entree, script.tokens_sortie)
        self._montant(self.cout_script, None if cout is None else cout * nombre)
        self.libelle_cout_script.setText(f"  ·  {nombre} scripts ≈" if nombre > 1 else "  ·  Script ≈")
        lecture = estimer_lecture(page or "x" * TEXTE_PAGE_TYPIQUE, brief.modele, brief.langue)
        self.produit.definir_estimation(prix.cout_eur(brief.modele, lecture.tokens_entree, lecture.tokens_sortie))

    @staticmethod
    def _montant(etiquette: MontantLabel, montant: Decimal | None) -> None:
        if montant is None:
            etiquette.setText("prix inconnu")
        else:
            etiquette.definir_montant(montant)

    # --- Tâches de fond -------------------------------------------------------------------------

    def _occuper(self, occupe: bool, message: str = "") -> None:
        self._occupe = occupe
        self.produit.occupe(occupe)
        self.bouton_accroches.setEnabled(not occupe)
        self.bouton_ecrire.setEnabled(not occupe)
        if message or not occupe:
            self._afficher(message, "secondaire")

    def _afficher(self, message: str, role: str) -> None:
        self.statut.setText(message)
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
        self._occuper(True, "Lecture de la page…")
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
        self._occuper(True, "Analyse du texte collé…")
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

    def tester_prononciation(self, texte: str) -> None:
        """▶ du dictionnaire : la voix du projet dit la prononciation (gardée en cache)."""
        if self._projet is None:
            return
        modele, voix = self._projet.voix.modele, self._projet.voix.voix
        self.ecoute.dire(
            texte, voix, modele, "essai de prononciation", fichier_prononciation(voix, modele, texte),
            f"Prononciation de « {texte} »…",
        )

    # --- Accroches ------------------------------------------------------------------------------

    def proposer_accroches(self) -> None:
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
        self._occuper(True, "Le modèle cherche des accroches…")
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
        self._a_ecrire = [a.texte for a in self._projet.ecriture.accroches_cochees()] or [""]
        self._ecrits = 0
        self._arret_demande = False
        self._ecrire_suivant()

    def arreter(self) -> None:
        self._arret_demande = True
        self.bouton_arreter.setEnabled(False)
        self._afficher("Arrêt demandé : le script en cours se termine.", "secondaire")

    def _ecrire_suivant(self) -> None:
        if self._projet is None or not self._a_ecrire or self._arret_demande:
            self._fin_ecriture()
            return
        adaptateur = self._adaptateur()
        if adaptateur is None:
            self._fin_ecriture(garder_message=True)
            return
        projet = self._projet
        brief = copie(projet.ecriture.brief)
        page = self._texte_page()
        exemples = self._exemples(brief)
        accroche = self._a_ecrire.pop(0)
        total = self._ecrits + len(self._a_ecrire) + 1

        def fin(script: ScriptEcrit) -> None:
            script.cout_eur = format(self._cout_tache, "f")
            self._ecrits += 1
            if self._projet is projet:
                projet.ecriture.scripts.append(script)
                self.scripts.definir(projet.ecriture.scripts)
                self._enregistrer()
            self._occuper(False)
            self._ecrire_suivant()

        def echec(erreur: Exception) -> None:
            self._a_ecrire = []
            self._fin_ecriture()
            self._afficher(f"Écriture impossible : {message_erreur(erreur)}", "erreur")

        self._cout_tache = Decimal(0)
        message = f"Script {self._ecrits + 1} sur {total}…" if total > 1 else "Écriture du script…"
        self._occuper(True, message)
        self.bouton_arreter.setVisible(total > 1)
        self.bouton_arreter.setEnabled(True)
        taches.lancer_avec_progres(
            lambda signaler: ecrire_script(adaptateur, brief, page, exemples, accroche, signaler),
            fin,
            echec,
            self._nouvelles(projet),
        )

    def _fin_ecriture(self, garder_message: bool = False) -> None:
        self.bouton_arreter.hide()
        self._occuper(False)
        if not garder_message and self._ecrits:
            if self._ecrits > 1:
                texte = f"{self._ecrits} scripts écrits et relus : relis-les, puis « Envoyer dans Voix »."
            else:
                texte = "Script écrit et relu : relis-le, puis « Envoyer dans Voix »."
            self._afficher(texte, "succes")

    # --- Scripts ----------------------------------------------------------------------------------

    def _script_modifie(self, script: ScriptEcrit) -> None:
        """Texte modifié à la main : l'app revérifie ce qui se compte (durée, mots interdits…)."""
        if self._projet is None:
            return
        gardes = [p for p in script.relecture if p.par == "modele" or p.critere == "balises"]
        script.relecture = controler(script, self._projet.ecriture.brief) + gardes
        carte = self.scripts.carte(script)
        if carte is not None:
            carte.rafraichir()
        self._modifie()

    def script_envoye(self, script: ScriptEcrit) -> None:
        """Appelé par la fenêtre principale quand le module Voix a reçu les répliques du script."""
        script.envoye_le = datetime.now().astimezone().isoformat(timespec="seconds")
        carte = self.scripts.carte(script)
        if carte is not None:
            carte.rafraichir()
        self._enregistrer()

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
        carte = self.scripts.carte(script)
        if carte is not None:
            carte.rafraichir()
        self._enregistrer()
        self._mettre_a_jour_estimations()
        self._afficher("Script gardé comme exemple : le modèle s'en inspirera pour les prochains scripts.", "succes")

    def supprimer_script(self, script: ScriptEcrit, confirmer: bool = True) -> None:
        if self._projet is None or script not in self._projet.ecriture.scripts:
            return
        if confirmer:
            reponse = QMessageBox.question(
                self,
                "Supprimer le script",
                "Supprimer ce script ? (S'il a été gardé comme exemple, l'exemple reste.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reponse != QMessageBox.StandardButton.Yes:
                return
        self._projet.ecriture.scripts.remove(script)
        self.scripts.definir(self._projet.ecriture.scripts)
        self._enregistrer()

    def quitter(self) -> None:
        """Quand on passe à un autre module : la lecture d'un essai de prononciation s'arrête."""
        self.lecteur.arreter()
        self.enregistrer_maintenant()

