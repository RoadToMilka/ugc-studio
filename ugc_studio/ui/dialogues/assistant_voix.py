"""Assistant de description pour Voice Design (§5.4 bis).

On choisit en français les traits permanents de la voix (genre, âge, timbre, texture, accent) et un
rôle ; l'app assemble une description de 1 à 2 phrases **en anglais**, avec sa traduction.
"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QVBoxLayout

from ...voice_design import ACCENTS, AGES, GENRES, PERSONAS, TEXTURES, TIMBRES, assembler_description, code_genre
from ..composants.bouton import activer_avec_entree
from ..composants.conseils import entete_de_fenetre
from ..composants.elements import bouton, champs_en_colonnes, info, libelle, liste_deroulante
from ..theme import Dimensions, Espacements

AUCUN = "Aucun choix"


def _liste(choix: list[str], avec_aucun: bool = True) -> QComboBox:
    liste = liste_deroulante()
    if avec_aucun:
        liste.addItem(AUCUN, "")
    for francais in choix:
        liste.addItem(francais, francais)
    return liste


class DialogueAssistantVoix(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assistant de description")
        self.setMinimumWidth(Dimensions.DIALOGUE_LARGEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addLayout(entete_de_fenetre("Assistant de description", "assistant-description"))
        disposition.addWidget(
            info(
                "Décris les traits permanents de la voix : l'app écrit 1 à 2 phrases en anglais, comme Google "
                "le conseille. L'émotion se règle ensuite avec les styles des répliques.",
                "secondaire",
            )
        )

        self.genre = _liste([ligne[0] for ligne in GENRES], avec_aucun=False)
        self.age = _liste([ligne[0] for ligne in AGES])
        self.timbre = _liste([ligne[0] for ligne in TIMBRES])
        self.texture = _liste([ligne[0] for ligne in TEXTURES])
        self.accent = _liste([ligne[0] for ligne in ACCENTS])
        self.persona = _liste([ligne[0] for ligne in PERSONAS])
        champs = (
            ("Genre", self.genre),
            ("Âge", self.age),
            ("Timbre", self.timbre),
            ("Texture de la voix", self.texture),
            ("Accent", self.accent),
            ("Rôle", self.persona),
        )
        for _titre, liste in champs:
            liste.currentIndexChanged.connect(self._apercu)
        disposition.addLayout(champs_en_colonnes(champs))  # sous leur nom, deux par rangée (V3.1)

        disposition.addWidget(libelle("Description envoyée à Google", "legende"))
        self.anglais = libelle("", "intitule", selectionnable=True)
        self.francais = libelle("", "legende")
        disposition.addWidget(self.anglais)
        disposition.addWidget(self.francais)

        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        boutons.addStretch(1)
        boutons.addWidget(bouton("Annuler", action=self.reject))
        self.bouton_utiliser = bouton(
            "Utiliser cette description", variante="principal", nom_icone="check", action=self.accept
        )
        activer_avec_entree(self.bouton_utiliser, self)
        boutons.addWidget(self.bouton_utiliser)
        disposition.addSpacing(Espacements.S)
        disposition.addLayout(boutons)
        self._apercu()

    def resultat(self) -> tuple[str, str]:
        """(description anglaise, traduction française)."""
        return assembler_description(
            self.genre.currentData() or "",
            self.age.currentData() or "",
            self.timbre.currentData() or "",
            self.texture.currentData() or "",
            self.accent.currentData() or "",
            self.persona.currentData() or "",
        )

    def code_genre(self) -> str:
        """Genre choisi, au format du champ « gender » de Google (« female »…)."""
        return code_genre(self.genre.currentData() or "")

    def _apercu(self, *_args) -> None:
        anglais, francais = self.resultat()
        self.anglais.setText(anglais)
        self.francais.setText(f"Traduction : {francais}")
