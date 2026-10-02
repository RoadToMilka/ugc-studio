"""Champs de consigne envoyés à Google **en anglais** : le style d'une réplique (§5.5) et la
description d'une voix créée avec Voice Design (§5.4 bis).

La traduction française s'affiche juste en dessous, pour comprendre ce qui est envoyé. Aides à côté
du champ :
- ✨ l'assistant : on choisit en français, l'app assemble la consigne anglaise ;
- 文A « Traduire en anglais » : on écrit en français, un modèle de texte Gemini traduit ;
- 📚 la bibliothèque de styles (styles seulement, facultatif) : réutiliser un style enregistré.
Sous le champ, des vérifications en direct signalent (sans bloquer) ce que Google déconseille.
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

from ...balises import nom_affiche
from ...conseils import Avertissement, verifier_description_voix, verifier_style
from ...services import Services
from ...traduction import MODELE_TRADUCTION, traduire_en_anglais
from .. import taches
from ..connexion_ia import FOURNISSEUR, adaptateur_par_defaut, message_erreur
from ..theme import Dimensions, Espacements
from .bouton import montrer_occupe
from .elements import afficher_message, bouton, libelle, vider_disposition


class ChampConsigne(QWidget):
    """Base commune : champ + aides + traduction affichée + vérifications en direct."""

    modifie = Signal()  # consigne ou traduction changées
    bibliotheque_demandee = Signal()
    balise_suggeree = Signal(str)  # « Insérer la balise « rire » » proposé par les vérifications (nom anglais)
    assistant_utilise = Signal(object)  # la fenêtre de l'assistant, après « Utiliser »

    INDICATION = ""
    AIDE_ASSISTANT = ""
    AIDE_BIBLIOTHEQUE = ""
    TEXTE_A_TRADUIRE = "Écris d'abord le texte en français, puis clique ici pour le traduire."
    PLUSIEURS_LIGNES = False  # champ de plusieurs lignes : les boutons restent en haut

    def __init__(self, services: Services, avec_bibliotheque: bool = False, parent=None):
        super().__init__(parent)
        self._services = services
        self._consigne_fr = ""
        self._programme = False  # vrai pendant un changement fait par l'app (pas par la frappe)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.XS)

        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.XS)
        self.champ = self._creer_editeur()
        ligne.addWidget(self.champ, 1)
        ligne.addSpacing(Espacements.XS)
        aides = QHBoxLayout()
        aides.setSpacing(Espacements.XS)
        if self.PLUSIEURS_LIGNES:
            # Boutons en face de la 1re ligne du champ (et non au milieu de sa hauteur).
            aides.setContentsMargins(0, Espacements.XS, 0, 0)
        # Crayon (et non baguette magique) : l'assistant aide à écrire, il ne génère rien tout seul.
        self.bouton_assistant = bouton("", variante="icone", nom_icone="pencil", action=self.ouvrir_assistant)
        self.bouton_assistant.setToolTip(self.AIDE_ASSISTANT)
        aides.addWidget(self.bouton_assistant)
        self.bouton_traduire = bouton("", variante="icone", nom_icone="languages", action=self.traduire)
        self.bouton_traduire.setToolTip("Traduire en anglais (modèle de texte Gemini, coût minime)")
        aides.addWidget(self.bouton_traduire)
        self.bouton_bibliotheque = None
        if avec_bibliotheque:
            self.bouton_bibliotheque = bouton(
                "", variante="icone", nom_icone="library", action=lambda: self.bibliotheque_demandee.emit()
            )
            self.bouton_bibliotheque.setToolTip(self.AIDE_BIBLIOTHEQUE)
            aides.addWidget(self.bouton_bibliotheque)
        ligne.addLayout(aides)
        if self.PLUSIEURS_LIGNES:
            ligne.setAlignment(aides, Qt.AlignmentFlag.AlignTop)
        disposition.addLayout(ligne)

        self.traduction = libelle("", "legende")
        self.traduction.hide()
        disposition.addWidget(self.traduction)
        self.message = libelle("", "legende")  # traduction en cours, erreur…
        self.message.hide()
        disposition.addWidget(self.message)
        self._avertissements = QVBoxLayout()
        self._avertissements.setSpacing(0)
        disposition.addLayout(self._avertissements)

    # --- À préciser par chaque sorte de champ -------------------------------------------------

    def _creer_editeur(self) -> QWidget:
        champ = QLineEdit()
        champ.setPlaceholderText(self.INDICATION)
        champ.textChanged.connect(self._texte_change)
        return champ

    def _texte_editeur(self) -> str:
        return self.champ.text()

    def _ecrire_editeur(self, texte: str) -> None:
        self.champ.setText(texte)

    def _verifications(self, texte: str) -> list[Avertissement]:
        return []

    def _dialogue_assistant(self):
        raise NotImplementedError

    # --- Valeur ------------------------------------------------------------------------------

    def consigne(self) -> str:
        """Le texte tel qu'envoyé à Google (en anglais)."""
        return self._texte_editeur().strip()

    def consigne_fr(self) -> str:
        """Sa traduction française (vide si le texte a été modifié à la main depuis)."""
        return self._consigne_fr

    def definir(self, consigne: str, consigne_fr: str = "") -> None:
        """Change le texte (et sa traduction française) sans passer par la frappe."""
        self._programme = True
        self._consigne_fr = consigne_fr.strip()
        self._ecrire_editeur(consigne)
        self._programme = False
        self._afficher_traduction()
        self._verifier()
        self.modifie.emit()

    def _texte_change(self, *_args) -> None:
        if not self._programme:
            # Modifié à la main : l'ancienne traduction ne correspond plus au texte.
            self._consigne_fr = ""
            self._afficher_traduction()
            self.message.hide()
            self._verifier()
            self.modifie.emit()

    def _afficher_traduction(self) -> None:
        self.traduction.setText(f"Traduction : {self._consigne_fr}")
        self.traduction.setVisible(bool(self._consigne_fr and self.consigne()))

    # --- Vérifications en direct ------------------------------------------------------------

    def avertissements(self) -> list[str]:
        return [a.message for a in self._verifications(self.consigne())] if self.consigne() else []

    def _verifier(self) -> None:
        vider_disposition(self._avertissements)
        if not self.consigne():
            return
        for avertissement in self._verifications(self.consigne()):
            texte = html.escape(avertissement.message)
            if avertissement.balise_suggeree:
                nom = avertissement.balise_suggeree
                affiche = html.escape(nom_affiche(nom))
                texte += f' <a href="{html.escape(nom)}">Insérer la balise « {affiche} » dans le texte</a>'
            etiquette = QLabel(texte)
            etiquette.setTextFormat(Qt.TextFormat.RichText)
            etiquette.setWordWrap(True)
            etiquette.setProperty("role", "legende-avertissement")
            etiquette.linkActivated.connect(self.balise_suggeree.emit)
            self._avertissements.addWidget(etiquette)

    # --- Assistant et traduction -------------------------------------------------------------

    def ouvrir_assistant(self) -> None:
        dialogue = self._dialogue_assistant()
        if dialogue.exec():
            anglais, francais = dialogue.resultat()
            self.definir(anglais, francais)
            self.assistant_utilise.emit(dialogue)

    def traduire(self) -> None:
        """Traduit le texte du champ (écrit en français) en anglais."""
        texte = self.consigne()
        if not texte:
            self._afficher_message(self.TEXTE_A_TRADUIRE, "legende")
            return
        try:
            adaptateur = adaptateur_par_defaut(self._services)
        except Exception as erreur:  # noqa: BLE001 — message clair affiché sous le champ
            self._afficher_message(message_erreur(erreur), "erreur")
            return
        montrer_occupe(self.bouton_traduire, True)  # le cercle tourne dans 文A (V3.1)
        self._afficher_message("Traduction en cours…", "legende")
        projet = self._services.projets.projet

        def fin(resultat) -> None:
            montrer_occupe(self.bouton_traduire, False)
            self.message.hide()
            self._services.couts.enregistrer(
                FOURNISSEUR,
                MODELE_TRADUCTION,
                "traduction",
                resultat.tokens_entree,
                resultat.tokens_sortie,
                projet=projet.nom if projet is not None else None,
            )
            self.definir(resultat.texte, texte)

        def echec(erreur: Exception) -> None:
            montrer_occupe(self.bouton_traduire, False)
            self._afficher_message(f"Traduction impossible : {message_erreur(erreur)}", "erreur")

        taches.lancer(lambda: traduire_en_anglais(adaptateur, texte), fin, echec)

    def _afficher_message(self, message: str, role: str) -> None:
        afficher_message(self.message, message, role)  # une erreur s'efface après 8 s (V3.2)


