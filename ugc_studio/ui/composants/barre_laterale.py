"""Barre latérale gauche (§9.6) : le projet ouvert en haut, puis Script, Voix, Transcription,
Sous-titres… et Réglages en bas.

V3.1 : le bouton du projet quitte le bandeau pour le haut de la barre, à la place du logo (le nom de
l'app reste dans la barre de titre de Windows et en bas de la barre, avec la version)."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
)

from ... import NOM_APP, __version__
from ..icones import icone
from ..polices import police
from ..theme import Arrondis, Couleurs, Dimensions, Espacements, Hauteurs, Opacites, Typo, qcolor
from .bouton import Bouton, dessiner_icone_et_texte
from .elements import libelle
from .menu import Menu

TEXTE_SANS_PROJET = "Aucun projet ouvert"
AIDE_PROJET = "Nouveau projet, ouvrir un projet, projets récents…"


@dataclass(frozen=True)
class Module:
    """Un module de l'app, tel qu'il apparaît dans la barre latérale."""

    identifiant: str
    libelle: str
    icone: str  # nom du fichier SVG dans ressources/icones


class BoutonNavigation(QAbstractButton):
    """Entrée de la barre latérale : icône + libellé, contour mauve quand elle est sélectionnée.

    Ce bouton est dessiné « à la main » (méthode paintEvent) pour contrôler exactement
    l'espacement entre l'icône et le texte, que les boutons standard de Qt imposent.
    """

    def __init__(self, module: Module, parent=None):
        super().__init__(parent)
        self.module = module
        self.setText(module.libelle)
        self.setCheckable(True)
        self.setIcon(icone(module.icone, Couleurs.TEXTE_SECONDAIRE, couleur_active=Couleurs.ACCENT_SURVOL))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(Hauteurs.CONTROLE)
        self.setToolTip(module.libelle)
        self._focus_clavier = False

    # Le contour de « focus » ne s'affiche que si l'on arrive sur le bouton avec la touche Tab
    # (navigation au clavier), pas quand la fenêtre s'ouvre ou après un clic.
    def focusInEvent(self, evenement) -> None:
        self._focus_clavier = evenement.reason() in (
            Qt.FocusReason.TabFocusReason,
            Qt.FocusReason.BacktabFocusReason,
        )
        super().focusInEvent(evenement)

    def focusOutEvent(self, evenement) -> None:
        self._focus_clavier = False
        super().focusOutEvent(evenement)

    def sizeHint(self) -> QSize:
        return QSize(Dimensions.LARGEUR_BARRE_LATERALE, Hauteurs.CONTROLE)

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        demi_bordure = Dimensions.BORDURE / 2
        cadre = QRectF(self.rect()).adjusted(demi_bordure, demi_bordure, -demi_bordure, -demi_bordure)

        selectionne = self.isChecked()
        survole = self.underMouse()
        if selectionne:
            fond = qcolor(Couleurs.ACCENT, Opacites.TEINTE_SELECTION)
            contour = qcolor(Couleurs.ACCENT)
        elif survole:
            fond = qcolor(Couleurs.SURFACE_ELEVEE)
            contour = None
        else:
            fond = None
            contour = None
        if self.hasFocus() and self._focus_clavier:
            contour = qcolor(Couleurs.ACCENT_SURVOL)

        if fond is not None or contour is not None:
            peintre.setPen(QPen(contour, Dimensions.BORDURE) if contour is not None else Qt.PenStyle.NoPen)
            peintre.setBrush(fond if fond is not None else Qt.BrushStyle.NoBrush)
            peintre.drawRoundedRect(cadre, Arrondis.CONTROLE, Arrondis.CONTROLE)

        # Icône + libellé : même dessin et même écart que les boutons de l'app (composants/bouton.py).
        cote = Dimensions.ICONE
        etat = QIcon.State.On if selectionne else QIcon.State.Off
        mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        image: QPixmap = self.icon().pixmap(QSize(cote, cote), self.devicePixelRatioF(), mode, etat)
        couleur_texte = Couleurs.TEXTE if (selectionne or survole) else Couleurs.TEXTE_SECONDAIRE
        if not self.isEnabled():
            couleur_texte = Couleurs.TEXTE_DESACTIVE
        dessiner_icone_et_texte(
            peintre,
            QRectF(self.rect()).adjusted(Espacements.M, 0, -Espacements.M, 0),
            image,
            cote,
            self.text(),
            police(Typo.COURANT, Typo.GRAISSE_MOYENNE),
            qcolor(couleur_texte),
            centrer=False,
        )
        peintre.end()

    # Redessiner le bouton quand la souris entre ou sort (effet de survol).
    def enterEvent(self, evenement) -> None:
        self.update()
        super().enterEvent(evenement)

    def leaveEvent(self, evenement) -> None:
        self.update()
        super().leaveEvent(evenement)


class BarreLaterale(QFrame):
    """Barre de navigation. Émet `module_selectionne(identifiant)` quand on clique un module.

    En haut, dans une bande de la hauteur du bandeau (et avec la même ligne dessous) : le bouton du
    projet ouvert, qui ouvre le menu Projet (nouveau, ouvrir, récents…), rempli par la fenêtre."""

    module_selectionne = Signal(str)

    def __init__(self, modules_haut: tuple[Module, ...], modules_bas: tuple[Module, ...], parent=None):
        super().__init__(parent)
        self.setObjectName("barreLaterale")
        self.setFixedWidth(Dimensions.LARGEUR_BARRE_LATERALE)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)

        # Haut : le projet ouvert. Bouton contour, nom à gauche, flèche au bord droit.
        haut = QFrame()
        haut.setObjectName("hautBarreLaterale")
        haut.setFixedHeight(Hauteurs.BANDEAU)
        ligne_projet = QHBoxLayout(haut)
        ligne_projet.setContentsMargins(Espacements.M, 0, Espacements.M, 0)
        self.bouton_projet = Bouton(TEXTE_SANS_PROJET, "projet", "chevron-down")
        self.bouton_projet.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.menu_projet = Menu(self.bouton_projet)
        self.bouton_projet.setMenu(self.menu_projet)
        ligne_projet.addWidget(self.bouton_projet)
        disposition.addWidget(haut)

        # Les modules, puis Réglages et la version en bas.
        navigation = QVBoxLayout()
        navigation.setContentsMargins(Espacements.M, Dimensions.ESPACE_BLOCS, Espacements.M, Espacements.L)
        navigation.setSpacing(Espacements.XS)
        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        self._boutons: dict[str, BoutonNavigation] = {}
        for module in modules_haut:
            navigation.addWidget(self._ajouter(module))
        navigation.addStretch(1)
        for module in modules_bas:
            navigation.addWidget(self._ajouter(module))
        navigation.addSpacing(Espacements.S)
        self.version = libelle(f"{NOM_APP} {__version__}", "discret", retour_a_la_ligne=False)
        self.version.setContentsMargins(Espacements.M, 0, 0, 0)
        navigation.addWidget(self.version)
        disposition.addLayout(navigation, 1)

        self.definir_projet(None)

    def definir_projet(self, nom: str | None) -> None:
        """Nom du projet ouvert (texte grisé « Aucun projet ouvert » sans projet). Au survol : le nom
        complet (utile quand il est abrégé) et ce que propose le menu."""
        self.bouton_projet.setText(nom or TEXTE_SANS_PROJET)
        self.bouton_projet.definir_attenue(not nom)
        self.bouton_projet.setToolTip(f"{nom}\n{AIDE_PROJET}" if nom else AIDE_PROJET)
        self.bouton_projet.update()

    def _ajouter(self, module: Module) -> BoutonNavigation:
        bouton = BoutonNavigation(module)
        bouton.clicked.connect(lambda _coche=False, ident=module.identifiant: self.module_selectionne.emit(ident))
        self._groupe.addButton(bouton)
        self._boutons[module.identifiant] = bouton
        return bouton

    def boutons(self) -> list[BoutonNavigation]:
        return list(self._boutons.values())

    def selectionner(self, identifiant: str) -> None:
        bouton = self._boutons.get(identifiant)
        if bouton is not None and not bouton.isChecked():
            bouton.setChecked(True)
