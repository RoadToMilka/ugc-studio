"""Atelier de voix off (§5) : modèle et voix (bibliothèque, favoris, voix créées), script en
répliques (chacune avec son style), dictionnaire de prononciation, génération (avec écoute pendant
le calcul), variantes A/B et écoute comparative, prises.

V2 (lot 2) : nombres dits à la belge ou à la suisse (projets en français), durée estimée avec la
vitesse de parole mesurée sur les prises de la voix choisie, accroches du module Script envoyées
en variantes A/B."""

from __future__ import annotations

import logging

from dataclasses import dataclass, field

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from ....estimation import estimer_repliques
from ....fournisseurs.base import Adaptateur
from ....fournisseurs.capacites import Capacite, deviner_capacites
from ....fournisseurs.google_voix import VOIX_PAR_DEFAUT, voix_de_base
from ....fournisseurs.voix import VoixBibliotheque
from ....generation import (
    Commande,
    enregistrer_prise,
    preparer,
    produire_audio,
    repliques_api,
    tokens_par_seconde,
)
from ....modeles_charges import CHARGES, VOIX
from ....nombres import FRANCE
from ....nombres import VARIANTES as VARIANTES_NOMBRES
from ....projets import LANGUES, Projet, RepliqueProjet
from ....prononciation import fusionner
from ....script import est_vide
from ....services import Services
from ....variantes import LETTRES, ReglagesVariante, copie_replique
from ... import taches
from ...composants.choix_voix import (
    MODELE_VOIX_PAR_DEFAUT,
    choisir,
    remplir_modeles_voix,
    remplir_voix,
    selectionner_voix,
)
from ...composants.editeur_script import EditeurScript
from ...composants.elements import bloc, bouton, info, libelle, liste_deroulante, minutes_secondes
from ...composants.lecteur import Lecteur
from ...composants.lecteur_flux import LecteurFlux
from ...composants.montant_label import MontantLabel
from ...composants.palette_balises import PaletteBalises
from ...connexion_ia import FOURNISSEUR, adaptateur_par_defaut, message_erreur
from ...dialogues.comparaison import DialogueComparaison
from ...dialogues.prononciation import DialoguePrononciation
from ...dialogues.styles import DialogueBibliothequeStyles
from ...dialogues.variantes import DialogueVariantes
from ...dialogues.voix import DialogueBibliothequeVoix
from ...extraits import EcouteVoix, fichier_prononciation
from ...theme import Espacements
from ..base import Page
from .prises import ListePrises
from .repliques import CarteReplique, ListeRepliques

journal = logging.getLogger(__name__)

DELAI_ENREGISTREMENT_MS = 800  # enregistrement automatique après une pause dans la frappe
CLE_ECOUTE_DIRECTE = "ecoute_pendant_generation"


@dataclass
class SerieEnCours:
    """Variantes A/B en cours de génération : elles partent l'une après l'autre."""

    numero: int
    projet: Projet
    adaptateur: Adaptateur
    a_faire: list[tuple[str, Commande]]  # (lettre, commande) pas encore générées
    total: int
    faites: list[str] = field(default_factory=list)  # lettres prêtes
    erreur: str = ""
    arretee: bool = False


