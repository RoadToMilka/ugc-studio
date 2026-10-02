"""Dialogue « Nouveau projet » (§3.2) : nom, langue (§5.7) et emplacement du dossier."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QLineEdit, QVBoxLayout

from ...chemins import dossier_projets_defaut
from ...projets import LANGUE_PAR_DEFAUT, LANGUES, ErreurProjet, GestionnaireProjets, Projet
from ..composants.bouton import activer_avec_entree
from ..composants.elements import ChampNomme, avec_aide, bouton, libelle, liste_deroulante
from ..theme import Dimensions, Espacements


class DialogueNouveauProjet(QDialog):
    def __init__(self, projets: GestionnaireProjets, parent=None):
        super().__init__(parent)
        self._projets = projets
        self.projet_cree: Projet | None = None
        self._emplacement = dossier_projets_defaut()
        self.setWindowTitle("Nouveau projet")
        self.setMinimumWidth(Dimensions.DIALOGUE_LARGEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        # Ce qu'est un projet : au survol de l'icône « i » devant le titre (V3.1 ; après lui jusqu'à la 3.1.0).
        disposition.addLayout(
            avec_aide(
                libelle("Nouveau projet", "titre-bloc", retour_a_la_ligne=False),
                "Un projet regroupe le script, les prises audio et les réglages d'une pub.",
            )
        )

        # Chaque champ sous son nom, 8 px visibles au-dessus (V3.2).
        self.nom = QLineEdit()
        self.nom.setPlaceholderText("ex. « Sérum Glowzy, hook témoignage »")
        disposition.addWidget(ChampNomme("Nom du projet", self.nom, etire=True))

        self.langue = liste_deroulante()
        for code, nom in LANGUES.items():
            self.langue.addItem(nom, code)
        self.langue.setCurrentIndex(self.langue.findData(LANGUE_PAR_DEFAUT))
        disposition.addWidget(ChampNomme("Langue de la voix off", self.langue, etire=True))

        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.chemin = libelle(str(self._emplacement), "secondaire", selectionnable=True)
        ligne.addWidget(self.chemin, 1)
        ligne.addWidget(bouton("Changer…", variante="contour", nom_icone="folder-open", action=self._choisir_dossier))
        disposition.addWidget(ChampNomme("Emplacement", ligne, etire=True))

        self.statut = libelle("", "erreur")
        self.statut.hide()
        disposition.addWidget(self.statut)

        boutons = QHBoxLayout()
        boutons.addStretch(1)
        boutons.addWidget(bouton("Annuler", action=self.reject))
        self.bouton_creer = bouton("Créer le projet", variante="principal", nom_icone="folder-plus", action=self.valider)
        activer_avec_entree(self.bouton_creer, self)  # la touche Entrée valide
        boutons.addWidget(self.bouton_creer)
        disposition.addSpacing(Espacements.S)
        disposition.addLayout(boutons)
        self.nom.setFocus()

    def _choisir_dossier(self) -> None:
        choix = QFileDialog.getExistingDirectory(self, "Emplacement des projets", str(self._emplacement))
        if choix:
            self._emplacement = Path(choix)
            self.chemin.setText(choix)

    def valider(self) -> None:
        try:
            self.projet_cree = self._projets.creer(self.nom.text(), self._emplacement, self.langue.currentData())
        except ErreurProjet as erreur:
            self.statut.setText(str(erreur))
            self.statut.show()
            return
        self.accept()
