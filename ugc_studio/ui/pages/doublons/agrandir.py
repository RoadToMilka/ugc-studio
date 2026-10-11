"""La paire en grand (V4.3 : « Agrandir », ou double-clic sur une ligne du tableau des paires).

Deux façons de regarder, au choix : les deux photos côte à côte, ou l'une puis l'autre à la même place
(la barre Espace passe de l'une à l'autre) : c'est la meilleure façon de voir une petite différence.
↑ et ↓ passent à la paire précédente ou suivante, sans fermer la fenêtre. La fenêtre tient sur l'écran
(au plus 80 % de sa largeur et de sa hauteur) ; les photos n'y sont jamais agrandies."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QAbstractButton, QDialog, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from ...composants.choix import ChoixEnBoutons
from ...composants.elements import bouton, libelle, libelle_abrege
from ...composants.fenetre import fenetre_en_bloc
from ...theme import Dimensions, Espacements
from .comparaison import FichePhoto, ImageAjustee, image_pour_l_ecran, texte_des_details

COTE_A_COTE, L_UNE_PUIS_L_AUTRE = "cote_a_cote", "alterner"
FACONS = {COTE_A_COTE: "Côte à côte", L_UNE_PUIS_L_AUTRE: "L'une puis l'autre"}
AIDE_FACON = "L'une puis l'autre : les deux photos à la même place, la barre Espace passe de l'une à l'autre."

# Ce que la page donne pour une paire : ses deux photos et sa description (« 96 % · Même photo · … »).
Paire = tuple[FichePhoto, FichePhoto, str]


class FenetrePaireEnGrand(QDialog):
    rang_change = Signal(int)  # la paire montrée a changé (↑ ↓) : la page choisit la même ligne

    def __init__(self, parent, obtenir: Callable[[int], Paire | None], rang: int, nombre: int, facon: str = COTE_A_COTE):
        super().__init__(parent)
        self._obtenir = obtenir
        self._rang = rang
        self._nombre = nombre
        self._montree = 0  # en « l'une puis l'autre » : 0 la première, 1 la seconde
        self._paire: Paire | None = None
        self._images: list = [None, None]
        fenetre, self.cadre, disposition = fenetre_en_bloc(self)
        disposition.setSpacing(Espacements.M)

        haut = QHBoxLayout()
        haut.setSpacing(Espacements.M)
        textes = QVBoxLayout()
        textes.setSpacing(Espacements.XS)
        self.titre = libelle("", "titre-bloc", retour_a_la_ligne=False)
        textes.addWidget(self.titre)
        self.description = libelle_abrege("", "secondaire")
        textes.addWidget(self.description)
        haut.addLayout(textes, 1)
        self.facon = ChoixEnBoutons(FACONS, info=AIDE_FACON)
        self.facon.definir(facon)
        self.facon.change.connect(lambda _valeur: self._afficher())
        haut.addWidget(self.facon, 0, Qt.AlignmentFlag.AlignTop)
        disposition.addLayout(haut)

        self.pages = QStackedWidget()
        cote_a_cote = QWidget()
        deux = QHBoxLayout(cote_a_cote)
        deux.setContentsMargins(0, 0, 0, 0)
        deux.setSpacing(Espacements.L)
        self.premiere, self.legende_premiere = self._colonne(deux)
        self.seconde, self.legende_seconde = self._colonne(deux)
        self.pages.addWidget(cote_a_cote)
        une = QWidget()
        seule = QHBoxLayout(une)
        seule.setContentsMargins(0, 0, 0, 0)
        self.unique, self.legende_unique = self._colonne(seule)
        self.pages.addWidget(une)
        disposition.addWidget(self.pages, 1)

        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        self.bouton_precedente = bouton("Précédente", nom_icone="chevron-up", action=lambda: self.aller(self._rang - 1))
        boutons.addWidget(self.bouton_precedente)
        self.bouton_suivante = bouton("Suivante", nom_icone="chevron-down", action=lambda: self.aller(self._rang + 1))
        boutons.addWidget(self.bouton_suivante)
        boutons.addStretch(1)
        self.bouton_fermer = bouton("Fermer", variante="principal", action=self.accept)
        boutons.addWidget(self.bouton_fermer)
        fenetre.addLayout(boutons)  # sous le bloc, sur le fond de l'app (V3.2)
        # Les touches (Espace, ↑, ↓) vont à la fenêtre, jamais à un bouton : la barre Espace « cliquerait »
        # sinon le bouton qui a la main (Fermer…). Échap ferme toujours la fenêtre.
        for element in self.findChildren(QAbstractButton):
            element.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()
        self.aller(rang)
        self.resize(*self._place())

    @staticmethod
    def _colonne(disposition):
        colonne = QVBoxLayout()
        colonne.setSpacing(Espacements.XS)
        image = ImageAjustee(None)  # toute la place de la fenêtre
        colonne.addWidget(image, 1)
        legende = libelle_abrege("", "legende")
        colonne.addWidget(legende)
        disposition.addLayout(colonne, 1)
        return image, legende

    def _place(self) -> tuple[int, int]:
        """Largeur et hauteur de l'écran que la fenêtre peut prendre (80 %)."""
        ecran = self.screen() or QGuiApplication.primaryScreen()
        zone = ecran.availableGeometry()
        return int(zone.width() * Dimensions.IMAGE_EN_GRAND_PART_ECRAN), int(zone.height() * Dimensions.IMAGE_EN_GRAND_PART_ECRAN)

    @property
    def rang(self) -> int:
        return self._rang

    def aller(self, rang: int) -> None:
        """Montre la paire de ce rang (0 : la première), si elle existe."""
        if not 0 <= rang < self._nombre:
            return
        paire = self._obtenir(rang)
        if paire is None:
            return
        self._rang, self._paire, self._montree = rang, paire, 0
        premiere, seconde, description = paire
        self.titre.setText(f"Paire {rang + 1} sur {self._nombre}")
        self.description.setText(description)
        self.setWindowTitle(f"{premiere.chemin.name} et {seconde.chemin.name}")
        largeur, hauteur = self._place()
        ratio = self.devicePixelRatioF()
        self._images = []
        for fiche in (premiere, seconde):
            try:
                self._images.append(image_pour_l_ecran(fiche.chemin, round(largeur * ratio), round(hauteur * ratio)))
            except Exception:  # noqa: BLE001 : fichier abîmé ou disparu : la case le dit
                self._images.append(None)
        self.bouton_precedente.setEnabled(rang > 0)
        self.bouton_suivante.setEnabled(rang < self._nombre - 1)
        self._afficher()
        self.rang_change.emit(rang)

    def basculer(self) -> None:
        """La barre Espace : en « l'une puis l'autre », l'autre photo ; côte à côte, passe à « l'une puis l'autre »."""
        if self.facon.valeur() != L_UNE_PUIS_L_AUTRE:
            self.facon.definir(L_UNE_PUIS_L_AUTRE)
            self._montree = 0
        else:
            self._montree = 1 - self._montree
        self._afficher()

    def _afficher(self) -> None:
        if self._paire is None:
            return
        premiere, seconde, _description = self._paire
        fiches = (premiere, seconde)
        if self.facon.valeur() == L_UNE_PUIS_L_AUTRE:
            self.pages.setCurrentIndex(1)
            fiche = fiches[self._montree]
            self.unique.definir(self._images[self._montree], "Aperçu impossible")
            self.legende_unique.setText(f"Image {self._montree + 1} sur 2 : {fiche.chemin.name} · {texte_des_details(fiche)} (Espace : l'autre)")
        else:
            self.pages.setCurrentIndex(0)
            for image, legende, fiche, donnees in ((self.premiere, self.legende_premiere, premiere, self._images[0]), (self.seconde, self.legende_seconde, seconde, self._images[1])):
                image.definir(donnees, "Aperçu impossible")
                legende.setText(f"{fiche.chemin.name} · {texte_des_details(fiche)}")

    def keyPressEvent(self, evenement) -> None:  # noqa: N802 : nom imposé par Qt
        touche = evenement.key()
        if touche == Qt.Key.Key_Space:
            self.basculer()
        elif touche == Qt.Key.Key_Up:
            self.aller(self._rang - 1)
        elif touche == Qt.Key.Key_Down:
            self.aller(self._rang + 1)
        else:
            super().keyPressEvent(evenement)
