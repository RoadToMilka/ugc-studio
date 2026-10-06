"""Grille des vignettes du module Renommer (V4, lot 2) : les images du dossier, dans l'ordre de
l'affichage. Chaque vignette montre en permanence le numéro qu'aura l'image : en mauve si on l'a
cliquée, en gris si elle suit l'ordre de l'affichage, en rouge si son nouveau nom est impossible. Ce
qu'on voit est ce qu'on obtiendra.

Un clic sur une image : elle prend le numéro suivant, ou le perd (`clic`) ; double-clic : l'image en
grand (`double_clic`). Dessinée « à la main » (DelegueVignette), comme les autres listes de l'app.

La grille prend la hauteur de ses rangées, jusqu'à trois rangées et demie, puis défile.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QListView,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
)

from ...polices import police
from ...theme import Arrondis, Couleurs, Dimensions, Espacements, Hauteurs, Typo, qcolor

ROLE_CHEMIN = Qt.ItemDataRole.UserRole + 1  # chemin de l'image (texte)
ROLE_NUMERO = Qt.ItemDataRole.UserRole + 2  # numéro tel qu'il sera écrit (« 01 »)
ROLE_CHOISIE = Qt.ItemDataRole.UserRole + 3  # cliquée : numéro mauve
ROLE_PROBLEME = Qt.ItemDataRole.UserRole + 4  # nouveau nom impossible : numéro rouge
ROLE_VIGNETTE = Qt.ItemDataRole.UserRole + 5  # QPixmap, une fois faite
ROLE_ILLISIBLE = Qt.ItemDataRole.UserRole + 6  # pas de vignette possible (fichier abîmé)

TEXTE_ILLISIBLE = "Aperçu impossible"
AIDE_VIGNETTE = "Clic : lui donner le numéro suivant, ou le lui retirer. Double-clic : la voir en grand."


def qimage_depuis_pillow(image) -> QImage:
    """Une image de Pillow en QImage, copiée (elle ne dépend plus de la mémoire de Pillow). Faite dans le
    fil de travail des vignettes : QImage le permet, au contraire de QPixmap (tâche principale)."""
    rgba = image if image.mode == "RGBA" else image.convert("RGBA")
    donnees = rgba.tobytes("raw", "RGBA")
    return QImage(donnees, rgba.width, rgba.height, rgba.width * len("RGBA"), QImage.Format.Format_RGBA8888).copy()


def _carre(case: QRectF) -> QRectF:
    """Le carré de l'image, en haut de la case, centré."""
    cote = Dimensions.RENOMMER_IMAGE
    return QRectF(case.center().x() - cote / 2, case.top() + Espacements.S, cote, cote)


