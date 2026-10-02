"""Fenêtre « Autre couleur » (V3.2, lot 3, §9.6), ouverte depuis un champ de couleur (studio des
sous-titres) : le sélecteur de couleur de Qt (carré des teintes, champs Teinte, Rouge…, couleurs de
base et personnalisées), posé dans le bloc d'une fenêtre de l'app ; « Annuler » et « Choisir cette
couleur » sous le bloc, comme dans les autres fenêtres. Jusqu'à la 3.1.2, c'était la fenêtre toute
faite de Qt, sur fond gris, avec ses propres boutons.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractSpinBox, QColorDialog, QDialog, QHBoxLayout, QLineEdit, QWidget

from ..composants.bouton import activer_avec_entree
from ..composants.elements import bouton, libelle
from ..composants.fenetre import fenetre_en_bloc
from ..theme import Espacements, Hauteurs

TITRE = "Autre couleur"


class _Selecteur(QColorDialog):
    """Le sélecteur de Qt, posé dans la fenêtre (et non dans une fenêtre à part). Échap et Entrée
    concernent la fenêtre « Autre couleur » : sans cela, Échap cacherait le sélecteur seul et
    laisserait un bloc vide."""

    def __init__(self, couleur: QColor):
        super().__init__(couleur)
        self.setOptions(QColorDialog.ColorDialogOption.NoButtons | QColorDialog.ColorDialogOption.DontUseNativeDialog)
        self.layout().setContentsMargins(0, 0, 0, 0)  # les marges sont celles du bloc
        # Ses champs comme ceux de l'app : 32 px de haut, sans les petites flèches (on tape la valeur,
        # ou ↑ ↓ au clavier), comme champ_entier().
        for champ in self.findChildren(QAbstractSpinBox):
            champ.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            champ.setFixedHeight(Hauteurs.CONTROLE)
        for champ in self.findChildren(QLineEdit):
            if not isinstance(champ.parentWidget(), QAbstractSpinBox):  # le code HTML (#f59e0b)
                champ.setFixedHeight(Hauteurs.CONTROLE)

    def keyPressEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        evenement.ignore()  # la touche remonte à la fenêtre « Autre couleur »


class DialogueCouleur(QDialog):
    def __init__(self, couleur: QColor, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(TITRE)
        fenetre, self.cadre, disposition = fenetre_en_bloc(self)
        disposition.setSpacing(Espacements.M)
        disposition.addWidget(libelle(TITRE, "titre-bloc"))
        self.selecteur = _Selecteur(couleur)
        disposition.addWidget(self.selecteur)  # devient un élément de la fenêtre (plus une fenêtre)

        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        boutons.addStretch(1)
        self.bouton_annuler = bouton("Annuler", action=self.reject)
        boutons.addWidget(self.bouton_annuler)
        self.bouton_choisir = bouton("Choisir cette couleur", variante="principal", nom_icone="check", action=self.accept)
        activer_avec_entree(self.bouton_choisir, self)  # Entrée choisit la couleur
        boutons.addWidget(self.bouton_choisir)
        fenetre.addLayout(boutons)  # sous le bloc, sur le fond de l'app (V3.2)

    def couleur(self) -> QColor:
        return self.selecteur.currentColor()


def choisir_couleur(couleur: QColor, parent: QWidget | None = None) -> QColor | None:
    """Ouvre la fenêtre « Autre couleur » : la couleur choisie, ou None si on annule."""
    dialogue = DialogueCouleur(couleur, parent)
    if not dialogue.exec():
        return None
    return dialogue.couleur()
