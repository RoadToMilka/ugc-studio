"""Atelier de voix off (§5) : choix du modèle et de la voix, script à badges, génération, prises."""

from __future__ import annotations

import logging
from dataclasses import replace

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit

from ....audio import en_wav
from ....chemins import dossier_cache
from ....connexions import ErreurConnexion
from ....estimation import estimer
from ....fournisseurs import creer_adaptateur
from ....fournisseurs.base import ErreurFournisseur
from ....fournisseurs.capacites import MODELES_CONNUS, Capacite, modeles_pour
from ....fournisseurs.google_voix import VOIX_GOOGLE, VOIX_PAR_DEFAUT, phrase_extrait, voix_de_base
from ....fournisseurs.voix import Replique, RequeteVoix
from ....generation import enregistrer_prise, noter_cout, preparer, produire_audio, tokens_par_seconde
from ....projets import LANGUES, Projet
from ....script import est_vide
from ....services import Services
from ... import taches
from ...composants.editeur_script import EditeurScript
from ...composants.elements import bloc, bouton, libelle
from ...composants.lecteur import Lecteur
from ...composants.montant_label import MontantLabel
from ...composants.palette_balises import PaletteBalises
from ...theme import Dimensions, Espacements
from ..base import Page
from .prises import ListePrises, minutes_secondes

journal = logging.getLogger(__name__)

FOURNISSEUR = "google"  # V1 : Google uniquement
DELAI_ENREGISTREMENT_MS = 800  # enregistrement automatique après une pause dans la frappe