class DelegueVignette(QStyledItemDelegate):
    """Dessin d'une case : l'image dans son carré (proportions gardées), son numéro en haut à gauche,
    son nom dessous (abrégé au milieu par « … » : le début et l'extension restent lisibles)."""

    def sizeHint(self, _option, _index) -> QSize:  # noqa: N802 : nom imposé par Qt
        return QSize(Dimensions.RENOMMER_CASE_LARGEUR, Dimensions.RENOMMER_CASE_HAUTEUR)

    def paint(self, peintre: QPainter, option, index) -> None:
        peintre.save()
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        peintre.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        case = QRectF(option.rect)
        survol = bool(option.state & QStyle.StateFlag.State_MouseOver)
        choisie = bool(index.data(ROLE_CHOISIE))
        if survol:
            fond = case.adjusted(Espacements.XS / 2, Espacements.XS / 2, -Espacements.XS / 2, -Espacements.XS / 2)
            peintre.setPen(Qt.PenStyle.NoPen)
            peintre.setBrush(qcolor(Couleurs.SURFACE_ELEVEE))
            peintre.drawRoundedRect(fond, Arrondis.CONTROLE, Arrondis.CONTROLE)

        carre = _carre(case)
        image = self._dessiner_l_image(peintre, carre, index)
        if choisie:
            demi = Dimensions.RENOMMER_CONTOUR_CHOISIE / 2
            peintre.setPen(QPen(qcolor(Couleurs.ACCENT), Dimensions.RENOMMER_CONTOUR_CHOISIE))
            peintre.setBrush(Qt.BrushStyle.NoBrush)
            peintre.drawRoundedRect(image.adjusted(-demi, -demi, demi, demi), Arrondis.PETIT, Arrondis.PETIT)
        self._dessiner_le_numero(peintre, image, index, choisie)

        # Le nom, sous le carré.
        nom = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        zone_nom = QRectF(
            case.left() + Espacements.XS,
            carre.bottom() + Espacements.S,
            case.width() - 2 * Espacements.XS,
            Dimensions.RENOMMER_NOM_HAUTEUR,
        )
        ecriture = police(Typo.LEGENDE)
        peintre.setFont(ecriture)
        peintre.setPen(qcolor(Couleurs.TEXTE if (survol or choisie) else Couleurs.TEXTE_SECONDAIRE))
        abrege = QFontMetrics(ecriture).elidedText(nom, Qt.TextElideMode.ElideMiddle, int(zone_nom.width()))
        peintre.drawText(zone_nom, Qt.AlignmentFlag.AlignCenter, abrege)
        peintre.restore()

    @staticmethod
    def _dessiner_l_image(peintre: QPainter, carre: QRectF, index) -> QRectF:
        """L'image centrée dans son carré (ou un carré gris, le temps qu'elle arrive). Renvoie la place
        qu'elle occupe."""
        vignette = index.data(ROLE_VIGNETTE)
        if isinstance(vignette, QPixmap) and not vignette.isNull():
            taille = vignette.deviceIndependentSize()
            place = QRectF(0, 0, min(taille.width(), carre.width()), min(taille.height(), carre.height()))
            place.moveCenter(carre.center())
            peintre.drawPixmap(place, vignette, QRectF(vignette.rect()))
            return place
        peintre.setPen(Qt.PenStyle.NoPen)
        peintre.setBrush(qcolor(Couleurs.SURFACE_ELEVEE))
        peintre.drawRoundedRect(carre, Arrondis.PETIT, Arrondis.PETIT)
        if index.data(ROLE_ILLISIBLE):
            peintre.setFont(police(Typo.LEGENDE))
            peintre.setPen(qcolor(Couleurs.TEXTE_DESACTIVE))
            peintre.drawText(carre, Qt.AlignmentFlag.AlignCenter, TEXTE_ILLISIBLE)
        return carre

    @staticmethod
    def _dessiner_le_numero(peintre: QPainter, image: QRectF, index, choisie: bool) -> None:
        """La pastille du numéro, en haut à gauche de l'image : mauve (cliquée), rouge (nom impossible)
        ou grise (ordre de l'affichage)."""
        numero = str(index.data(ROLE_NUMERO) or "")
        if not numero:
            return
        ecriture = police(Typo.LEGENDE, Typo.GRAISSE_FORTE)
        hauteur = Hauteurs.PASTILLE
        largeur = max(hauteur, QFontMetrics(ecriture).horizontalAdvance(numero) + 2 * Dimensions.BADGE_MARGE_HORIZONTALE)
        pastille = QRectF(image.left() + Espacements.XS, image.top() + Espacements.XS, largeur, hauteur)
        if index.data(ROLE_PROBLEME):
            fond, contour, texte = Couleurs.ERREUR, Couleurs.ERREUR, Couleurs.TEXTE
        elif choisie:
            fond, contour, texte = Couleurs.ACCENT, Couleurs.ACCENT, Couleurs.TEXTE
        else:
            fond, contour, texte = Couleurs.SURFACE_ELEVEE, Couleurs.BORDURE, Couleurs.TEXTE_SECONDAIRE
        peintre.setPen(QPen(qcolor(contour), Dimensions.BORDURE))
        peintre.setBrush(qcolor(fond))
        peintre.drawRoundedRect(pastille, hauteur / 2, hauteur / 2)
        peintre.setFont(ecriture)
        peintre.setPen(qcolor(texte))
        peintre.drawText(pastille, Qt.AlignmentFlag.AlignCenter, numero)


