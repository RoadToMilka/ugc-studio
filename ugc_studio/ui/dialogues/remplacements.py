"""Dictionnaire de remplacements (§6.3) : corrige automatiquement la transcription.

Ex. « sérum anti rides » → « Sérum Anti-Rides® ». Appliqué après chaque transcription (gratuit :
c'est l'app qui remplace), en gardant les temps des mots. Deux dictionnaires : celui du projet et
celui de tous les projets (le projet l'emporte pour une même entrée).
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ...services import Services
from ...transcription import Remplacement, nettoyer_remplacements
from ..composants.bouton import activer_avec_entree
from ..composants.elements import bouton, info, libelle
from ..composants.onglets import Onglets
from ..pages.base import zone_defilante
from ..theme import Dimensions, Espacements


class TableauRemplacements(QWidget):
    """Lignes « transcrit | remplacer par | ✕ », et un bouton pour en ajouter."""

    def __init__(self, entrees: list[Remplacement], parent=None):
        super().__init__(parent)
        self._lignes: list[tuple[QLineEdit, QLineEdit, list[QWidget]]] = []
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, Espacements.M, 0, 0)
        disposition.setSpacing(Espacements.S)
        self._grille = QGridLayout()
        self._grille.setHorizontalSpacing(Espacements.S)
        self._grille.setVerticalSpacing(Espacements.S)
        self._grille.addWidget(libelle("Tel que transcrit (un ou plusieurs mots)", "legende"), 0, 0)
        self._grille.addWidget(libelle("Remplacer par", "legende"), 0, 1)
        self._grille.setColumnStretch(0, 1)
        self._grille.setColumnStretch(1, 1)
        disposition.addLayout(self._grille)
        ajouter = QHBoxLayout()
        ajouter.addWidget(bouton("Ajouter un remplacement", variante="contour", nom_icone="plus", action=self.ajouter))
        ajouter.addStretch(1)
        disposition.addLayout(ajouter)
        disposition.addStretch(1)
        for entree in entrees:
            self.ajouter(entree)
        if not entrees:
            self.ajouter()

    def ajouter(self, entree: Remplacement | None = None) -> None:
        rang = len(self._lignes) + 1
        cherche = QLineEdit(entree.cherche if entree else "")
        cherche.setPlaceholderText("ex. sérum anti rides")
        remplace = QLineEdit(entree.remplace if entree else "")
        remplace.setPlaceholderText("ex. Sérum Anti-Rides®")
        retirer = bouton("", variante="icone", nom_icone="trash")
        retirer.setToolTip("Retirer ce remplacement")
        elements: list[QWidget] = [cherche, remplace, retirer]
        retirer.clicked.connect(lambda: self._retirer(elements))
        for colonne, element in enumerate(elements):
            self._grille.addWidget(element, rang, colonne)
        self._lignes.append((cherche, remplace, elements))
        if entree is None and self.isVisible():
            cherche.setFocus()

    def _retirer(self, elements: list[QWidget]) -> None:
        for element in elements:
            element.hide()
            element.deleteLater()
        self._lignes = [ligne for ligne in self._lignes if ligne[2] is not elements]

    def entrees(self) -> list[Remplacement]:
        return nettoyer_remplacements([Remplacement(c.text(), r.text()) for c, r, _elements in self._lignes])


class DialogueRemplacements(QDialog):
    def __init__(self, services: Services, parent=None):
        super().__init__(parent)
        self._services = services
        self.setWindowTitle("Dictionnaire de remplacements")
        self.setMinimumSize(Dimensions.DIALOGUE_LARGE_LARGEUR, Dimensions.DIALOGUE_LARGE_HAUTEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addWidget(libelle("Dictionnaire de remplacements", "titre-bloc"))
        disposition.addWidget(
            info(
                "Pour les mots que la transcription écrit mal (noms de marque, produits…) : écris-les tels "
                "que transcrits, puis comment ils doivent apparaître. Ils sont remplacés après chaque "
                "transcription, en gardant le moment de chaque mot (gratuit : c'est l'app qui remplace). "
                "Pour une même entrée, le dictionnaire du projet l'emporte.",
                "secondaire",
            )
        )
        self.onglets = Onglets()
        projet = services.projets.projet
        self.projet = TableauRemplacements(list(projet.remplacements) if projet else [])
        self.global_ = TableauRemplacements(list(services.remplacements.entrees))
        for tableau, titre in ((self.projet, "Ce projet"), (self.global_, "Tous les projets")):
            zone, contenu = zone_defilante(largeur_max=None)
            contenu.addWidget(tableau)
            self.onglets.addTab(zone, titre)
        self.onglets.setTabEnabled(0, projet is not None)
        if projet is None:
            self.onglets.setCurrentIndex(1)
        disposition.addWidget(self.onglets, 1)

        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        boutons.addStretch(1)
        boutons.addWidget(bouton("Annuler", action=self.reject))
        self.bouton_enregistrer = bouton("Enregistrer", variante="principal", nom_icone="check", action=self.valider)
        activer_avec_entree(self.bouton_enregistrer, self)
        boutons.addWidget(self.bouton_enregistrer)
        disposition.addLayout(boutons)

    def valider(self) -> None:
        projet = self._services.projets.projet
        if projet is not None:
            projet.remplacements = self.projet.entrees()
            self._services.projets.enregistrer()
        self._services.remplacements.enregistrer(self.global_.entrees())
        self.accept()
