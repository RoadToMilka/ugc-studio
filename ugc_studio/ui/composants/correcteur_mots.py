"""Correction des mots d'une transcription (§6.4) : le texte mot par mot, et le mot choisi.

Un clic choisit un mot ; son texte, son début et sa fin se corrigent sans perdre son moment dans
l'audio ; il se fusionne avec le suivant, se coupe en deux ou se supprime. Le même dans le module
Transcription et dans la fenêtre « Corriger les mots » des sous-titres importés (V3.1, lot 6 : avant,
cette partie n'existait que dans le module Transcription).

Le composant corrige la liste de mots qu'on lui donne (afficher), à sa place ; après chaque
correction, il prévient (signal `corrige`, avec le message à afficher) : à la page d'enregistrer,
puis de réafficher.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ...prix import lire_decimal
from ...transcription import Mot, ajuster, corriger, couper, fusionner, supprimer
from ..theme import Dimensions, Espacements
from .editeur_transcription import EditeurTranscription, nom_de_personne
from .elements import bouton, info, libelle


class CorrecteurDeMots(QWidget):
    mot_clique = Signal(int)  # un mot choisi d'un clic : la page peut y placer la lecture
    corrige = Signal(str)  # une correction faite (le message à afficher)
    refuse = Signal(str)  # correction impossible : la raison

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.M)
        self.editeur = EditeurTranscription()
        self.editeur.mot_clique.connect(self.mot_clique.emit)
        # S'il y a de la place en plus (la fenêtre « Corriger les mots »), c'est le texte qui la prend :
        # le panneau du mot choisi reste groupé dessous.
        disposition.addWidget(self.editeur, 1)
        self.panneau = self._panneau()
        disposition.addWidget(self.panneau)
        self._mots: list[Mot] = []
        self._duree: float | None = None
        self.actualiser_le_mot()

    def _panneau(self) -> QFrame:
        """« Mot choisi » : corriger son texte, ses temps ; fusionner, couper, supprimer."""
        panneau = QFrame()
        disposition = QVBoxLayout(panneau)
        disposition.setContentsMargins(0, Espacements.S, 0, 0)
        disposition.setSpacing(Espacements.S)
        self.titre_mot = info("Clique sur un mot pour le corriger.")
        disposition.addWidget(self.titre_mot)
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.champ_mot = QLineEdit()
        self.champ_mot.setPlaceholderText("Texte du mot")
        self.champ_mot.returnPressed.connect(self.appliquer_mot)
        ligne.addWidget(self.champ_mot, 1)
        ligne.addWidget(libelle("Début", "legende", retour_a_la_ligne=False))
        self.champ_debut = QLineEdit()
        self.champ_debut.setFixedWidth(Dimensions.CHAMP_NOMBRE_LARGEUR)
        self.champ_debut.setToolTip("Début du mot, en secondes (ex. 1.25)")
        self.champ_debut.returnPressed.connect(self.appliquer_mot)
        ligne.addWidget(self.champ_debut)
        ligne.addWidget(libelle("Fin", "legende", retour_a_la_ligne=False))
        self.champ_fin = QLineEdit()
        self.champ_fin.setFixedWidth(Dimensions.CHAMP_NOMBRE_LARGEUR)
        self.champ_fin.setToolTip("Fin du mot, en secondes")
        self.champ_fin.returnPressed.connect(self.appliquer_mot)
        ligne.addWidget(self.champ_fin)
        self.bouton_appliquer = bouton("Appliquer", nom_icone="check", action=self.appliquer_mot)
        ligne.addWidget(self.bouton_appliquer)
        disposition.addLayout(ligne)
        actions = QHBoxLayout()
        actions.setSpacing(Espacements.S)
        self.bouton_fusionner = bouton("Fusionner avec le suivant", variante="contour", nom_icone="list-plus", action=self.fusionner_mot)
        actions.addWidget(self.bouton_fusionner)
        self.bouton_couper = bouton("Couper en deux", variante="contour", nom_icone="scissors", action=self.couper_mot)
        actions.addWidget(self.bouton_couper)
        self.bouton_supprimer = bouton("Supprimer", variante="contour", nom_icone="trash", action=self.supprimer_mot)
        actions.addWidget(self.bouton_supprimer)
        actions.addStretch(1)
        disposition.addLayout(actions)
        return panneau

    # --- Mots ----------------------------------------------------------------------------------

    def afficher(self, mots: list[Mot], hesitations: set[str], masquer: bool, duree: float | None = None) -> None:
        """Les mots à corriger (corrigés à leur place) ; `duree` : celle de l'audio, que la fin du
        dernier mot ne dépasse pas."""
        self._mots, self._duree = mots, duree
        self.editeur.afficher(mots, hesitations, masquer)
        self.actualiser_le_mot()

    @property
    def mot_choisi(self) -> int:
        return self.editeur.mot_choisi

    def choisir(self, index: int) -> None:
        self.editeur.choisir(index)
        self.actualiser_le_mot()

    def actualiser_le_mot(self) -> None:
        """Le panneau du mot choisi : ses valeurs, ou l'invitation à cliquer sur un mot."""
        index = self.editeur.mot_choisi
        valide = 0 <= index < len(self._mots)
        for element in (self.champ_mot, self.champ_debut, self.champ_fin, self.bouton_appliquer, self.bouton_couper, self.bouton_supprimer):
            element.setEnabled(valide)
        self.bouton_fusionner.setEnabled(valide and index < len(self._mots) - 1)
        if not valide:
            self.titre_mot.setText("Clique sur un mot pour le corriger (son moment dans l'audio est gardé).")
            for champ in (self.champ_mot, self.champ_debut, self.champ_fin):
                champ.clear()
            return
        mot = self._mots[index]
        personne = f" · {nom_de_personne(mot.locuteur)}" if mot.locuteur else ""
        self.titre_mot.afficher_etat(f"Mot {index + 1} sur {len(self._mots)}{personne}")  # donnée : sans ampoule
        self.champ_mot.setText(mot.texte)
        self.champ_debut.setText(f"{mot.debut:.2f}")
        self.champ_fin.setText(f"{mot.fin:.2f}")

    # --- Corrections (§6.4) ------------------------------------------------------------------------

    def _modifier(self, action, message: str, choisi: int | None = None) -> None:
        """Applique une correction aux mots ; le mot choisi reste celui-là (ou le plus proche)."""
        try:
            action(self._mots)
        except ValueError as erreur:
            self.refuse.emit(str(erreur))
            return
        self.editeur.choisir(-1 if choisi is None else min(choisi, len(self._mots) - 1))
        self.corrige.emit(message)

    def appliquer_mot(self) -> None:
        index = self.editeur.mot_choisi
        if not 0 <= index < len(self._mots):
            return
        try:
            debut = float(lire_decimal(self.champ_debut.text()))
            fin = float(lire_decimal(self.champ_fin.text()))
        except ValueError:
            self.refuse.emit("Début et fin : des secondes, ex. 1.25")
            return

        def action(mots) -> None:
            corriger(mots, index, self.champ_mot.text())
            ajuster(mots, index, debut, fin, self._duree or None)

        self._modifier(action, "Mot corrigé.", index)

    def fusionner_mot(self) -> None:
        index = self.editeur.mot_choisi
        self._modifier(lambda mots: fusionner(mots, index), "Mots fusionnés : corrige le texte si besoin.", index)

    def couper_mot(self) -> None:
        index = self.editeur.mot_choisi
        self._modifier(lambda mots: couper(mots, index), "Mot coupé en deux.", index)

    def supprimer_mot(self) -> None:
        index = self.editeur.mot_choisi
        self._modifier(lambda mots: supprimer(mots, index), "Mot supprimé.", index)
