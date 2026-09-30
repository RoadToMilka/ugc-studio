"""Listes déroulantes « intégrées au champ » (V1.1, §9.4 quinquies) : la liste des choix.

Au clic, la liste s'ouvre collée sous le champ, de la même largeur, par-dessus ce qui est dessous
(sans rien pousser). Le choix actuel reste en haut : c'est le champ lui-même, au contour mauve ; la
liste montre les autres choix, décalés vers la droite, dans leur ordre habituel. Au plus 8 choix
visibles : au-delà, une barre de défilement fine et un fondu en haut et en bas de la liste.

Pourquoi ? Le style de base de Qt (« Fusion ») posait la liste par-dessus le champ et, avec
beaucoup de choix, sur toute la hauteur de l'écran. La propriété « combobox-popup: 0 » de la
feuille de style (theme.py) remet la liste sous le champ ; ce fichier s'occupe du reste. Le champ
lui-même est dans elements.py (ListeDeroulante).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QPen
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QToolTip

from ..theme import Couleurs, Dimensions, Espacements, Hauteurs, qcolor
from .defilement import Fondus

SEPARATEUR = "separator"  # marque des séparations posées par QComboBox.insertSeparator()


def est_separateur(index) -> bool:
    return index.data(Qt.ItemDataRole.AccessibleDescriptionRole) == SEPARATEUR


class DelegueChoix(QStyledItemDelegate):
    """Dessin des choix : hauteur confortable, séparations en fine ligne, texte trop long abrégé
    par « … » (Qt le fait) avec le texte complet au survol (fait ici)."""

    def paint(self, peintre, option, index) -> None:
        if not est_separateur(index):
            super().paint(peintre, option, index)
            return
        milieu = option.rect.center().y()
        peintre.save()
        peintre.setPen(QPen(qcolor(Couleurs.BORDURE), Dimensions.BORDURE))
        peintre.drawLine(option.rect.left() + Espacements.M, milieu, option.rect.right() - Espacements.M, milieu)
        peintre.restore()

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