class ChampStyle(ChampConsigne):
    """Style d'une réplique ou d'un style enregistré (§5.5)."""

    INDICATION = "Style (facultatif), en anglais. Ex. : warm and enthusiastic, fast-paced"
    AIDE_ASSISTANT = "Écrire le style avec l'assistant : tu choisis en français, l'app écrit la consigne en anglais"
    AIDE_BIBLIOTHEQUE = "Choisir un style dans la bibliothèque"
    TEXTE_A_TRADUIRE = "Écris d'abord le style en français, puis clique ici pour le traduire."

    def __init__(self, services: Services, avec_bibliotheque: bool = True, parent=None):
        super().__init__(services, avec_bibliotheque, parent)

    def _verifications(self, texte: str) -> list[Avertissement]:
        return verifier_style(texte)

    def _dialogue_assistant(self):
        from ..dialogues.assistant_style import DialogueAssistantStyle

        return DialogueAssistantStyle(self.window())


class ChampDescription(ChampConsigne):
    """Description d'une voix à créer (Voice Design, §5.4 bis) : 1 à 2 phrases, en anglais."""

    INDICATION = "Description en anglais, 1 à 2 phrases. Ex. : A young woman in her mid-20s with a warm voice…"
    AIDE_ASSISTANT = (
        "Écrire la description avec l'assistant : tu choisis âge, timbre, accent… en français, "
        "l'app écrit la description en anglais"
    )
    TEXTE_A_TRADUIRE = "Écris d'abord la description en français, puis clique ici pour la traduire."
    PLUSIEURS_LIGNES = True

    def __init__(self, services: Services, parent=None):
        super().__init__(services, avec_bibliotheque=False, parent=parent)

    def _creer_editeur(self) -> QWidget:
        champ = QPlainTextEdit()
        champ.setPlaceholderText(self.INDICATION)
        champ.setFixedHeight(Dimensions.CHAMP_DESCRIPTION_HAUTEUR)
        champ.textChanged.connect(self._texte_change)
        return champ

    def _texte_editeur(self) -> str:
        return self.champ.toPlainText()

    def _ecrire_editeur(self, texte: str) -> None:
        self.champ.setPlainText(texte)

    def _verifications(self, texte: str) -> list[Avertissement]:
        return verifier_description_voix(texte)

    def _dialogue_assistant(self):
        from ..dialogues.assistant_voix import DialogueAssistantVoix

        return DialogueAssistantVoix(self.window())
