"""« Corriger les mots » des sous-titres importés (V3.1, lot 6 ; cahier des charges §7.14).

La même correction que dans le module Transcription (composants/correcteur_mots.py : un clic sur un
mot, son texte, son début et sa fin ; fusionner, couper, supprimer), dans une fenêtre, pour des mots
qui ne viennent pas de ce module : une prise de voix (on l'écoute pendant la correction) ou un
fichier SRT (sans son).

Les corrections se font sur une copie des mots : « Enregistrer » les garde, « Annuler » les oublie.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget

from ...transcription import Mot, Transcription, index_au_temps
from ..composants.conseils import entete_de_fenetre
from ..composants.correcteur_mots import CorrecteurDeMots
from ..composants.elements import afficher_message, bouton, glissiere, libelle, minutes_secondes
from ..composants.lecteur import Lecteur
from ..icones import icone
from ..theme import Couleurs, Dimensions, Espacements


class DialogueCorrigerMots(QDialog):
    def __init__(
        self,
        transcription: Transcription,
        description: str,
        audio: Path | None,
        hesitations: set[str],
        parent: QWidget | None = None,
        mot: int = -1,
    ):
        super().__init__(parent)
        self.setWindowTitle("Corriger les mots")
        self.resize(Dimensions.DIALOGUE_LARGE_LARGEUR, Dimensions.DIALOGUE_HAUTEUR_MAX)
        self.mots: list[Mot] = [replace(m) for m in transcription.mots]  # une copie : « Annuler » l'oublie
        self.modifie = False
        self._duree = transcription.duree_s or None
        self._audio = audio if audio is not None and audio.exists() else None
        self.lecteur = Lecteur(self)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addLayout(
            entete_de_fenetre(
                "Corriger les mots",
                "corriger-mots",
                aide=(
                    "Les mots importés dans la page Sous-titres (prise de voix, fichier SRT) : corrige un mot ou "
                    "son moment, comme dans le module Transcription. Les sous-titres suivent."
                ),
            )
        )
        self.description = libelle(description, "secondaire")
        disposition.addWidget(self.description)

        # Lecture (une prise ; un fichier SRT n'a pas de son).
        self.zone_lecture = QWidget()
        lecture = QHBoxLayout(self.zone_lecture)
        lecture.setContentsMargins(0, 0, 0, 0)
        lecture.setSpacing(Espacements.M)
        self.bouton_lecture = bouton("", variante="icone", action=self.basculer_lecture)
        lecture.addWidget(self.bouton_lecture)
        self.position = glissiere()
        self.position.sliderMoved.connect(self.lecteur.aller_a)
        lecture.addWidget(self.position, 1)
        self.temps = libelle("0:00 / 0:00", "legende", retour_a_la_ligne=False)
        lecture.addWidget(self.temps)
        self.zone_lecture.setVisible(self._audio is not None)
        disposition.addWidget(self.zone_lecture)

        self.correcteur = CorrecteurDeMots()
        self.correcteur.mot_clique.connect(self.choisir_mot)
        self.correcteur.corrige.connect(self._corrige)
        self.correcteur.refuse.connect(lambda raison: self._statut(raison, "erreur"))
        self._hesitations, self._masquer = hesitations, transcription.masquer_hesitations
        disposition.addWidget(self.correcteur, 1)
        self.statut = libelle("", "secondaire")
        self.statut.hide()
        disposition.addWidget(self.statut)

        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        boutons.addStretch(1)
        boutons.addWidget(bouton("Annuler", action=self.reject))
        self.bouton_enregistrer = bouton("Enregistrer", variante="principal", nom_icone="check", action=self.accept)
        boutons.addWidget(self.bouton_enregistrer)
        disposition.addLayout(boutons)

        self.lecteur.etat_change.connect(lambda _chemin, _lecture: self._etat_lecture())
        self.lecteur.position_change.connect(self._position_lue)
        self._afficher()
        self._etat_lecture()
        if 0 <= mot < len(self.mots):
            self.choisir_mot(mot)

    def _afficher(self) -> None:
        self.correcteur.afficher(self.mots, self._hesitations, self._masquer, self._duree)

    def _statut(self, message: str, role: str) -> None:
        afficher_message(self.statut, message, role)  # vert ou rouge : effacé après 8 s (V3.2)

    def _corrige(self, message: str) -> None:
        self.modifie = True
        self._statut(message, "succes")
        self._afficher()

    def choisir_mot(self, index: int) -> None:
        """Clic sur un mot : il est choisi ; la lecture se place à ce moment."""
        if not 0 <= index < len(self.mots):
            return
        self.correcteur.choisir(index)
        if self._audio is not None and self.lecteur.chemin == str(self._audio):
            self.lecteur.aller_a(round(self.mots[index].debut * 1000))

    # --- Lecture -----------------------------------------------------------------------------

    def basculer_lecture(self) -> None:
        if self._audio is None:
            return
        if self.lecteur.chemin == str(self._audio):
            self.lecteur.basculer(self._audio)
            return
        choisi = self.correcteur.mot_choisi
        depart = round(self.mots[choisi].debut * 1000) if 0 <= choisi < len(self.mots) else 0
        self.lecteur.jouer_depuis(self._audio, depart)

    def _etat_lecture(self) -> None:
        en_lecture = self._audio is not None and self.lecteur.en_lecture(self._audio)
        self.bouton_lecture.setIcon(icone("pause" if en_lecture else "play", Couleurs.ACCENT_SURVOL, rempli=True))
        self.bouton_lecture.setToolTip("Pause" if en_lecture else "Écouter")

    def _position_lue(self, position_ms: int, duree_ms: int) -> None:
        if not self.position.isSliderDown():
            self.position.setRange(0, max(duree_ms, 0))
            self.position.setValue(position_ms)
        self.temps.setText(f"{minutes_secondes(position_ms / 1000)} / {minutes_secondes(duree_ms / 1000)}")
        self.correcteur.editeur.mettre_en_lecture(index_au_temps(self.mots, position_ms / 1000))

    def done(self, resultat: int) -> None:  # noqa: D401 — nom imposé par Qt
        self.lecteur.arreter()  # libère le fichier de la prise
        super().done(resultat)
