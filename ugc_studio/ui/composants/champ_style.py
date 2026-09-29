"""Champ « style » d'une réplique ou d'un style enregistré (§5.5).

Le style (consigne de jeu) est **envoyé à Google en anglais** ; sa traduction française s'affiche
juste en dessous, pour comprendre ce qui est envoyé. Trois aides à côté du champ :
- ✨ l'assistant : on choisit en français, l'app assemble la consigne anglaise ;
- 文A « Traduire en anglais » : on écrit en français, un modèle de texte Gemini traduit ;
- 📚 la bibliothèque de styles (facultatif) : réutiliser un style enregistré.
Sous le champ, des vérifications en direct signalent (sans bloquer) ce que Google déconseille.
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ...conseils import verifier_style
from ...services import Services
from ...traduction import MODELE_TRADUCTION, traduire_en_anglais
from .. import taches
from ..connexion_ia import FOURNISSEUR, adaptateur_par_defaut, message_erreur
from ..theme import Espacements
from .elements import bouton, libelle, vider_disposition

INDICATION = "Style (facultatif), en anglais — ex. warm and enthusiastic, fast-paced"


class ChampStyle(QWidget):
    modifie = Signal()  # style ou traduction changés
    bibliotheque_demandee = Signal()
    balise_suggeree = Signal(str)  # « Insérer <laugh> » proposé par les vérifications

    def __init__(self, services: Services, avec_bibliotheque: bool = True, parent=None):
        super().__init__(parent)
        self._services = services
        self._style_fr = ""
        self._programme = False  # vrai pendant un changement fait par l'app (pas par la frappe)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.XS)

        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.XS)
        self.champ = QLineEdit()
        self.champ.setPlaceholderText(INDICATION)
        self.champ.textChanged.connect(self._texte_change)
        ligne.addWidget(self.champ, 1)
        ligne.addSpacing(Espacements.XS)
        self.bouton_assistant = bouton("", variante="icone", nom_icone="wand-sparkles", action=self.ouvrir_assistant)
        self.bouton_assistant.setToolTip("Assistant de style : choisis en français, l'app écrit la consigne en anglais")
        ligne.addWidget(self.bouton_assistant)
        self.bouton_traduire = bouton("", variante="icone", nom_icone="languages", action=self.traduire)
        self.bouton_traduire.setToolTip("Traduire en anglais (modèle de texte Gemini, coût minime)")
        ligne.addWidget(self.bouton_traduire)
        self.bouton_bibliotheque = None
        if avec_bibliotheque:
            self.bouton_bibliotheque = bouton(
                "", variante="icone", nom_icone="library", action=lambda: self.bibliotheque_demandee.emit()
            )
            self.bouton_bibliotheque.setToolTip("Choisir un style dans la bibliothèque")
            ligne.addWidget(self.bouton_bibliotheque)
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

    # --- Valeur ------------------------------------------------------------------------------

    # (Pas de méthode « style() » : ce nom est déjà une fonction de tous les éléments Qt.)
    def consigne(self) -> str:
        """Le style tel qu'envoyé à Google (en anglais)."""
        return self.champ.text().strip()

    def consigne_fr(self) -> str:
        """Sa traduction française (vide si le style a été modifié à la main depuis)."""
        return self._style_fr

    def definir(self, style: str, style_fr: str = "") -> None:
        """Change le style (et sa traduction française) sans passer par la frappe."""
        self._programme = True
        self._style_fr = style_fr.strip()
        self.champ.setText(style)
        self._programme = False
        self._afficher_traduction()
        self._verifier()
        self.modifie.emit()

    def _texte_change(self, _texte: str) -> None:
        if not self._programme:
            # Le style a été modifié à la main : l'ancienne traduction ne lui correspond plus.
            self._style_fr = ""
            self._afficher_traduction()
            self.message.hide()
            self._verifier()
            self.modifie.emit()

    def _afficher_traduction(self) -> None:
        self.traduction.setText(f"Traduction : {self._style_fr}")
        self.traduction.setVisible(bool(self._style_fr and self.consigne()))

    # --- Vérifications en direct ------------------------------------------------------------

    def avertissements(self) -> list[str]:
        return [a.message for a in verifier_style(self.consigne())] if self.consigne() else []

    def _verifier(self) -> None:
        vider_disposition(self._avertissements)
        if not self.consigne():
            return
        for avertissement in verifier_style(self.consigne()):
            texte = html.escape(avertissement.message)
            if avertissement.balise_suggeree:
                nom = avertissement.balise_suggeree
                texte += f' <a href="{html.escape(nom)}">Insérer &lt;{html.escape(nom)}&gt; dans le texte</a>'
            etiquette = QLabel(texte)
            etiquette.setTextFormat(Qt.TextFormat.RichText)
            etiquette.setWordWrap(True)
            etiquette.setProperty("role", "legende-avertissement")
            etiquette.linkActivated.connect(self.balise_suggeree.emit)
            self._avertissements.addWidget(etiquette)

    # --- Assistant et traduction -------------------------------------------------------------

    def ouvrir_assistant(self) -> None:
        from ..dialogues.assistant_style import DialogueAssistantStyle

        dialogue = DialogueAssistantStyle(self.window())
        if dialogue.exec():
            anglais, francais = dialogue.resultat()
            self.definir(anglais, francais)

    def traduire(self) -> None:
        """Traduit le texte du champ (écrit en français) en anglais."""
        texte = self.consigne()
        if not texte:
            self._afficher_message("Écris d'abord le style en français, puis clique ici pour le traduire.", "legende")
            return
        try:
            adaptateur = adaptateur_par_defaut(self._services)
        except Exception as erreur:  # noqa: BLE001 — message clair affiché sous le champ
            self._afficher_message(message_erreur(erreur), "erreur")
            return
        self.bouton_traduire.setEnabled(False)
        self._afficher_message("Traduction en cours…", "legende")
        projet = self._services.projets.projet

        def fin(resultat) -> None:
            self.bouton_traduire.setEnabled(True)
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
            self.bouton_traduire.setEnabled(True)
            self._afficher_message(f"Traduction impossible : {message_erreur(erreur)}", "erreur")

        taches.lancer(lambda: traduire_en_anglais(adaptateur, texte), fin, echec)

    def _afficher_message(self, message: str, role: str) -> None:
        self.message.setText(message)
        self.message.setProperty("role", role)
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.message.show()
