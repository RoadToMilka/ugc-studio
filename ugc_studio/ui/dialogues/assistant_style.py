"""Assistant de style structuré (§5.5) : émotion / attitude + rythme, choisis en français.

L'app assemble directement une consigne courte **en anglais** (celle qui est envoyée à Google) et
montre sa traduction française. Aucun appel à l'API : les correspondances sont fixes (styles.py).
"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QGridLayout, QHBoxLayout, QVBoxLayout

from ...styles import EMOTIONS, INTENSITES, RYTHMES, assembler
from ..composants.bouton import activer_avec_entree
from ..composants.elements import bouton, info, libelle, liste_deroulante
from ..theme import Dimensions, Espacements

AUCUN = "Aucun choix"


def _liste(choix: tuple[tuple[str, str], ...], avec_aucun: bool) -> QComboBox:
    liste = liste_deroulante()
    if avec_aucun:
        liste.addItem(AUCUN, "")
    for francais, _anglais in choix:
        liste.addItem(francais, francais)
    return liste


class DialogueAssistantStyle(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assistant de style")
        self.setMinimumWidth(Dimensions.DIALOGUE_LARGEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addWidget(libelle("Assistant de style", "titre-bloc"))
        disposition.addWidget(
            info(
                "Choisis en français : l'app écrit une consigne courte en anglais, comme Google le conseille "
                "(émotion ou attitude, puis rythme).",
                "secondaire",
            )
        )

        grille = QGridLayout()
        grille.setHorizontalSpacing(Espacements.M)
        grille.setVerticalSpacing(Espacements.S)
        self.emotion = _liste(EMOTIONS, avec_aucun=True)
        self.emotion2 = _liste(EMOTIONS, avec_aucun=True)
        self.rythme = _liste(RYTHMES, avec_aucun=True)
        self.intensite = _liste(INTENSITES, avec_aucun=True)
        for rang, (titre, liste) in enumerate(
            (
                ("Émotion ou attitude", self.emotion),
                ("… et (facultatif)", self.emotion2),
                ("Rythme (facultatif)", self.rythme),
                ("Voix (facultatif)", self.intensite),
            )
        ):
            grille.addWidget(libelle(titre, "legende", retour_a_la_ligne=False), rang, 0)
            grille.addWidget(liste, rang, 1)
            liste.currentIndexChanged.connect(self._apercu)
        grille.setColumnStretch(1, 1)
        disposition.addLayout(grille)

        self.anglais = libelle("", "intitule", selectionnable=True)
        self.francais = libelle("", "legende")
        disposition.addWidget(libelle("Consigne envoyée à Google", "legende"))
        disposition.addWidget(self.anglais)
        disposition.addWidget(self.francais)

        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        boutons.addStretch(1)
        boutons.addWidget(bouton("Annuler", action=self.reject))
        self.bouton_utiliser = bouton("Utiliser ce style", variante="principal", nom_icone="check", action=self.accept)
        activer_avec_entree(self.bouton_utiliser, self)
        boutons.addWidget(self.bouton_utiliser)
        disposition.addSpacing(Espacements.S)
        disposition.addLayout(boutons)
        self._apercu()

    def resultat(self) -> tuple[str, str]:
        """(consigne anglaise, traduction française)."""
        return assembler(
            self.emotion.currentData() or "",
            self.emotion2.currentData() or "",
            self.rythme.currentData() or "",
            self.intensite.currentData() or "",
        )

    def _apercu(self, *_args) -> None:
        anglais, francais = self.resultat()
        self.anglais.setText(anglais or "Choisis au moins une émotion ou un rythme.")
        self.francais.setText(f"Traduction : {francais}" if francais else "")
        self.bouton_utiliser.setEnabled(bool(anglais))
