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
from ..composants.conseils import entete_de_fenetre
from ..composants.elements import bouton, info, noms_de_colonnes
from ..composants.fenetre import fenetre_en_bloc
from ..composants.onglets import Onglets
from ..composants.defilement import zone_defilante
from ..theme import Dimensions, Espacements, Hauteurs


class TableauRemplacements(QWidget):
    """Lignes « transcrit | remplacer par | ✕ », et un bouton pour en ajouter."""

    def __init__(self, entrees: list[Remplacement], parent=None):
        super().__init__(parent)
        self._lignes: list[tuple[QLineEdit, QLineEdit, list[QWidget]]] = []
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, Espacements.M, 0, 0)
        disposition.setSpacing(Espacements.S)
        # Les noms des colonnes au-dessus de la grille des champs : 8 px visibles sous eux (V3.2).
        colonnes = QVBoxLayout()
        colonnes.setSpacing(Dimensions.ECART_NOM_CHAMP)
        colonnes.addLayout(noms_de_colonnes(("Tel que transcrit (un ou plusieurs mots)", "Remplacer par"), Hauteurs.PETIT_BOUTON))
        self._grille = QGridLayout()
        self._grille.setHorizontalSpacing(Espacements.S)
        self._grille.setVerticalSpacing(Espacements.S)
        self._grille.setColumnStretch(0, 1)
        self._grille.setColumnStretch(1, 1)
        colonnes.addLayout(self._grille)
        disposition.addLayout(colonnes)
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
        rang = self._grille.rowCount()  # toujours une nouvelle ligne, à la fin (même après un retrait)
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

        fenetre, self.cadre, disposition = fenetre_en_bloc(self, titre_avec_boutons=True)
        disposition.setSpacing(Espacements.M)
        disposition.addLayout(
            entete_de_fenetre(
                "Dictionnaire de remplacements",
                "remplacements",
                aide=(
                    "Pour les mots que la transcription écrit mal (noms de marque, produits…). Ils sont remplacés "
                    "après chaque transcription, en gardant le moment de chaque mot (gratuit : c'est l'app qui "
                    "remplace). Pour une même entrée, le dictionnaire du projet l'emporte."
                ),
            )
        )
        # Le mode d'emploi du tableau reste écrit (V3.1 : il dit quoi faire).
        disposition.addWidget(info("Écris les mots tels que transcrits, puis comment ils doivent apparaître.", "secondaire"))
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
        fenetre.addLayout(boutons)  # sous le bloc, sur le fond de l'app (V3.2)

    def valider(self) -> None:
        projet = self._services.projets.projet
        if projet is not None:
            projet.remplacements = self.projet.entrees()
            self._services.projets.enregistrer()
        self._services.remplacements.enregistrer(self.global_.entrees())
        self.accept()
