"""La paire en grand (V4.3 : « Agrandir », ou double-clic sur une ligne du tableau des paires).

Deux façons de regarder, au choix : les deux photos côte à côte, ou l'une puis l'autre à la même place
(la barre Espace passe de l'une à l'autre) : c'est la meilleure façon de voir une petite différence.
↑ et ↓ passent à la paire précédente ou suivante, sans fermer la fenêtre. La fenêtre tient sur l'écran
(au plus 80 % de sa largeur et de sa hauteur) ; les photos n'y sont jamais agrandies.

V4.5 : on y décide aussi, sans la fermer : « Supprimer » sous chaque photo (en « l'une puis l'autre », celle
qui est montrée), « Ignorer » (ou la touche I), « Annuler ». La page fait le travail (la corbeille, le
tableau) ; la fenêtre suit, sur la paire qui prend la place de celle qui est partie."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QAbstractButton, QDialog, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from ...composants.choix import ChoixEnBoutons
from ...composants.elements import bouton, libelle, libelle_abrege
from ...composants.fenetre import fenetre_en_bloc
from ...theme import Dimensions, Espacements
from .comparaison import FichePhoto, ImageAjustee, bouton_supprimer, image_pour_l_ecran, texte_des_details

COTE_A_COTE, L_UNE_PUIS_L_AUTRE = "cote_a_cote", "alterner"
FACONS = {COTE_A_COTE: "Côte à côte", L_UNE_PUIS_L_AUTRE: "L'une puis l'autre"}
AIDE_FACON = "L'une puis l'autre : les deux photos à la même place, la barre Espace passe de l'une à l'autre."

# Ce que la page donne pour une paire : ses deux photos et sa description (« 96 % · Même photo · … »).
Paire = tuple[FichePhoto, FichePhoto, str]


class FenetrePaireEnGrand(QDialog):
    rang_change = Signal(int)  # la paire montrée a changé (↑ ↓) : la page choisit la même ligne
    supprimer_demande = Signal(int)  # V4.5 : « Supprimer » sous la photo 0 (à gauche) ou 1 (à droite)
    ignorer_demande = Signal()
    annuler_demande = Signal()

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
        self.premiere, self.legende_premiere, supprimer_premiere = self._colonne(deux, lambda: self.supprimer_demande.emit(0))
        self.seconde, self.legende_seconde, supprimer_seconde = self._colonne(deux, lambda: self.supprimer_demande.emit(1))
        self.pages.addWidget(cote_a_cote)
        une = QWidget()
        seule = QHBoxLayout(une)
        seule.setContentsMargins(0, 0, 0, 0)
        self.unique, self.legende_unique, supprimer_unique = self._colonne(seule, lambda: self.supprimer_demande.emit(self._montree))
        self.pages.addWidget(une)
        self.boutons_supprimer = [supprimer_premiere, supprimer_seconde, supprimer_unique]
        disposition.addWidget(self.pages, 1)
        # V4.5 : la dernière décision, et « Annuler » (comme sous la comparaison de la page).
        self.zone_decision = QWidget()
        decision = QHBoxLayout(self.zone_decision)
        decision.setContentsMargins(0, 0, 0, 0)
        decision.setSpacing(Espacements.M)
        self.texte_decision = libelle("", "secondaire")
        decision.addWidget(self.texte_decision, 1)
        self.bouton_annuler = bouton("Annuler", variante="contour", nom_icone="undo-2", action=self.annuler_demande.emit)
        decision.addWidget(self.bouton_annuler, 0, Qt.AlignmentFlag.AlignVCenter)
        self.zone_decision.hide()
        disposition.addWidget(self.zone_decision)

        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        self.bouton_precedente = bouton("Précédente", nom_icone="chevron-up", action=lambda: self.aller(self._rang - 1))
        boutons.addWidget(self.bouton_precedente)
        self.bouton_suivante = bouton("Suivante", nom_icone="chevron-down", action=lambda: self.aller(self._rang + 1))
        boutons.addWidget(self.bouton_suivante)
        self.bouton_ignorer = bouton("Ignorer", nom_icone="eye-off", action=self.ignorer_demande.emit)
        self.bouton_ignorer.setToolTip("Masquer cette paire pour cette analyse (touche I)")
        boutons.addWidget(self.bouton_ignorer)
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
    def _colonne(disposition, supprimer):
        colonne = QVBoxLayout()
        colonne.setSpacing(Espacements.XS)
        image = ImageAjustee(None)  # toute la place de la fenêtre
        colonne.addWidget(image, 1)
        legende = libelle_abrege("", "legende")
        colonne.addWidget(legende)
        colonne.addSpacing(Espacements.XS)
        bouton_de_la_photo = bouton_supprimer(supprimer)
        colonne.addWidget(bouton_de_la_photo, 0, Qt.AlignmentFlag.AlignLeft)
        disposition.addLayout(colonne, 1)
        return image, legende, bouton_de_la_photo

    def _place(self) -> tuple[int, int]:
        """Largeur et hauteur de l'écran que la fenêtre peut prendre (80 %)."""
        ecran = self.screen() or QGuiApplication.primaryScreen()
        zone = ecran.availableGeometry()
        return int(zone.width() * Dimensions.IMAGE_EN_GRAND_PART_ECRAN), int(zone.height() * Dimensions.IMAGE_EN_GRAND_PART_ECRAN)

    @property
    def rang(self) -> int:
        return self._rang

    @property
    def montree(self) -> int:
        """En « l'une puis l'autre » : la photo montrée (0 la première, 1 la seconde)."""
        return self._montree

    def actualiser(self, nombre: int, rang: int) -> None:
        """Les paires ont changé (V4.5 : une photo mise à la corbeille, une paire ignorée, « Annuler ») :
        la fenêtre montre la paire de ce rang, parmi `nombre`."""
        self._nombre = nombre
        self.aller(max(0, min(rang, nombre - 1)))

    def permettre_les_decisions(self, libre: bool, annulable: bool) -> None:
        """Les boutons qui décident, comme ceux de la page (grisés pendant qu'une photo part ou revient)."""
        for supprimer in self.boutons_supprimer:
            supprimer.setEnabled(libre)
        self.bouton_ignorer.setEnabled(libre)
        self.bouton_annuler.setEnabled(annulable)

    def montrer_la_decision(self, texte: str, role: str, annuler: bool) -> None:
        self.texte_decision.setText(texte)
        if self.texte_decision.property("role") != role:
            self.texte_decision.setProperty("role", role)
            self.texte_decision.style().unpolish(self.texte_decision)
            self.texte_decision.style().polish(self.texte_decision)
        self.bouton_annuler.setVisible(annuler)
        self.zone_decision.setVisible(bool(texte))

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
        elif touche == Qt.Key.Key_I and not evenement.modifiers() & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier
        ):
            self.ignorer_demande.emit()
        elif touche == Qt.Key.Key_Up:
            self.aller(self._rang - 1)
        elif touche == Qt.Key.Key_Down:
            self.aller(self._rang + 1)
        else:
            super().keyPressEvent(evenement)
