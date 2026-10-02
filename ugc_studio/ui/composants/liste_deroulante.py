"""Listes déroulantes « intégrées au champ » (V1.1, §9.4 quinquies ; revues en V3.1) : la liste des
choix.

Au clic, la liste s'ouvre 8 px sous le champ (au-dessus s'il manque de la place en bas), de la même
largeur, par-dessus ce qui est dessous (sans rien pousser). Coins arrondis et bordure fine grise,
comme les champs et les menus. Tous les choix y sont, à leur place, le choix actuel compris, sur un
fond mauve léger aux coins arrondis ; au survol (ou avec les flèches du clavier), un choix prend le
même fond arrondi, en gris. Le texte des choix commence au même endroit que celui du champ. Au plus
8 choix visibles : au-delà, une barre de défilement fine et un fondu en haut et en bas de la liste.

Jusqu'à la 3.0.0 (décidé en V1.1) : la liste était collée au champ, bordée de mauve, sans le choix
actuel (le champ le montrait), et les autres choix étaient décalés vers la droite.

Pourquoi ? Le style de base de Qt (« Fusion ») posait la liste par-dessus le champ et, avec
beaucoup de choix, sur toute la hauteur de l'écran. La propriété « combobox-popup: 0 » de la
feuille de style (theme.py) remet la liste sous le champ ; ce fichier s'occupe du reste. Le champ
lui-même est dans elements.py (ListeDeroulante).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QComboBox, QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QToolTip, QWidget

from ..theme import LISTES_INTEGREES, Arrondis, Couleurs, Dimensions, Espacements, Hauteurs, Opacites, qcolor
from .defilement import Fondus

SEPARATEUR = "separator"  # marque des séparations posées par QComboBox.insertSeparator()


def est_separateur(index) -> bool:
    return index.data(Qt.ItemDataRole.AccessibleDescriptionRole) == SEPARATEUR


class DelegueChoix(QStyledItemDelegate):
    """Dessin des choix : hauteur confortable, séparations en fine ligne, choix actuel sur un fond
    mauve léger et choix survolé sur un fond gris (coins arrondis), texte trop long abrégé par « … »
    (Qt le fait) avec le texte complet au survol (fait ici)."""

    def paint(self, peintre, option, index) -> None:
        if est_separateur(index):
            milieu = option.rect.center().y()
            peintre.save()
            peintre.setPen(QPen(qcolor(Couleurs.BORDURE), Dimensions.BORDURE))
            peintre.drawLine(option.rect.left() + Espacements.M, milieu, option.rect.right() - Espacements.M, milieu)
            peintre.restore()
            return
        if LISTES_INTEGREES:
            liste = self.parent()
            actuel = isinstance(liste, QComboBox) and index.row() == liste.currentIndex()
            survole = bool(option.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver))
            if actuel or survole:
                if actuel:
                    fond = qcolor(Couleurs.ACCENT, Opacites.TEINTE_SURVOL if survole else Opacites.TEINTE)
                else:
                    fond = qcolor(Couleurs.BORDURE)
                peintre.save()
                peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
                peintre.setPen(Qt.PenStyle.NoPen)
                peintre.setBrush(fond)
                peintre.drawRoundedRect(QRectF(option.rect), Arrondis.PETIT, Arrondis.PETIT)
                peintre.restore()
            # Le texte seulement : les fonds sont dessinés ci-dessus.
            option = QStyleOptionViewItem(option)
            option.state &= ~(QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_HasFocus)
        super().paint(peintre, option, index)

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 — nom imposé par Qt
        if est_separateur(index):
            return QSize(0, Dimensions.SEPARATEUR_LISTE)
        taille = super().sizeHint(option, index)
        return QSize(taille.width(), max(taille.height(), Hauteurs.CHOIX_LISTE))

    def texte_abrege(self, vue, option, index) -> bool:
        """Le texte du choix dépasse-t-il de sa place (il est alors abrégé par « … ») ?"""
        option = QStyleOptionViewItem(option)
        self.initStyleOption(option, index)
        place = vue.style().subElementRect(QStyle.SubElement.SE_ItemViewItemText, option, vue)
        return option.fontMetrics.horizontalAdvance(option.text) > place.width()

    def helpEvent(self, evenement, vue, option, index) -> bool:  # noqa: N802 — nom imposé par Qt
        if evenement.type() != QEvent.Type.ToolTip or not index.isValid() or est_separateur(index):
            return super().helpEvent(evenement, vue, option, index)
        infobulle = index.data(Qt.ItemDataRole.ToolTipRole)
        if self.texte_abrege(vue, option, index):
            infobulle = index.data(Qt.ItemDataRole.DisplayRole)
        if infobulle:
            QToolTip.showText(evenement.globalPos(), str(infobulle), vue)
        else:
            QToolTip.hideText()
        return True


class VueChoix(QListView):
    """Liste des choix, avec un fondu en haut et en bas quand d'autres choix sont cachés."""

    def __init__(self):
        super().__init__()
        self.setTextElideMode(Qt.TextElideMode.ElideRight)  # « Kore · Ferme · fémi… »
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.fondus = Fondus(self, Couleurs.SURFACE_ELEVEE)  # fond de la liste (feuille de style)


class _EcartDuChamp(QObject):
    """Filtre de la fenêtre de la liste : au moment où elle s'ouvre (avant qu'elle ne s'affiche, donc
    sans saut visible), elle s'écarte du champ de 8 px."""

    def __init__(self, champ: QComboBox):
        super().__init__(champ)
        self._champ = champ

    def eventFilter(self, fenetre, evenement) -> bool:  # noqa: N802 — nom imposé par Qt
        if evenement.type() == QEvent.Type.Show:
            ecarter_du_champ(self._champ, fenetre)
        return False


def ecarter_du_champ(champ: QComboBox, fenetre: QWidget) -> None:
    """Pose la liste ouverte `fenetre` 8 px sous le champ, ou 8 px au-dessus si Qt l'a ouverte vers le
    haut (pas assez de place en bas). Qt la colle au champ ; elle reste dans l'écran."""
    cadre = fenetre.geometry()
    haut_du_champ = champ.mapToGlobal(QPoint(0, 0)).y()
    bas_du_champ = haut_du_champ + champ.height()  # première ligne de pixels sous le champ
    ecran = (champ.screen() or fenetre.screen()).availableGeometry()
    if cadre.top() >= bas_du_champ - Dimensions.BORDURE:  # ouverte vers le bas
        cadre.moveTop(bas_du_champ + Dimensions.ECART_LISTE)
        if cadre.bottom() > ecran.bottom():
            cadre.setBottom(ecran.bottom())
    else:  # ouverte vers le haut
        cadre.moveBottom(haut_du_champ - 1 - Dimensions.ECART_LISTE)
        if cadre.top() < ecran.top():
            cadre.setTop(ecran.top())
    fenetre.setGeometry(cadre)


def preparer_la_liste(champ: QComboBox) -> None:
    """La fenêtre de la liste d'un champ : transparente autour de ses coins arrondis (dessinés par la
    feuille de style), sans ombre carrée de Windows, et écartée du champ à l'ouverture."""
    if not LISTES_INTEGREES:
        return
    fenetre = champ.view().window()
    fenetre.setWindowFlags(fenetre.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
    fenetre.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    fenetre.installEventFilter(_EcartDuChamp(champ))
