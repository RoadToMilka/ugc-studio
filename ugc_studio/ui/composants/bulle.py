"""Bulle d'aide de l'app (V3.2, §9.4 ter) : le texte qui s'affiche au survol d'un bouton, d'un
champ, d'une icône « i », d'un choix de menu…

Pourquoi ne pas garder celle de Qt (QToolTip) ? Ses coins arrondis ne sont pas lissés (Qt découpe sa
fenêtre au pixel près, en escalier) et elle prend le fond des menus. Celle-ci est une petite fenêtre
transparente où l'app dessine elle-même : coins arrondis lissés de 8 px, le fond et le contour fin
des blocs, 16 px autour du texte, qui passe à la ligne tous les 60 caractères environ (comme les
bulles des icônes « i » depuis la V3.1).

Une seule bulle pour toute l'app (bulle()). Elle s'ouvre :
- au survol d'un élément qui a une infobulle (setToolTip, comme avant) : le filtre de l'app (voir
  ui/habillage.py) la montre à la place de celle de Qt, aussi pour les choix des menus et les cases
  des listes et des tableaux ;
- quand un élément le décide lui-même (icône « i » dès le survol, frise, texte abrégé d'une liste…) :
  montrer_bulle() et cacher_bulle(). Ces éléments portent la propriété « bulle_maison » : le filtre
  les laisse faire.
Elle se ferme quand la souris quitte l'élément (ou la zone donnée), au clic, à la molette, à une
touche, ou après un moment (10 s, plus pour un long texte, comme celle de Qt).
"""

from __future__ import annotations

import textwrap

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QApplication,
    QHeaderView,
    QLabel,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from ..theme import Arrondis, Couleurs, Dimensions, Durees, Espacements, qcolor

PROPRIETE_MAISON = "bulle_maison"  # un élément qui montre lui-même sa bulle : le filtre le laisse faire

_FERMENT_LA_BULLE = (
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonDblClick,
    QEvent.Type.Wheel,
    QEvent.Type.KeyPress,
)
_TOUCHES_SANS_EFFET = (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_AltGr)


def texte_en_lignes(texte: str) -> str:
    """Le texte d'une bulle, coupé en lignes d'environ 60 caractères (sans couper un mot, ni après une
    espace insécable) : une longue explication se lit sur quelques lignes plutôt que sur toute la
    largeur de l'écran. Les retours à la ligne voulus (une ligne par état, des paragraphes) sont gardés."""
    return "\n".join(
        textwrap.fill(ligne, Dimensions.BULLE_CARACTERES, break_long_words=False, break_on_hyphens=False)
        for ligne in texte.split("\n")
    )


class Bulle(QWidget):
    """La bulle : une fenêtre sans cadre, transparente autour de ses coins arrondis, qui ne prend ni
    le clavier ni la souris."""

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.L, Espacements.L, Espacements.L, Espacements.L)
        self.etiquette = QLabel()
        self.etiquette.setTextFormat(Qt.TextFormat.PlainText)
        disposition.addWidget(self.etiquette)
        self.auteur: QWidget | None = None  # l'élément survolé
        self.zone: QRect | None = None  # dans l'auteur : la bulle se ferme quand la souris en sort
        self._fin = QTimer(self)
        self._fin.setSingleShot(True)
        self._fin.timeout.connect(self.cacher)

    def texte(self) -> str:
        return self.etiquette.text()

    def montrer(
        self,
        texte: str,
        position: QPoint,
        auteur: QWidget | None = None,
        zone: QRect | None = None,
        sous_le_curseur: bool = True,
    ) -> None:
        """Affiche `texte` (coupé en lignes) à `position` (coordonnées de l'écran) : sous le curseur
        (`sous_le_curseur`), ou exactement là (ex. sous une icône « i »). Toujours dans l'écran."""
        if not texte:
            self.cacher()
            return
        self._suivre(auteur)
        self.zone = zone
        self.etiquette.setText(texte_en_lignes(texte))
        self.adjustSize()
        self.move(self._place(position, sous_le_curseur))
        self.show()
        self.raise_()
        self.update()
        # Comme la bulle de Qt : 10 s, et 40 ms de plus par caractère au-delà de 100.
        surplus = max(0, len(texte) - Durees.BULLE_CARACTERES_SANS_SURPLUS)
        self._fin.start(Durees.BULLE_MS + surplus * Durees.BULLE_MS_PAR_CARACTERE)

    def _suivre(self, auteur: QWidget | None) -> None:
        """Retient l'élément survolé ; s'il disparaît, la bulle se ferme."""
        if auteur is self.auteur:
            return
        if self.auteur is not None:
            try:
                self.auteur.destroyed.disconnect(self._auteur_detruit)
            except (RuntimeError, TypeError):
                pass
        self.auteur = auteur
        if auteur is not None:
            auteur.destroyed.connect(self._auteur_detruit)

    def _auteur_detruit(self, *_arguments) -> None:
        self.auteur = None
        self.cacher()

    def cacher(self, auteur: QWidget | None = None) -> None:
        """Ferme la bulle (seulement si elle est celle de `auteur`, s'il est donné)."""
        if auteur is not None and auteur is not self.auteur:
            return
        self._fin.stop()
        self.hide()

    def _place(self, position: QPoint, sous_le_curseur: bool) -> QPoint:
        """Comme la bulle de Qt : sous le curseur ; au-dessus s'il manque de la place en bas, plus à
        gauche s'il en manque à droite ; toujours dans l'écran."""
        point = QPoint(position)
        if sous_le_curseur:
            point += QPoint(0, Dimensions.BULLE_SOUS_LE_CURSEUR)
        ecran = QApplication.screenAt(position) or QApplication.primaryScreen()
        if ecran is None:
            return point
        zone = ecran.availableGeometry()
        if point.y() + self.height() > zone.bottom():
            point.setY(position.y() - self.height())  # au-dessus de la position, plutôt que par-dessus
        point.setX(max(zone.left(), min(point.x(), zone.right() + 1 - self.width())))
        point.setY(max(zone.top(), min(point.y(), zone.bottom() + 1 - self.height())))
        return point

    def paintEvent(self, _evenement) -> None:  # noqa: N802 — nom imposé par Qt
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        demi = Dimensions.BORDURE / 2
        cadre = QRectF(self.rect()).adjusted(demi, demi, -demi, -demi)
        peintre.setPen(QPen(qcolor(Couleurs.BORDURE), Dimensions.BORDURE))
        peintre.setBrush(qcolor(Couleurs.SURFACE))
        peintre.drawRoundedRect(cadre, Arrondis.CONTROLE, Arrondis.CONTROLE)
        peintre.end()


