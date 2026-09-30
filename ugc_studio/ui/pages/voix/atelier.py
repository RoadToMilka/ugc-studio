"""Atelier de voix off (§5) : modèle et voix (bibliothèque, favoris, voix créées), script en
répliques (chacune avec son style), dictionnaire de prononciation, génération, prises."""

from __future__ import annotations

import logging

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout

from ....conseils import CONSEILS_STYLE
from ....estimation import estimer_repliques
from ....fournisseurs.capacites import MODELES_CONNUS, Capacite, modeles_pour
from ....fournisseurs.google_voix import VOIX_GOOGLE, VOIX_PAR_DEFAUT, voix_de_base
from ....fournisseurs.voix import VoixBibliotheque
from ....generation import (
    enregistrer_prise,
    preparer,
    produire_audio,
    repliques_api,
    tokens_par_seconde,
)
from ....projets import LANGUES, Projet
from ....prononciation import fusionner
from ....script import est_vide
from ....services import Services
from ... import taches
from ...composants.conseils import ListeConseils
from ...composants.editeur_script import EditeurScript
from ...composants.elements import bloc, bouton, libelle
from ...composants.lecteur import Lecteur
from ...composants.montant_label import MontantLabel
from ...composants.palette_balises import PaletteBalises
from ...connexion_ia import FOURNISSEUR, adaptateur_par_defaut, message_erreur
from ...dialogues.prononciation import DialoguePrononciation
from ...dialogues.styles import DialogueBibliothequeStyles
from ...dialogues.voix import DialogueBibliothequeVoix
from ...extraits import EcouteVoix, fichier_prononciation
from ...theme import Dimensions, Espacements
from ..base import Page
from .prises import ListePrises, minutes_secondes
from .repliques import CarteReplique, ListeRepliques

journal = logging.getLogger(__name__)

DELAI_ENREGISTREMENT_MS = 800  # enregistrement automatique après une pause dans la frappe
CLE_CONSEILS_VISIBLES = "conseils_styles_visibles"


