"""Barre latérale gauche (§9.6) : Voix, Transcription, Sous-titres… et Réglages en bas."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QPainter, QPen, QPixmap, QTextOption
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

from ... import NOM_APP, __version__
from ...chemins import dossier_ressources
from ..icones import icone
from ..theme import Arrondis, Couleurs, Dimensions, Espacements, Hauteurs, Opacites, qcolor
from .elements import libelle


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
        if self.hasFocus():  # navigation au clavier
            contour = qcolor(Couleurs.ACCENT_SURVOL)

        if fond is not None or contour is not None:
            peintre.setPen(QPen(contour, Dimensions.BORDURE) if contour is not None else Qt.PenStyle.NoPen)
            peintre.setBrush(fond if fond is not None else Qt.BrushStyle.NoBrush)
            peintre.drawRoundedRect(cadre, Arrondis.CONTROLE, Arrondis.CONTROLE)

        # Icône
        cote = Dimensions.ICONE
        x_icone = Espacements.M
        y_icone = (self.height() - cote) // 2
        etat = QIcon.State.On if selectionne else QIcon.State.Off
        mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        image: QPixmap = self.icon().pixmap(QSize(cote, cote), self.devicePixelRatioF(), mode, etat)
        peintre.drawPixmap(x_icone, y_icone, image)

        # Libellé
        police = QFont(self.font())
        police.setWeight(QFont.Weight.Medium)
        peintre.setFont(police)
        couleur_texte = Couleurs.TEXTE if (selectionne or survole) else Couleurs.TEXTE_SECONDAIRE
        if not self.isEnabled():
            couleur_texte = Couleurs.TEXTE_DESACTIVE
        peintre.setPen(qcolor(couleur_texte))
        x_texte = x_icone + cote + Espacements.M
        zone_texte = QRectF(self.rect().adjusted(x_texte, 0, -Espacements.M, 0))
        options = QTextOption(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        options.setWrapMode(QTextOption.WrapMode.NoWrap)
        peintre.drawText(zone_texte, self.text(), options)
        peintre.end()

    # Redessiner le bouton quand la souris entre ou sort (effet de survol).
    def enterEvent(self, evenement) -> None:
        self.update()
        super().enterEvent(evenement)

    def leaveEvent(self, evenement) -> None:
        self.update()
        super().leaveEvent(evenement)


class BarreLaterale(QFrame):
    """Barre de navigation. Émet `module_selectionne(identifiant)` quand on clique un module."""

    module_selectionne = Signal(str)

    def __init__(self, modules_haut: tuple[Module, ...], modules_bas: tuple[Module, ...], parent=None):
        super().__init__(parent)
        self.setObjectName("barreLaterale")
        self.setFixedWidth(Dimensions.LARGEUR_BARRE_LATERALE)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.M, Espacements.L, Espacements.M, Espacements.L)
        disposition.setSpacing(Espacements.XS)

        # Logo + nom de l'app
        ligne_logo = QHBoxLayout()
        ligne_logo.setContentsMargins(Espacements.S, 0, 0, 0)
        ligne_logo.setSpacing(Espacements.S)
        logo = QLabel()
        logo.setPixmap(self._image_logo())
        logo.setFixedSize(Dimensions.LOGO, Dimensions.LOGO)
        ligne_logo.addWidget(logo)
        nom = QLabel(NOM_APP)
        nom.setProperty("role", "nom-app")
        ligne_logo.addWidget(nom)
        ligne_logo.addStretch(1)
        disposition.addLayout(ligne_logo)
        disposition.addSpacing(Espacements.XL)

        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        self._boutons: dict[str, BoutonNavigation] = {}
        for module in modules_haut:
            disposition.addWidget(self._ajouter(module))
        disposition.addStretch(1)
        for module in modules_bas:
            disposition.addWidget(self._ajouter(module))
        disposition.addSpacing(Espacements.S)
        version = libelle(f"Version {__version__}", "discret", retour_a_la_ligne=False)
        version.setContentsMargins(Espacements.M, 0, 0, 0)
        disposition.addWidget(version)

    def _image_logo(self) -> QPixmap:
        echelle = self.devicePixelRatioF()
        cote = round(Dimensions.LOGO * echelle)
        image = QPixmap(str(dossier_ressources() / "app.png")).scaled(
            cote, cote, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        image.setDevicePixelRatio(echelle)
        return image

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