_bulle: Bulle | None = None


def bulle() -> Bulle:
    """La bulle de l'app (créée au premier besoin)."""
    global _bulle
    if _bulle is None:
        _bulle = Bulle()
    return _bulle


def montrer_bulle(
    texte: str, position: QPoint, auteur: QWidget | None = None, zone: QRect | None = None, sous_le_curseur: bool = True
) -> None:
    """Affiche la bulle de l'app (voir Bulle.montrer) ; un texte vide la ferme."""
    bulle().montrer(texte, position, auteur, zone, sous_le_curseur)


def cacher_bulle(auteur: QWidget | None = None) -> None:
    """Ferme la bulle (seulement celle de `auteur`, s'il est donné)."""
    if _bulle is not None:
        _bulle.cacher(auteur)


def bulle_visible() -> bool:
    return _bulle is not None and _bulle.isVisible()


def texte_de_la_bulle() -> str:
    """Le texte affiché dans la bulle (vide si elle est fermée)."""
    return _bulle.texte() if bulle_visible() else ""


# --- Le filtre de l'app : la bulle à la place de celle de Qt ------------------------------------


def _infobulle(objet: QWidget, position: QPoint) -> tuple[str, QRect | None] | None:
    """Ce que montrerait Qt au survol de `objet` à `position` : (texte, zone où la bulle reste
    ouverte), ou None s'il n'y a rien (l'événement continue alors vers l'élément parent, comme avec Qt)."""
    if isinstance(objet, QMenu):
        action = objet.actionAt(position)
        if action is None or not objet.toolTipsVisible():
            return None
        texte = action.toolTip()
        if not texte or texte == action.text().replace("&", ""):
            return None  # pas d'infobulle propre à ce choix (Qt redonnerait son texte : inutile)
        return texte, objet.actionGeometry(action)
    vue = objet.parentWidget()
    if isinstance(vue, QAbstractItemView) and objet is vue.viewport():
        if isinstance(vue, QHeaderView):
            section = vue.logicalIndexAt(position)
            modele = vue.model()
            if section < 0 or modele is None:
                return None
            texte = modele.headerData(section, vue.orientation(), Qt.ItemDataRole.ToolTipRole)
            debut, taille = vue.sectionViewportPosition(section), vue.sectionSize(section)
            if vue.orientation() == Qt.Orientation.Horizontal:
                zone = QRect(debut, 0, taille, objet.height())
            else:
                zone = QRect(0, debut, objet.width(), taille)
            return (str(texte), zone) if texte else None
        index = vue.indexAt(position)
        texte = index.data(Qt.ItemDataRole.ToolTipRole) if index.isValid() else None
        return (str(texte), vue.visualRect(index)) if texte else None
    texte = objet.toolTip()
    return (texte, None) if texte else None


def _est_maison(objet: QWidget) -> bool:
    """L'élément (ou la zone qui défile dont il est la partie visible : liste, tableau, éditeur) montre
    lui-même sa bulle."""
    if objet.property(PROPRIETE_MAISON):
        return True
    parent = objet.parentWidget()
    return isinstance(parent, QAbstractScrollArea) and objet is parent.viewport() and bool(parent.property(PROPRIETE_MAISON))


def filtrer_pour_les_bulles(objet: QObject, evenement: QEvent) -> bool:
    """Le travail du filtre de l'app (voir ui/habillage.py) pour les bulles : montre la bulle de l'app
    à la place de celle de Qt, et la ferme au bon moment. Renvoie True si l'événement est traité."""
    type_ = evenement.type()
    if type_ == QEvent.Type.ToolTip and isinstance(objet, QWidget):
        if _est_maison(objet):
            return False
        trouve = _infobulle(objet, evenement.pos())
        if trouve is None:
            return False  # rien ici : Qt passe la main à l'élément parent
        texte, zone = trouve
        montrer_bulle(texte, evenement.globalPos(), objet, zone)
        return True
    if _bulle is None or not _bulle.isVisible():
        return False
    if type_ in _FERMENT_LA_BULLE:
        if type_ != QEvent.Type.KeyPress or evenement.key() not in _TOUCHES_SANS_EFFET:
            _bulle.cacher()
    elif objet is _bulle.auteur and isinstance(objet, QWidget):
        if type_ in (QEvent.Type.Leave, QEvent.Type.Hide, QEvent.Type.WindowDeactivate):
            _bulle.cacher()
        elif type_ == QEvent.Type.MouseMove and _bulle.zone is not None:
            if not _bulle.zone.contains(evenement.position().toPoint()):
                _bulle.cacher()
    return False
