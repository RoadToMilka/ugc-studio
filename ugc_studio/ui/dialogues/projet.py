"""Dialogue « Nouveau projet » (§3.2) : nom, langue (§5.7) et emplacement du dossier."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QLineEdit

from ...chemins import dossier_projets_defaut
from ...projets import LANGUE_PAR_DEFAUT, LANGUES, ErreurProjet, GestionnaireProjets, Projet
from ..composants.bouton import activer_avec_entree
from ..composants.elements import ChampNomme, afficher_message, avec_aide, bouton, libelle, liste_deroulante
from ..composants.fenetre import fenetre_en_bloc
from ..theme import Dimensions, Espacements


class DialogueNouveauProjet(QDialog):
    def __init__(self, projets: GestionnaireProjets, parent=None):
        super().__init__(parent)
        self._projets = projets
        self.projet_cree: Projet | None = None
        self._emplacement = dossier_projets_defaut()
        self.setWindowTitle("Nouveau projet")
        self.setMinimumWidth(Dimensions.DIALOGUE_LARGEUR)

        fenetre, self.cadre, disposition = fenetre_en_bloc(self, titre_avec_boutons=False)
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
        boutons.setSpacing(Espacements.S)  # 8 px entre les boutons, comme dans les autres fenêtres
        boutons.addStretch(1)
        boutons.addWidget(bouton("Annuler", action=self.reject))
        self.bouton_creer = bouton("Créer le projet", variante="principal", nom_icone="folder-plus", action=self.valider)
        activer_avec_entree(self.bouton_creer, self)  # la touche Entrée valide
        boutons.addWidget(self.bouton_creer)
        fenetre.addLayout(boutons)  # sous le bloc, sur le fond de l'app (V3.2)
        self.nom.setFocus()
        # Taille (V3.3) : la hauteur du contenu à la largeur de la fenêtre, le chemin du dossier pouvant
        # passer à la ligne. Jusqu'à la 3.2.2, Qt calculait cette hauteur pour une autre largeur, et le
        # contenu pouvait être serré. La fenêtre n'est pas non plus plus étroite que son contenu (un
        # long chemin d'un seul tenant).
        largeur = max(Dimensions.DIALOGUE_LARGEUR, self.minimumSizeHint().width())
        self.resize(largeur, self.heightForWidth(largeur))

    def event(self, evenement: QEvent) -> bool:
        traite = super().event(evenement)
        if evenement.type() == QEvent.Type.LayoutRequest:
            # Le contenu vient de changer (un autre dossier, un message d'erreur) : s'il lui faut plus de
            # hauteur à cette largeur, la fenêtre grandit pour tout montrer (V3.3).
            hauteur = self.heightForWidth(self.width())
            if hauteur > self.height():
                self.resize(self.width(), hauteur)
        return traite

    def _choisir_dossier(self) -> None:
        choix = QFileDialog.getExistingDirectory(self, "Emplacement des projets", str(self._emplacement))
        if choix:
            self._emplacement = Path(choix)
            self.chemin.setText(choix)

    def valider(self) -> None:
        try:
            self.projet_cree = self._projets.creer(self.nom.text(), self._emplacement, self.langue.currentData())
        except ErreurProjet as erreur:
            afficher_message(self.statut, str(erreur), "erreur")  # effacé après 8 s (V3.2)
            return
        self.accept()
