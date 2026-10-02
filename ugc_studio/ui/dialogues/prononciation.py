"""Dictionnaire de prononciation (§5.2) : « mot écrit → façon de le prononcer ».

Pour les mots que la voix prononce mal (noms de marque…). Seul le texte envoyé à la voix est
modifié : le script affiché et les sous-titres gardent la bonne orthographe. Deux dictionnaires :
celui du projet et celui de tous les projets (le projet l'emporte pour un même mot).
Le bouton ▶ fait dire la prononciation par la voix choisie (coût minime, noté dans le suivi).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ...prononciation import Prononciation, nettoyer
from ...services import Services
from ..composants.bouton import Bouton, activer_avec_entree
from ..composants.conseils import entete_de_fenetre
from ..composants.elements import bouton, info, noms_de_colonnes
from ..composants.onglets import Onglets
from ..composants.defilement import zone_defilante
from ..theme import Dimensions, Espacements, Hauteurs


class TableauPrononciations(QWidget):
    """Lignes « mot écrit | se prononce | ▶ | ✕ », et un bouton pour ajouter un mot."""

    def __init__(self, entrees: list[Prononciation], tester: Callable[[str, Bouton], None] | None, parent=None):
        super().__init__(parent)
        self._tester = tester
        self._lignes: list[tuple[QLineEdit, QLineEdit, list[QWidget]]] = []
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, Espacements.M, 0, 0)
        disposition.setSpacing(Espacements.S)
        # Les noms des colonnes au-dessus de la grille des champs : 8 px visibles sous eux (V3.2) ;
        # au bout de chaque ligne, deux petits boutons (▶ et la corbeille).
        colonnes = QVBoxLayout()
        colonnes.setSpacing(Dimensions.ECART_NOM_CHAMP)
        boutons = 2 * Hauteurs.PETIT_BOUTON + Espacements.S
        colonnes.addLayout(noms_de_colonnes(("Mot tel qu'écrit dans le script", "Se prononce"), boutons))
        self._grille = QGridLayout()
        self._grille.setHorizontalSpacing(Espacements.S)
        self._grille.setVerticalSpacing(Espacements.S)
        self._grille.setColumnStretch(0, 1)
        self._grille.setColumnStretch(1, 1)
        colonnes.addLayout(self._grille)
        disposition.addLayout(colonnes)
        ajouter = QHBoxLayout()
        ajouter.addWidget(bouton("Ajouter un mot", variante="contour", nom_icone="plus", action=self.ajouter))
        ajouter.addStretch(1)
        disposition.addLayout(ajouter)
        disposition.addStretch(1)
        for entree in entrees:
            self.ajouter(entree)
        if not entrees:
            self.ajouter()

    def ajouter(self, entree: Prononciation | None = None) -> None:
        rang = self._grille.rowCount()  # toujours une nouvelle ligne, à la fin (même après un retrait)
        mot = QLineEdit(entree.mot if entree else "")
        mot.setPlaceholderText("ex. Glowzy")
        dit = QLineEdit(entree.dit if entree else "")
        dit.setPlaceholderText("ex. Glo-zi")
        ecouter = bouton("", variante="icone", nom_icone="play")
        ecouter.clicked.connect(lambda: self._ecouter(dit, ecouter))
        ecouter.setToolTip("Écouter cette prononciation avec la voix choisie (coût minime)")
        ecouter.setEnabled(self._tester is not None)
        retirer = bouton("", variante="icone", nom_icone="trash")
        retirer.setToolTip("Retirer ce mot")
        elements: list[QWidget] = [mot, dit, ecouter, retirer]
        retirer.clicked.connect(lambda: self._retirer(elements))
        for colonne, element in enumerate(elements):
            self._grille.addWidget(element, rang, colonne)
        self._lignes.append((mot, dit, elements))
        if entree is None and self.isVisible():
            mot.setFocus()

    def _retirer(self, elements: list[QWidget]) -> None:
        for element in elements:
            element.hide()
            element.deleteLater()
        self._lignes = [ligne for ligne in self._lignes if ligne[2] is not elements]

    def _ecouter(self, dit: QLineEdit, ecouter: Bouton) -> None:
        # Le cercle tourne dans ce ▶ pendant que la voix prépare la prononciation (V3.1).
        if self._tester is not None and dit.text().strip():
            self._tester(dit.text().strip(), ecouter)

    def entrees(self) -> list[Prononciation]:
        return nettoyer([Prononciation(mot.text(), dit.text()) for mot, dit, _elements in self._lignes])


class DialoguePrononciation(QDialog):
    """`mots_proposes` : noms repérés sur une page produit (module Script) ; ceux qui ne sont dans
    aucun des deux dictionnaires sont ajoutés à celui du projet, prononciation à écrire (une ligne
    laissée sans prononciation n'est pas enregistrée)."""

    def __init__(
        self,
        services: Services,
        tester: Callable[[str, Bouton], None] | None = None,
        parent=None,
        mots_proposes: list[str] | None = None,
    ):
        super().__init__(parent)
        self._services = services
        self.setWindowTitle("Dictionnaire de prononciation")
        self.setMinimumSize(Dimensions.DIALOGUE_LARGE_LARGEUR, Dimensions.DIALOGUE_LARGE_HAUTEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addLayout(
            entete_de_fenetre(
                "Dictionnaire de prononciation",
                "prononciation",
                aide=(
                    "Pour les mots que la voix prononce mal (noms de marque…). Seul le texte envoyé à la voix "
                    "change : le script et les sous-titres gardent la bonne orthographe. Pour un même mot, le "
                    "dictionnaire du projet l'emporte."
                ),
            )
        )
        # Le mode d'emploi du tableau reste écrit (V3.1 : il dit quoi faire).
        disposition.addWidget(info("Écris le mot comme dans le script, puis comment le dire.", "secondaire"))

        self.onglets = Onglets()
        projet = services.projets.projet
        entrees = list(projet.prononciations) if projet else []
        connus = {e.mot.casefold() for e in [*entrees, *services.prononciations.entrees]}
        nouveaux = []
        for mot in mots_proposes or []:
            mot = " ".join(mot.split())
            if mot and mot.casefold() not in connus:
                connus.add(mot.casefold())
                nouveaux.append(Prononciation(mot, ""))
        self.projet = TableauPrononciations([*entrees, *nouveaux] if projet else entrees, tester)
        self.global_ = TableauPrononciations(list(services.prononciations.entrees), tester)
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
            projet.prononciations = self.projet.entrees()
            self._services.projets.enregistrer()
        self._services.prononciations.enregistrer(self.global_.entrees())
        self.accept()