class AtelierVoix(Page):
    def __init__(self, services: Services):
        super().__init__("Voix", "Voix off générée par IA (TTS).", conseils="voix")
        self._services = services
        self._projet: Projet | None = None
        self._chargement = False
        self.lecteur = Lecteur(self)
        self.ecoute = EcouteVoix(services, self.lecteur, self._afficher, self._occupe_ecoute)
        # Écoute pendant la génération ; une prise lancée à la main l'interrompt.
        self.flux = LecteurFlux(self)
        self.lecteur.etat_change.connect(lambda _chemin, lecture: self.flux.arreter() if lecture else None)
        self._serie: SerieEnCours | None = None
        self.comparaison: DialogueComparaison | None = None

        self._minuterie = QTimer(self)
        self._minuterie.setSingleShot(True)
        self._minuterie.setInterval(DELAI_ENREGISTREMENT_MS)
        self._minuterie.timeout.connect(self._enregistrer)

        # --- Voix et modèle ---
        cadre, d = bloc("Voix et modèle")
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.modele = liste_deroulante()
        self.modele.currentIndexChanged.connect(self._reglage_change)
        self.modele.currentIndexChanged.connect(lambda _index: self._declarer_modele())
        ligne.addWidget(self.modele, 1)
        self.voix = liste_deroulante()
        self.voix.setToolTip("Tes favoris ★ et tes voix créées d'abord, puis les 30 voix de base")
        self.voix.currentIndexChanged.connect(self._voix_changee)
        ligne.addWidget(self.voix, 1)
        self.bouton_bibliotheque_voix = bouton(
            "", variante="icone", nom_icone="library", action=self.ouvrir_bibliotheque_voix
        )
        self.bouton_bibliotheque_voix.setToolTip("Bibliothèque de voix : toutes les voix de Google, favoris, Voice Design")
        ligne.addWidget(self.bouton_bibliotheque_voix)
        self.bouton_extrait = bouton("Écouter", nom_icone="play", action=self.ecouter_extrait)
        self.bouton_extrait.setToolTip("Joue un extrait de cette voix (préparé une seule fois, puis gardé).")
        ligne.addWidget(self.bouton_extrait)
        d.addLayout(ligne)
        self.info_modeles = libelle("", "avertissement")
        self.info_modeles.hide()
        d.addWidget(self.info_modeles)
        # Nombres dits à la belge ou à la suisse (V2, lot 2) : projets en français seulement.
        self.zone_nombres = QWidget()
        ligne_nombres = QHBoxLayout(self.zone_nombres)
        ligne_nombres.setContentsMargins(0, 0, 0, 0)
        ligne_nombres.setSpacing(Espacements.M)
        ligne_nombres.addWidget(libelle("Nombres dits", retour_a_la_ligne=False))
        self.nombres = liste_deroulante(
            "Façon dont la voix dit les prix et les nombres (septante, nonante…). Le script et les "
            "sous-titres gardent les chiffres."
        )
        for code, nom in VARIANTES_NOMBRES.items():
            self.nombres.addItem(nom, code)
        self.nombres.currentIndexChanged.connect(self._reglage_change)
        ligne_nombres.addWidget(self.nombres)
        ligne_nombres.addStretch(1)
        d.addWidget(self.zone_nombres)
        # Script écrit pour une femme, voix masculine (ou l'inverse) : avertissement (V2, §10.11).
        self.info_genre = libelle("", "legende-avertissement")
        self.info_genre.hide()
        d.addWidget(self.info_genre)
        self.contenu.addWidget(cadre)

        # --- Script : répliques, outils, palette de balises ---
        cadre, d = bloc("Script")
        d.addWidget(
            info(
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
            bouton("Ajouter une réplique", variante="contour", nom_icone="list-plus", action=self.ajouter_replique)
        )
        accent = bouton("Accentuer", variante="contour", nom_icone="case-upper", action=self.accentuer)
        accent.setToolTip(
            "Met le mot sélectionné en valeur : le modèle appuie sur les mots en MAJUSCULES. "
            "Les sous-titres gardent l'écriture d'origine."
        )
        outils.addWidget(accent)
        prononciation = bouton("Prononciation", variante="contour", nom_icone="book-a", action=self.ouvrir_prononciation)
        prononciation.setToolTip("Dictionnaire de prononciation : pour les mots que la voix prononce mal (noms de marque…)")
        outils.addWidget(prononciation)
        outils.addStretch(1)
        d.addLayout(outils)
        d.addSpacing(Espacements.S)
        # « Balises » est un sous-titre du bloc (comme « Découpage » dans Sous-titres), l'aide en dessous.
        d.addWidget(libelle("Balises", "intitule"))
        d.addWidget(info("Clique dans le texte, puis sur une balise pour l'insérer.", "legende"))
        self.palette = PaletteBalises()
        self.palette.balise_choisie.connect(lambda nom: self.editeur.inserer_balise(nom))
        d.addWidget(self.palette)
        self.contenu.addWidget(cadre)

        # --- Générer : boutons et estimation (caractères, durée, coût), option d'écoute, avancement ---
        generation = QVBoxLayout()
        generation.setSpacing(Espacements.S)
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.M)
        # « Générer l'audio » (et non « Générer la voix ») : on ne le confond pas avec « Créer une voix ».
        self.bouton_generer = bouton("Générer l'audio", variante="principal", nom_icone="audio-lines", action=self.generer)
        ligne.addWidget(self.bouton_generer)
        self.bouton_variantes = bouton("Variantes…", nom_icone="git-compare-arrows", action=self.ouvrir_variantes)
        self.bouton_variantes.setToolTip(
            "Tests A/B : plusieurs versions du script en un seul lancement, puis écoute comparative"
        )
        ligne.addWidget(self.bouton_variantes)
        self.bouton_arreter = bouton("Arrêter", nom_icone="square", action=self.arreter_variantes)
        self.bouton_arreter.setToolTip("Arrête la série après la variante en cours (celles déjà prêtes sont gardées)")
        self.bouton_arreter.hide()
        ligne.addWidget(self.bouton_arreter)
        estimation = QHBoxLayout()
        estimation.setSpacing(Espacements.XS)
        self.estimation = libelle("", "legende", retour_a_la_ligne=False)
        estimation.addWidget(self.estimation)
        self.cout_estime = MontantLabel(0)
        self.cout_estime.setProperty("role", "legende")
        estimation.addWidget(self.cout_estime)
        ligne.addLayout(estimation)
        ligne.addStretch(1)
        generation.addLayout(ligne)
        self.ecoute_directe = QCheckBox("Écouter pendant la génération")
        self.ecoute_directe.setToolTip(
            "La voix commence à jouer avant la fin du calcul (modèles Gemini 3.8). "
            "Sinon, la prise est jouée quand elle est prête."
        )
        self.ecoute_directe.setChecked(bool(services.preferences.lire(CLE_ECOUTE_DIRECTE, True)))
        self.ecoute_directe.toggled.connect(self._ecoute_directe_changee)
        generation.addWidget(self.ecoute_directe)
        self.statut = libelle("", "secondaire")
        generation.addWidget(self.statut)
        self.contenu.addLayout(generation)

        # --- Prises ---
        cadre, d = bloc("Prises")
        self.prises = ListePrises(services, self.lecteur)
        self.prises.comparaison_demandee.connect(self.comparer)
        d.addWidget(self.prises)
        self.contenu.addWidget(cadre)

        services.projets.abonner(self._projet_change)
        services.connexions.abonner(self._remplir_modeles)
        services.modeles.abonner(self._remplir_modeles, {CHARGES})  # modèles chargés ou retirés
        services.prix.abonner(self._mettre_a_jour_estimation)
        services.vitesses.abonner(self._mettre_a_jour_estimation)  # vitesse de parole mesurée (V2)
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
        self.flux.arreter()
        self._projet = projet
        if projet is None:
            self._declarer_modele()
            return
        self._chargement = True
        self.titre.setText(f"Voix / {projet.nom}")
        # Le modèle du projet est toujours proposé, même s'il n'est plus chargé : il est alors
        # rechargé (voir modeles_charges.py), sans rien changer dans le projet.
        remplir_modeles_voix(self.modele, self._services, projet.voix.modele)
        choisir(self.modele, projet.voix.modele)
        self._declarer_modele()
        self._selectionner_voix(projet.voix.voix or VOIX_PAR_DEFAUT)
        choisir(self.nombres, projet.voix.nombres)
        self.zone_nombres.setVisible(projet.langue.startswith("fr"))
        self.repliques.definir(projet.repliques)
        self._chargement = False
        self.statut.setText(f"Langue du projet : {LANGUES.get(projet.langue, projet.langue)}")
        self.prises.rafraichir()
        self._mettre_a_jour_estimation()
        self._verifier_genre()

    def remplacer_repliques(
        self, repliques: list[RepliqueProjet], confirmer: bool = True, nombres: str | None = None
    ) -> bool:
        """« Envoyer dans Voix » (module Script, V2) : ces répliques remplacent celles du projet, avec
        leurs styles, balises et mots accentués. Si le module contient déjà un script, confirmation
        d'abord (l'ancien script reste dans l'historique du module Script). `nombres` : nombres dits
        à la française, à la belge ou à la suisse, d'après la langue du script (None : inchangé).
        Renvoie True si c'est fait."""
        if self._projet is None or not repliques:
            return False
        actuelles = [r for r in self.repliques.repliques() if not est_vide(r.script)]
        if confirmer and actuelles:
            quoi = "la réplique actuelle" if len(actuelles) == 1 else f"les {len(actuelles)} répliques actuelles"
            reponse = QMessageBox.question(
                self,
                "Envoyer dans Voix",
                f"Remplacer {quoi} du module Voix par ce script ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reponse != QMessageBox.StandardButton.Yes:
                return False
        self._chargement = True
        self.repliques.definir(repliques)
        self._chargement = False
        if nombres is not None:
            self.definir_nombres(nombres)
        self._minuterie.stop()
        self._enregistrer()
        self._mettre_a_jour_estimation()
        self._verifier_genre()
        precision = ""
        if self._nombres() != FRANCE:
            precision = f" (nombres dits {VARIANTES_NOMBRES[self._nombres()].split(' (')[0].lower()})"
        self._afficher(f"Script reçu du module Script{precision} : prêt pour « Générer l'audio ».", "succes")
        return True

    def definir_nombres(self, variante: str) -> None:
        """Nombres dits à la belge ou à la suisse (choisis d'après la langue d'un script envoyé)."""
        if self._projet is None or variante not in VARIANTES_NOMBRES:
            return
        choisir(self.nombres, variante)  # → _reglage_change : enregistré, estimation à jour

    def _nombres(self) -> str:
        """Variante des nombres pour la voix : celle du projet s'il est en français."""
        if self._projet is None or not self._projet.langue.startswith("fr"):
            return FRANCE
        return self.nombres.currentData() or FRANCE

    def _verifier_genre(self) -> None:
        """Personne qui parle du brief (module Script) et genre de la voix choisie : différents ?"""
        voulu = self._projet.ecriture.brief.genre if self._projet is not None else ""
        voix = self._services.voix.voix(self.voix.currentData() or "")
        genre_voix = {"female": "femme", "male": "homme"}.get(voix.genre if voix else "", "")
        differents = bool(voulu and genre_voix and voulu != genre_voix and self._projet.ecriture.scripts)
        if differents:
            self.info_genre.setText(
                f"Le script a été écrit pour {'une femme' if voulu == 'femme' else 'un homme'}, et cette voix est "
                f"{'féminine' if genre_voix == 'femme' else 'masculine'} : les accords du texte (« ravie », « ravi ») "
                "peuvent sonner faux."
            )
        self.info_genre.setVisible(differents)

    def _remplir_modeles(self) -> None:
        """Modèles de voix chargés et accessibles avec les clés (croisement avec les capacités, §3.4)."""
        choix = self.modele.currentData() or (self._projet.voix.modele if self._projet else None)
        avec_cle = remplir_modeles_voix(self.modele, self._services, choix)
        self.info_modeles.setText("Aucune clé testée : ajoute et teste ta clé Google dans Réglages → Connexions API.")
        self.info_modeles.setVisible(not avec_cle)
        self._declarer_modele()

    def _declarer_modele(self) -> None:
        """Réglages → Modèles et prix, « Utilisé dans » : le modèle choisi ici (projet ouvert)."""
        self._services.modeles.choisir(VOIX, self.modele.currentData() if self._projet else None)

    # --- Voix : favoris, voix créées, 30 voix de base ----------------------------------------

    def _remplir_voix(self) -> None:
        """Liste des voix : favoris ★, puis voix créées, puis voix de base (sans doublon)."""
        actuelle = self.voix.currentData() or (self._projet.voix.voix if self._projet else VOIX_PAR_DEFAUT)
        remplir_voix(self.voix, self._services, actuelle)

    def _selectionner_voix(self, identifiant: str) -> None:
        """Choisit une voix dans la liste (en l'ajoutant en tête si elle n'y est pas encore)."""
        selectionner_voix(self.voix, self._services, identifiant)

    def _voix_changee(self, *_args) -> None:
        """Une voix créée l'a été avec un modèle précis : on prend ce modèle avec elle."""
        voix = self._services.voix.voix(self.voix.currentData() or "")
        if voix is not None and voix.creee and voix.modele and self.modele.findData(voix.modele) >= 0:
            choisir(self.modele, voix.modele)
        self._reglage_change()
        self._verifier_genre()

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
        self._projet.voix.nombres = self.nombres.currentData() or FRANCE
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
        # Le projet de cette page (et pas forcément celui qui vient de s'ouvrir, voir _projet_change).
        self._services.projets.enregistrer(self._projet)

    def _prononciations(self):
        projet = self._projet.prononciations if self._projet else []
        return fusionner(self._services.prononciations.entrees, projet)

    def _mettre_a_jour_estimation(self) -> None:
        modele = self.modele.currentData() or "gemini-3.8-flash-tts"
        voix = self.voix.currentData() or VOIX_PAR_DEFAUT
        vitesse = self._services.vitesses.vitesse(voix)
        estimation = estimer_repliques(
            repliques_api(self.repliques.repliques(), self._prononciations(), self._nombres()),
            modele,
            self._services.prix,
            tokens_par_seconde(self._services, modele),
            vitesse.mots_par_seconde,
        )
        self.estimation.setText(f"{estimation.caracteres} caractères  ·  ≈ {minutes_secondes(estimation.duree_s)}  ·  ≈")
        # La même vitesse que le module Script (V2) : les deux modules annoncent la même durée.
        self.estimation.setToolTip(f"Durée estimée avec la {vitesse.texte(self._services.voix.nom(voix))}")
        if estimation.cout_eur is None:
            self.cout_estime.setText("prix inconnu")
        else:
            self.cout_estime.definir_montant(estimation.cout_eur)

    # --- Outils du script --------------------------------------------------------------------

    def ajouter_replique(self) -> None:
        self.repliques.ajouter(apres=self.repliques.carte_active)

    def accentuer(self) -> None:
        self.editeur.basculer_accent()

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
            choisir(self.modele, style.modele)
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
        self.bouton_variantes.setEnabled(not occupe)
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
            self._nombres(),
        )
        vitesse = tokens_par_seconde(self._services, commande.modele)
        projet = self._projet
        ecoute = self._preparer_ecoute(commande.modele)
        self._occupe(
            True,
            "Génération en cours… La voix commence à jouer dans un instant."
            if ecoute
            else "Génération en cours… (quelques secondes)",
        )

        def fin(resultat) -> None:
            self._occupe(False)
            if ecoute:
                self.flux.terminer()  # la lecture continue jusqu'au bout
            if self._projet is not projet:
                return  # le projet a changé pendant la génération
            prise = enregistrer_prise(self._services, commande, resultat)
            self._afficher(f"{prise.nom} prête ({minutes_secondes(prise.duree_s)}).", "succes")
            self.prises.rafraichir()
            self._mettre_a_jour_estimation()
            if not (ecoute and self.flux.a_joue):
                self.lecteur.basculer(projet.chemin(prise.fichier))

        def echec(erreur: Exception) -> None:
            self.flux.arreter()
            self._echec(erreur)

        if not ecoute:
            taches.lancer(lambda: produire_audio(adaptateur, commande, vitesse), fin, echec)
            return
        # Chaque morceau d'audio reçu dans la tâche de fond est confié au lecteur (tâche principale).
        taches.lancer_avec_progres(
            lambda progres: produire_audio(adaptateur, commande, vitesse, lambda pcm, f: progres((pcm, f))),
            fin,
            echec,
            lambda morceau: self.flux.ajouter(*morceau),
        )

    def _echec(self, erreur: Exception) -> None:
        self._occupe(False)
        self._afficher(message_erreur(erreur), "erreur")

    # --- Écoute pendant la génération (§5.6) --------------------------------------------------

    def _ecoute_directe_changee(self, active: bool) -> None:
        self._services.preferences.ecrire(CLE_ECOUTE_DIRECTE, active)
        self._services.preferences.enregistrer()

    def _preparer_ecoute(self, modele: str) -> bool:
        """Écouter pendant la génération ? Oui si l'option est cochée, si le modèle envoie son audio
        en flux et si une sortie audio est utilisable."""
        if not self.ecoute_directe.isChecked() or Capacite.TTS_FLUX not in deviner_capacites(modele):
            return False
        if not self.flux.commencer():
            return False
        self.lecteur.arreter()
        return True

    # --- Variantes A/B (§5.6) -----------------------------------------------------------------

    def reglages_de_base(self) -> ReglagesVariante:
        """Réglages actuels de l'atelier : le point de départ de chaque variante."""
        return ReglagesVariante(
            self.modele.currentData() or MODELE_VOIX_PAR_DEFAUT,
            self.voix.currentData() or VOIX_PAR_DEFAUT,
            [copie_replique(r) for r in self.repliques.repliques()],
        )

    def ouvrir_variantes(self) -> None:
        if self._projet is None:
            return
        self._enregistrer()
        base = self.reglages_de_base()
        if all(est_vide(r.script) for r in base.repliques):
            self._afficher("Le script est vide : écris d'abord le texte à dire.", "erreur")
            return
        dialogue = DialogueVariantes(self._services, base, self._prononciations(), self.window(), self._nombres())
        if dialogue.exec():
            self.generer_variantes(dialogue.variantes())

    def ouvrir_variantes_d_accroches(self, accroches: list[RepliqueProjet]) -> None:
        """« Envoyer les accroches en variantes » (module Script, V2) : la fenêtre Variantes s'ouvre sur
        « Réglages par variante », une variante par accroche (seule la réplique 1 change). Le script
        (avec la première accroche) est déjà dans l'atelier."""
        if self._projet is None or self._serie is not None or len(accroches) < 2:
            return
        self._enregistrer()
        base = self.reglages_de_base()
        if not base.repliques:
            return
        variantes = []
        for replique in accroches[: len(LETTRES)]:
            variante = base.copie()
            variante.repliques[0] = copie_replique(replique)
            variantes.append(variante)
        dialogue = DialogueVariantes(
            self._services, base, self._prononciations(), self.window(), self._nombres(), variantes
        )
        if dialogue.exec():
            self.generer_variantes(dialogue.variantes())

    def generer_variantes(self, variantes: list[ReglagesVariante]) -> None:
        """Génère les variantes l'une après l'autre ; chacune devient une prise de la même série."""
        if self._projet is None or self._serie is not None or not variantes:
            return
        try:
            adaptateur = adaptateur_par_defaut(self._services)
        except Exception as erreur:  # noqa: BLE001 — message clair affiché
            self._afficher(message_erreur(erreur), "erreur")
            return
        prononciations, nombres = self._prononciations(), self._nombres()
        a_faire = [
            (LETTRES[index], preparer(FOURNISSEUR, v.modele, v.voix, v.repliques, self._projet.nom, prononciations, nombres))
            for index, v in enumerate(variantes[: len(LETTRES)])
        ]
        self._serie = SerieEnCours(
            self._services.projets.nouvelle_serie(), self._projet, adaptateur, a_faire, len(a_faire)
        )
        self.lecteur.arreter()
        self.flux.arreter()
        self._occupe(True)
        self.bouton_variantes.hide()
        self.bouton_arreter.show()
        self.bouton_arreter.setEnabled(True)
        self._variante_suivante()

    def _variante_suivante(self) -> None:
        serie = self._serie
        if serie is None:
            return
        if serie.arretee or serie.erreur or not serie.a_faire or self._projet is not serie.projet:
            self._serie_finie()
            return
        lettre, commande = serie.a_faire.pop(0)
        numero = serie.total - len(serie.a_faire)
        self._afficher(f"Variante {lettre} en cours ({numero}/{serie.total})…", "secondaire")
        vitesse = tokens_par_seconde(self._services, commande.modele)

        def fin(resultat) -> None:
            if self._projet is serie.projet:
                enregistrer_prise(self._services, commande, resultat, serie.numero, lettre)
                serie.faites.append(lettre)
                self.prises.rafraichir()
            self._variante_suivante()

        def echec(erreur: Exception) -> None:
            serie.erreur = f"Variante {lettre} non générée : {message_erreur(erreur)}"
            self._variante_suivante()

        taches.lancer(lambda: produire_audio(serie.adaptateur, commande, vitesse), fin, echec)

    def arreter_variantes(self) -> None:
        """La série s'arrête après la variante en cours (celles déjà prêtes sont gardées)."""
        if self._serie is not None:
            self._serie.arretee = True
            self.bouton_arreter.setEnabled(False)
            self._afficher("Arrêt après la variante en cours…", "secondaire")

    def _serie_finie(self) -> None:
        serie, self._serie = self._serie, None
        self._occupe(False)
        self.bouton_arreter.hide()
        self.bouton_variantes.show()
        self._mettre_a_jour_estimation()
        pretes = ", ".join(serie.faites)
        if serie.erreur:
            suite = f" Déjà prêtes : {pretes}." if serie.faites else ""
            self._afficher(serie.erreur + suite, "erreur")
        elif serie.arretee:
            self._afficher(f"Série arrêtée. Variantes prêtes : {pretes or 'aucune'}.", "secondaire")
        else:
            self._afficher(f"{len(serie.faites)} variantes prêtes ({pretes}) : compare-les à l'écoute.", "succes")
        if len(serie.faites) >= 2 and self._projet is serie.projet:
            self.comparer(serie.numero)

    def comparer(self, numero: int) -> None:
        """Écoute comparative d'une série (fenêtre ouverte sans bloquer l'atelier)."""
        if self._projet is None or self.comparaison is not None:
            return
        self.lecteur.arreter()
        self.flux.arreter()
        self.comparaison = DialogueComparaison(self._services, numero, self.window())
        self.comparaison.finished.connect(self._comparaison_fermee)
        self.comparaison.open()

    def _comparaison_fermee(self, _resultat: int) -> None:
        if self.comparaison is not None:
            self.comparaison.deleteLater()
        self.comparaison = None
        self.prises.rafraichir()

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