class GrilleVignettes(QListWidget):
    """Les vignettes (voir en haut du fichier). Les cases sont remplies par la page : chemin, nom,
    numéro, cliquée ou non ; les vignettes arrivent ensuite, au fur et à mesure (definir_vignette)."""

    clic = Signal(object)  # chemin de l'image cliquée
    double_clic = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("grilleVignettes")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True)
        self.setGridSize(QSize(Dimensions.RENOMMER_CASE_LARGEUR, Dimensions.RENOMMER_CASE_HAUTEUR))
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        self.setItemDelegate(DelegueVignette(self))
        self._cases: dict[Path, QListWidgetItem] = {}
        self.itemClicked.connect(lambda case: self.clic.emit(Path(case.data(ROLE_CHEMIN))))
        self.itemDoubleClicked.connect(lambda case: self.double_clic.emit(Path(case.data(ROLE_CHEMIN))))
        self._ajuster_la_hauteur()

    # --- Contenu --------------------------------------------------------------------------------

    def remplir(self, chemins: list[Path], vignettes: dict[Path, QPixmap | None]) -> None:
        """Une case par image, dans cet ordre ; les vignettes déjà faites (None : illisible)."""
        self.clear()
        self._cases = {}
        for chemin in chemins:
            case = QListWidgetItem(chemin.name)
            case.setData(ROLE_CHEMIN, str(chemin))
            case.setToolTip(f"{chemin.name}\n{AIDE_VIGNETTE}")
            case.setFlags(Qt.ItemFlag.ItemIsEnabled)
            if chemin in vignettes:
                self._poser(case, vignettes[chemin])
            self.addItem(case)
            self._cases[chemin] = case
        self._ajuster_la_hauteur()

    def definir_numeros(self, numeros: dict[Path, tuple[str, bool, bool]]) -> None:
        """Pour chaque image : (numéro, cliquée, nom impossible)."""
        for chemin, case in self._cases.items():
            numero, choisie, probleme = numeros.get(chemin, ("", False, False))
            case.setData(ROLE_NUMERO, numero)
            case.setData(ROLE_CHOISIE, choisie)
            case.setData(ROLE_PROBLEME, probleme)

    def definir_vignette(self, chemin: Path, vignette: QPixmap | None) -> None:
        case = self._cases.get(chemin)
        if case is not None:
            self._poser(case, vignette)

    @staticmethod
    def _poser(case: QListWidgetItem, vignette: QPixmap | None) -> None:
        case.setData(ROLE_VIGNETTE, vignette)
        case.setData(ROLE_ILLISIBLE, vignette is None)

    def case(self, chemin: Path) -> QListWidgetItem | None:
        return self._cases.get(chemin)

    def chemins(self) -> list[Path]:
        return list(self._cases)

    # --- Hauteur --------------------------------------------------------------------------------

    def par_rangee(self) -> int:
        """Images par rangée, sans barre de défilement, comme Qt les range : une image passe à la rangée
        suivante dès que sa case atteindrait le dernier pixel de la largeur (d'où le « - 1 »)."""
        largeur = self.width() - 2 * self.frameWidth()
        return max(1, (largeur - 1) // Dimensions.RENOMMER_CASE_LARGEUR)

    def _ajuster_la_hauteur(self) -> None:
        """La hauteur de ses rangées, jusqu'à trois rangées et demie (RENOMMER_GRILLE_HAUTEUR_MAX) ; au-delà,
        la grille défile. La barre de défilement n'apparaît que dans ce cas : sinon, en prenant de la
        largeur, elle ferait passer une image à la rangée suivante, puis disparaîtrait, sans fin."""
        rangees = max(1, math.ceil(self.count() / self.par_rangee()))
        hauteur = rangees * Dimensions.RENOMMER_CASE_HAUTEUR
        defile = hauteur > Dimensions.RENOMMER_GRILLE_HAUTEUR_MAX
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if defile else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        hauteur = min(hauteur, Dimensions.RENOMMER_GRILLE_HAUTEUR_MAX)
        if self.minimumHeight() != hauteur or self.maximumHeight() != hauteur:
            self.setFixedHeight(hauteur)

    def resizeEvent(self, evenement) -> None:  # noqa: N802 : nom imposé par Qt
        super().resizeEvent(evenement)
        self._ajuster_la_hauteur()