class AtelierVoix(Page):
    def __init__(self, services: Services):
        super().__init__("Voix", "Voix off générée par IA (TTS).", largeur_max=Dimensions.CONTENU_LARGEUR_MAX)
        self._services = services
        self._projet: Projet | None = None
        self._chargement = False
        self.lecteur = Lecteur(self)

        self._minuterie = QTimer(self)
        self._minuterie.setSingleShot(True)
        self._minuterie.setInterval(DELAI_ENREGISTREMENT_MS)
        self._minuterie.timeout.connect(self._enregistrer)

        # --- Voix : modèle, voix, style ---
        cadre, d = bloc("Voix")
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.modele = QComboBox()
        self.modele.currentIndexChanged.connect(self._reglage_change)
        ligne.addWidget(self.modele, 1)
        self.voix = QComboBox()
        for voix in VOIX_GOOGLE:
            self.voix.addItem(voix.libelle, voix.nom)
        self.voix.currentIndexChanged.connect(self._reglage_change)
        ligne.addWidget(self.voix, 1)
        self.bouton_extrait = bouton("Écouter la voix", nom_icone="play", action=self.ecouter_extrait)
        self.bouton_extrait.setToolTip("Génère (une seule fois) une phrase d'exemple avec cette voix, puis la joue.")
        ligne.addWidget(self.bouton_extrait)
        d.addLayout(ligne)
        self.info_modeles = libelle("", "avertissement")
        self.info_modeles.hide()
        d.addWidget(self.info_modeles)

        d.addWidget(libelle("Style (facultatif) — comment dire le texte", "legende"))
        self.style = QLineEdit()
        self.style.setMinimumWidth(Dimensions.CHAMP_STYLE_LARGEUR_MIN)
        self.style.setPlaceholderText("ex. chaleureux et enthousiaste, débit rapide")
        self.style.textChanged.connect(self._reglage_change)
        d.addWidget(self.style)
        d.addWidget(
            libelle(
                "Conseil Google : un style court (quelques mots). Teste d'abord sans style ; les rires, "
                "soupirs et pauses se mettent en balises dans le texte.",
                "legende",
            )
        )
        self.contenu.addWidget(cadre)

        # --- Script ---
        cadre, d = bloc("Script")
        self.editeur = EditeurScript()
        self.editeur.script_modifie.connect(self._script_modifie)
        d.addWidget(self.editeur)
        outils = QHBoxLayout()
        outils.setSpacing(Espacements.S)
        accent = bouton("Accentuer", variante="discret", nom_icone="case-upper", action=self.editeur.basculer_accent)
        accent.setToolTip(
            "Met le mot sélectionné en valeur : le modèle appuie sur les mots en MAJUSCULES. "
            "Les sous-titres gardent l'écriture d'origine."
        )
        outils.addWidget(accent)
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
        self.palette.balise_choisie.connect(self.editeur.inserer_balise)
        d.addWidget(self.palette)
        self.contenu.addWidget(cadre)

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
        self._remplir_modeles()
        self._projet_change(services.projets.projet)

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
        self._choisir(self.voix, projet.voix.voix if voix_de_base(projet.voix.voix) else VOIX_PAR_DEFAUT)
        self.style.setText(projet.voix.style)
        self.editeur.definir_segments(projet.script)
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
                if Capacite.TTS in modele.capacites:
                    self.modele.addItem(modele.nom, modele.identifiant)
            self.info_modeles.setText(
                "Aucune clé testée : ajoute et teste ta clé Google dans Réglages → Connexions API."
            )
            self.info_modeles.show()
        self._choisir(self.modele, choix or "gemini-3.8-flash-tts")
        self.modele.blockSignals(False)

    # --- Modifications (enregistrées automatiquement) ----------------------------------------

    def _reglage_change(self, *_args) -> None:
        if self._chargement or self._projet is None:
            return
        self._projet.voix.modele = self.modele.currentData() or self._projet.voix.modele
        self._projet.voix.voix = self.voix.currentData() or self._projet.voix.voix
        self._projet.voix.style = self.style.text()
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
        self._projet.script = self.editeur.segments()
        self._services.projets.enregistrer()

    def _mettre_a_jour_estimation(self) -> None:
        modele = self.modele.currentData() or "gemini-3.8-flash-tts"
        texte = self.editeur.texte_api()
        estimation = estimer(texte, self.style.text(), modele, self._services.prix, tokens_par_seconde(self._services, modele))
        self.estimation.setText(f"{estimation.caracteres} caractères  ·  ≈ {minutes_secondes(estimation.duree_s)}  ·  ≈")
        if estimation.cout_eur is None:
            self.cout_estime.setText("prix inconnu")
        else:
            self.cout_estime.definir_montant(estimation.cout_eur)

    # --- Génération --------------------------------------------------------------------------

    def _adaptateur(self):
        connexion = self._services.connexions.connexion_par_defaut(FOURNISSEUR)
        if connexion is None:
            raise ErreurConnexion("Ajoute d'abord ta clé Google dans Réglages → Connexions API.")
        return creer_adaptateur(FOURNISSEUR, self._services.connexions.lire_cle(connexion.identifiant))

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
        segments = self.editeur.segments()
        if est_vide(segments):
            self._afficher("Le script est vide : écris d'abord le texte à dire.", "erreur")
            return
        try:
            adaptateur = self._adaptateur()
        except ErreurConnexion as erreur:
            self._afficher(str(erreur), "erreur")
            return
        commande = preparer(
            FOURNISSEUR,
            self.modele.currentData(),
            self.voix.currentData(),
            self.style.text(),
            segments,
            self._projet.nom,
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
        message = erreur.message if isinstance(erreur, ErreurFournisseur) else f"Erreur inattendue : {erreur}"
        self._afficher(message, "erreur")

    def ecouter_extrait(self) -> None:
        """▶ : phrase d'exemple avec la voix choisie (générée une fois, puis gardée en cache)."""
        modele = self.modele.currentData()
        voix = self.voix.currentData()
        langue = self._projet.langue if self._projet else "fr-FR"
        fichier = dossier_cache() / "extraits" / f"{modele}-{voix}-{langue}.wav"
        if fichier.exists():
            self.lecteur.basculer(fichier)
            return
        try:
            adaptateur = self._adaptateur()
        except ErreurConnexion as erreur:
            self._afficher(str(erreur), "erreur")
            return
        commande = replace(
            preparer(FOURNISSEUR, modele, voix, "", [{"texte": phrase_extrait(langue)}], None),
            operation="essai de voix",
        )
        self._occupe(True, f"Préparation de l'extrait de {voix}…")

        def fin(resultat) -> None:
            self._occupe(False)
            noter_cout(self._services, commande, resultat)
            fichier.parent.mkdir(parents=True, exist_ok=True)
            fichier.write_bytes(en_wav(resultat.audio_wav))
            self.lecteur.basculer(fichier)

        requete = RequeteVoix(modele, voix, (Replique(commande.texte_api),))
        taches.lancer(lambda: adaptateur.generer_voix(requete), fin, self._echec)