class AtelierVoix(Page):
    def __init__(self, services: Services):
        super().__init__("Voix", "Voix off générée par IA (TTS).", largeur_max=Dimensions.CONTENU_LARGEUR_MAX)
        self._services = services
        self._projet: Projet | None = None
        self._chargement = False
        self.lecteur = Lecteur(self)
        self.ecoute = EcouteVoix(services, self.lecteur, self._afficher, self._occupe_ecoute)

        self._minuterie = QTimer(self)
        self._minuterie.setSingleShot(True)
        self._minuterie.setInterval(DELAI_ENREGISTREMENT_MS)
        self._minuterie.timeout.connect(self._enregistrer)

        # --- Voix : modèle et voix ---
        cadre, d = bloc("Voix")
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.modele = QComboBox()
        self.modele.currentIndexChanged.connect(self._reglage_change)
        ligne.addWidget(self.modele, 1)
        self.voix = QComboBox()
        self.voix.setToolTip("Tes favoris ★ et tes voix créées d'abord, puis les 30 voix de base")
        self.voix.currentIndexChanged.connect(self._voix_changee)
        ligne.addWidget(self.voix, 1)
        self.bouton_bibliotheque_voix = bouton(
            "", variante="icone", nom_icone="library", action=self.ouvrir_bibliotheque_voix
        )
        self.bouton_bibliotheque_voix.setToolTip("Bibliothèque de voix : toutes les voix de Google, favoris, Voice Design")
        ligne.addWidget(self.bouton_bibliotheque_voix)
        self.bouton_extrait = bouton("Écouter la voix", nom_icone="play", action=self.ecouter_extrait)
        self.bouton_extrait.setToolTip("Joue un extrait de cette voix (préparé une seule fois, puis gardé).")
        ligne.addWidget(self.bouton_extrait)
        d.addLayout(ligne)
        self.info_modeles = libelle("", "avertissement")
        self.info_modeles.hide()
        d.addWidget(self.info_modeles)
        self.contenu.addWidget(cadre)

        # --- Script : répliques, outils, palette de balises ---
        cadre, d = bloc("Script")
        d.addWidget(
            libelle(
                "Découpe en répliques quand l'émotion change (ex. hook énergique, puis témoignage calme) : "
                "chaque réplique a son propre style. Tout part dans la même génération.",
                "legende",
            )
        )
        self.repliques = ListeRepliques(services)
        self.repliques.modifiee.connect(self._script_modifie)
        self.repliques.bibliotheque_demandee.connect(self.ouvrir_bibliotheque)
        d.addWidget(self.repliques)
        outils = QHBoxLayout()
        outils.setSpacing(Espacements.S)
        outils.addWidget(
            bouton("Ajouter une réplique", variante="discret", nom_icone="list-plus", action=self.ajouter_replique)
        )
        accent = bouton("Accentuer", variante="discret", nom_icone="case-upper", action=self.accentuer)
        accent.setToolTip(
            "Met le mot sélectionné en valeur : le modèle appuie sur les mots en MAJUSCULES. "
            "Les sous-titres gardent l'écriture d'origine."
        )
        outils.addWidget(accent)
        prononciation = bouton("Prononciation", variante="discret", nom_icone="book-a", action=self.ouvrir_prononciation)
        prononciation.setToolTip("Dictionnaire de prononciation : pour les mots que la voix prononce mal (noms de marque…)")
        outils.addWidget(prononciation)
        outils.addStretch(1)
        self.estimation = libelle("", "legende", retour_a_la_ligne=False)
        outils.addWidget(self.estimation)
        self.cout_estime = MontantLabel(0)
        self.cout_estime.setProperty("role", "legende")
        outils.addWidget(self.cout_estime)
        d.addLayout(outils)
        d.addSpacing(Espacements.S)
        d.addWidget(libelle("Balises — clique dans le texte, puis sur une balise pour l'insérer", "legende"))
        self.palette = PaletteBalises()
        self.palette.balise_choisie.connect(lambda nom: self.editeur.inserer_balise(nom))
        d.addWidget(self.palette)
        self.contenu.addWidget(cadre)

        # --- Conseils Google pour les styles (repliables) ---
        cadre, d = bloc()
        entete = QHBoxLayout()
        entete.setSpacing(Espacements.S)
        entete.addWidget(libelle("Conseils Google pour les styles", "titre-bloc", retour_a_la_ligne=False))
        entete.addStretch(1)
        self.bouton_conseils = bouton("", variante="discret", action=self.basculer_conseils)
        entete.addWidget(self.bouton_conseils)
        d.addLayout(entete)
        self.conseils = ListeConseils(CONSEILS_STYLE)
        d.addWidget(self.conseils)
        self.contenu.addWidget(cadre)
        self._afficher_conseils(bool(services.preferences.lire(CLE_CONSEILS_VISIBLES, True)))

        # --- Générer ---
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.M)
        self.bouton_generer = bouton("Générer la voix", variante="principal", nom_icone="audio-lines", action=self.generer)
        ligne.addWidget(self.bouton_generer)
        self.statut = libelle("", "secondaire")
        ligne.addWidget(self.statut, 1)
        self.contenu.addLayout(ligne)

        # --- Prises ---
        cadre, d = bloc("Prises")
        self.prises = ListePrises(services, self.lecteur)
        d.addWidget(self.prises)
        self.contenu.addWidget(cadre)

        services.projets.abonner(self._projet_change)
        services.connexions.abonner(self._remplir_modeles)
        services.prix.abonner(self._mettre_a_jour_estimation)
        services.voix.abonner(self._remplir_voix)
        self._remplir_modeles()
        self._remplir_voix()
        self._projet_change(services.projets.projet)

    @property
    def editeur(self) -> EditeurScript:
        """Éditeur de la réplique en cours (celle où la palette insère les balises)."""
        return self.repliques.editeur_actif

    # --- Projet ------------------------------------------------------------------------------

    def _projet_change(self, projet: Projet | None) -> None:
        if self._minuterie.isActive():
            self._minuterie.stop()
            self._enregistrer()
        self.lecteur.arreter()
        self._projet = projet
        if projet is None:
            return
        self._chargement = True
        self.titre.setText(f"Voix — {projet.nom}")
        self._choisir(self.modele, projet.voix.modele)
        self._selectionner_voix(projet.voix.voix or VOIX_PAR_DEFAUT)
        self.repliques.definir(projet.repliques)
        self._chargement = False
        self.statut.setText(f"Langue du projet : {LANGUES.get(projet.langue, projet.langue)}")
        self.prises.rafraichir()
        self._mettre_a_jour_estimation()

    @staticmethod
    def _choisir(liste: QComboBox, valeur: str) -> None:
        index = liste.findData(valeur)
        if index >= 0:
            liste.setCurrentIndex(index)

    def _remplir_modeles(self) -> None:
        """Modèles de voix accessibles avec les clés (croisement avec les capacités, §3.4)."""
        choix = self.modele.currentData() or (self._projet.voix.modele if self._projet else None)
        disponibles = self._services.connexions.modeles_disponibles(FOURNISSEUR)
        compatibles = [c for c in modeles_pour({Capacite.TTS}, disponibles) if c.compatible]
        self.modele.blockSignals(True)
        self.modele.clear()
        if compatibles:
            for c in compatibles:
                self.modele.addItem(c.nom, c.identifiant)
            self.info_modeles.hide()
        else:
            for modele in MODELES_CONNUS:
                if Capacite.TTS in modele.capacites and modele.principal:
                    self.modele.addItem(modele.nom, modele.identifiant)
            self.info_modeles.setText(
                "Aucune clé testée : ajoute et teste ta clé Google dans Réglages → Connexions API."
            )
            self.info_modeles.show()
        self._choisir(self.modele, choix or "gemini-3.8-flash-tts")
        self.modele.blockSignals(False)

    # --- Voix : favoris, voix créées, 30 voix de base ----------------------------------------

    def _remplir_voix(self) -> None:
        """Liste des voix : favoris ★, puis voix créées, puis voix de base (sans doublon)."""
        gestion = self._services.voix
        actuelle = self.voix.currentData() or (self._projet.voix.voix if self._projet else VOIX_PAR_DEFAUT)
        favoris = gestion.favoris()
        creees = [v.identifiant for v in gestion.voix_creees() if v.identifiant not in favoris]
        base = [v.nom for v in VOIX_GOOGLE if v.nom not in favoris]
        self.voix.blockSignals(True)
        self.voix.clear()
        for groupe, prefixe in ((favoris, "★ "), (creees, ""), (base, "")):
            if not groupe:
                continue
            if self.voix.count():
                self.voix.insertSeparator(self.voix.count())
            for identifiant in groupe:
                self.voix.addItem(prefixe + gestion.libelle(identifiant), identifiant)
        self._selectionner_voix(actuelle, signaler=False)
        self.voix.blockSignals(False)

    def _selectionner_voix(self, identifiant: str, signaler: bool = True) -> None:
        """Choisit une voix dans la liste (en l'ajoutant en tête si elle n'y est pas encore)."""
        if self.voix.findData(identifiant) < 0:
            self.voix.insertItem(0, self._services.voix.libelle(identifiant), identifiant)
        if not signaler:
            self.voix.setCurrentIndex(self.voix.findData(identifiant))
            return
        self._choisir(self.voix, identifiant)

    def _voix_changee(self, *_args) -> None:
        """Une voix créée l'a été avec un modèle précis : on prend ce modèle avec elle."""
        voix = self._services.voix.voix(self.voix.currentData() or "")
        if voix is not None and voix.creee and voix.modele and self.modele.findData(voix.modele) >= 0:
            self._choisir(self.modele, voix.modele)
        self._reglage_change()

    def ouvrir_bibliotheque_voix(self) -> None:
        dialogue = DialogueBibliothequeVoix(
            self._services,
            self.lecteur,
            self.window(),
            modele=self.modele.currentData() or "gemini-3.8-flash-tts",
            langue=self._projet.langue if self._projet else "fr-FR",
        )
        if dialogue.exec() and dialogue.voix_choisie is not None:
            self.choisir_voix(dialogue.voix_choisie)

    def choisir_voix(self, voix: VoixBibliotheque) -> None:
        self._selectionner_voix(voix.identifiant)
        self._afficher(f"Voix choisie : {self._services.voix.nom(voix.identifiant)}.", "secondaire")

    # --- Modifications (enregistrées automatiquement) ----------------------------------------

    def _reglage_change(self, *_args) -> None:
        if self._chargement or self._projet is None:
            return
        self._projet.voix.modele = self.modele.currentData() or self._projet.voix.modele
        self._projet.voix.voix = self.voix.currentData() or self._projet.voix.voix
        self._minuterie.start()
        self._mettre_a_jour_estimation()

    def _script_modifie(self) -> None:
        if self._chargement or self._projet is None:
            return
        self._minuterie.start()
        self._mettre_a_jour_estimation()

    def enregistrer_maintenant(self) -> None:
        """Enregistre sans attendre (ex. à la fermeture de l'app)."""
        self._minuterie.stop()
        self._enregistrer()

    def _enregistrer(self) -> None:
        if self._projet is None:
            return
        self._projet.repliques = self.repliques.repliques()
        self._services.projets.enregistrer()

    def _prononciations(self):
        projet = self._projet.prononciations if self._projet else []
        return fusionner(self._services.prononciations.entrees, projet)

    def _mettre_a_jour_estimation(self) -> None:
        modele = self.modele.currentData() or "gemini-3.8-flash-tts"
        estimation = estimer_repliques(
            repliques_api(self.repliques.repliques(), self._prononciations()),
            modele,
            self._services.prix,
            tokens_par_seconde(self._services, modele),
        )
        self.estimation.setText(f"{estimation.caracteres} caractères  ·  ≈ {minutes_secondes(estimation.duree_s)}  ·  ≈")
        if estimation.cout_eur is None:
            self.cout_estime.setText("prix inconnu")
        else:
            self.cout_estime.definir_montant(estimation.cout_eur)

    # --- Outils du script --------------------------------------------------------------------

    def ajouter_replique(self) -> None:
        self.repliques.ajouter(apres=self.repliques.carte_active)

    def accentuer(self) -> None:
        self.editeur.basculer_accent()

    def basculer_conseils(self) -> None:
        visibles = self.conseils.isHidden()
        self._afficher_conseils(visibles)
        self._services.preferences.ecrire(CLE_CONSEILS_VISIBLES, visibles)
        self._services.preferences.enregistrer()

    def _afficher_conseils(self, visibles: bool) -> None:
        self.conseils.setVisible(visibles)
        self.bouton_conseils.setText("Masquer" if visibles else "Afficher")

    def ouvrir_bibliotheque(self, carte: CarteReplique) -> None:
        """📚 d'une réplique : choisir un style enregistré ; il s'applique à cette réplique,
        avec sa voix et son modèle."""
        dialogue = DialogueBibliothequeStyles(
            self._services,
            self.window(),
            cible=carte.titre.text().lower(),
            style_actuel=(carte.champ_style.consigne(), carte.champ_style.consigne_fr()),
            modele=self.modele.currentData() or "gemini-3.8-flash-tts",
            voix=self.voix.currentData() or VOIX_PAR_DEFAUT,
            langue=self._projet.langue if self._projet else "fr-FR",
        )
        if dialogue.exec() and dialogue.style_choisi is not None:
            self.appliquer_style(carte, dialogue.style_choisi)

    def appliquer_style(self, carte: CarteReplique, style) -> None:
        carte.champ_style.definir(style.consigne, style.consigne_fr)
        details = []
        connue = voix_de_base(style.voix) or self._services.voix.voix(style.voix)
        if connue is not None and style.voix != self.voix.currentData():
            self._selectionner_voix(style.voix)
            details.append(f"voix {self._services.voix.nom(style.voix)}")
        if self.modele.findData(style.modele) >= 0 and style.modele != self.modele.currentData():
            self._choisir(self.modele, style.modele)
            details.append(self.modele.currentText())
        message = f"Style « {style.nom} » appliqué à la {carte.titre.text().lower()}"
        self._afficher(message + (f" ({', '.join(details)})." if details else "."), "secondaire")

    def ouvrir_prononciation(self) -> None:
        dialogue = DialoguePrononciation(self._services, self.tester_prononciation, self.window())
        if dialogue.exec():
            self._mettre_a_jour_estimation()

    # --- Génération --------------------------------------------------------------------------

    def _occupe(self, occupe: bool, message: str = "") -> None:
        self.bouton_generer.setEnabled(not occupe)
        self.bouton_extrait.setEnabled(not occupe)
        self._afficher(message, "secondaire")

    def _afficher(self, message: str, role: str) -> None:
        self.statut.setText(message)
        self.statut.setProperty("role", role)
        self.statut.style().unpolish(self.statut)
        self.statut.style().polish(self.statut)

    def generer(self) -> None:
        if self._projet is None:
            return
        self._enregistrer()
        repliques = self.repliques.repliques()
        if all(est_vide(r.script) for r in repliques):
            self._afficher("Le script est vide : écris d'abord le texte à dire.", "erreur")
            return
        try:
            adaptateur = adaptateur_par_defaut(self._services)
        except Exception as erreur:  # noqa: BLE001 — message clair affiché
            self._afficher(message_erreur(erreur), "erreur")
            return
        commande = preparer(
            FOURNISSEUR,
            self.modele.currentData(),
            self.voix.currentData(),
            repliques,
            self._projet.nom,
            self._prononciations(),
        )
        vitesse = tokens_par_seconde(self._services, commande.modele)
        self._occupe(True, "Génération en cours… (quelques secondes)")
        projet = self._projet

        def fin(resultat) -> None:
            self._occupe(False)
            if self._projet is not projet:
                return  # le projet a changé pendant la génération
            prise = enregistrer_prise(self._services, commande, resultat)
            self._afficher(f"{prise.nom} prête ({minutes_secondes(prise.duree_s)}).", "succes")
            self.prises.rafraichir()
            self._mettre_a_jour_estimation()
            self.lecteur.basculer(projet.chemin(prise.fichier))

        taches.lancer(lambda: produire_audio(adaptateur, commande, vitesse), fin, self._echec)

    def _echec(self, erreur: Exception) -> None:
        self._occupe(False)
        self._afficher(message_erreur(erreur), "erreur")

    def _occupe_ecoute(self, occupe: bool) -> None:
        self.bouton_extrait.setEnabled(not occupe)

    def ecouter_extrait(self) -> None:
        """▶ : un extrait de la voix choisie (préparé une fois, puis gardé en cache)."""
        langue = self._projet.langue if self._projet else "fr-FR"
        self.ecoute.ecouter(self.voix.currentData(), self.modele.currentData(), langue)

    def tester_prononciation(self, texte: str) -> None:
        """▶ du dictionnaire : la voix choisie dit la prononciation (gardée en cache)."""
        modele, voix = self.modele.currentData(), self.voix.currentData()
        self.ecoute.dire(
            texte, voix, modele, "essai de prononciation", fichier_prononciation(voix, modele, texte),
            f"Prononciation de « {texte} »…",
        )
