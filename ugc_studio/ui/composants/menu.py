"""Menus de l'app (V3.2, §9.4 quinquies) : comme une liste déroulante ouverte.

Le menu du projet, les menus ⋯, « Couper », « Balise »… et le menu du clic droit dans un champ de
texte : coins arrondis lissés de 8 px, bordure fine grise, fond des listes, choix survolé sur un fond
gris arrondi ; un menu ouvert par un bouton s'ouvre 8 px sous lui (au-dessus s'il manque de la place
en bas), comme une liste. Jusqu'à la 3.1.0 : coins carrés avec une ombre carrée de Windows, collé au
bouton, choix survolé en mauve.

Pourquoi une sorte de menu à part (Menu) plutôt que la feuille de style ? Pour des coins arrondis
lissés, la fenêtre du menu doit être transparente autour d'eux : cela se décide à sa création, avant
qu'elle ne s'affiche. Menu le fait, et dessine lui-même son fond arrondi. Les menus se créent donc
toujours avec Menu (un test le vérifie) ; ceux que Qt crée lui-même (clic droit dans un champ) sont
remplacés par un Menu avec les mêmes choix (voir menu_contextuel_du_champ).
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPen
from PySide6.QtWidgets import QAbstractSpinBox, QLineEdit, QMenu, QPlainTextEdit, QTextEdit, QWidget

from ..theme import Arrondis, Couleurs, Dimensions, qcolor

PROPRIETE = "arrondi"  # les menus de l'app, dessinés ici (la feuille de style leur laisse le fond)


class Menu(QMenu):
    """Menu de l'app : fenêtre transparente autour de ses coins arrondis, sans l'ombre carrée de
    Windows ; le fond et la bordure sont dessinés ici, les choix par Qt (feuille de style)."""

    def __init__(self, parent: QWidget | None = None, titre: str = ""):
        super().__init__(titre, parent)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setProperty(PROPRIETE, True)

    def addMenu(self, *arguments):  # noqa: N802 — même nom que chez Qt
        """Comme QMenu.addMenu, mais un sous-menu créé ici est aussi un Menu de l'app."""
        if len(arguments) == 1 and isinstance(arguments[0], QMenu):
            return super().addMenu(arguments[0])
        icone, titre = (arguments[0], arguments[1]) if isinstance(arguments[0], QIcon) else (None, arguments[0])
        sous_menu = Menu(self, titre)
        if icone is not None:
            sous_menu.setIcon(icone)
        super().addMenu(sous_menu)
        return sous_menu

    def paintEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        demi = Dimensions.BORDURE / 2
        cadre = QRectF(self.rect()).adjusted(demi, demi, -demi, -demi)
        peintre.setPen(QPen(qcolor(Couleurs.BORDURE), Dimensions.BORDURE))
        peintre.setBrush(qcolor(Couleurs.SURFACE_ELEVEE))
        peintre.drawRoundedRect(cadre, Arrondis.CONTROLE, Arrondis.CONTROLE)
        peintre.end()
        super().paintEvent(evenement)  # les choix, par-dessus


def position_du_menu(bouton: QWidget, menu: QMenu) -> QPoint:
    """Où ouvrir le menu d'un bouton (coordonnées de l'écran) : 8 px sous le bouton, aligné sur son
    bord gauche (sur son bord droit s'il dépasserait de l'écran à droite) ; 8 px au-dessus du bouton
    s'il manque de la place en bas, comme une liste déroulante."""
    taille = menu.sizeHint()
    haut_gauche = bouton.mapToGlobal(QPoint(0, 0))
    x = haut_gauche.x()
    y = haut_gauche.y() + bouton.height() + Dimensions.ECART_LISTE
    ecran = bouton.screen().availableGeometry() if bouton.screen() is not None else None
    if ecran is not None:
        if x + taille.width() > ecran.right() + 1:
            x = max(ecran.left(), haut_gauche.x() + bouton.width() - taille.width())
        if y + taille.height() > ecran.bottom() + 1:
            dessus = haut_gauche.y() - Dimensions.ECART_LISTE - taille.height()
            if dessus >= ecran.top():
                y = dessus
    return QPoint(x, y)


def menu_contextuel_du_champ(objet: QWidget, position_globale: QPoint) -> bool:
    """Clic droit dans un champ de texte : le menu standard de Qt (Annuler, Couper, Copier, Coller…),
    mais dans un Menu de l'app. Renvoie False si `objet` n'est pas un champ de texte (Qt fait alors
    comme d'habitude)."""
    champ = objet
    parent = objet.parentWidget()
    if isinstance(parent, (QTextEdit, QPlainTextEdit)) and objet is parent.viewport():
        champ = parent
    if isinstance(champ, QAbstractSpinBox):
        champ = champ.lineEdit()
    if not isinstance(champ, (QLineEdit, QTextEdit, QPlainTextEdit)) or champ.contextMenuPolicy() != Qt.ContextMenuPolicy.DefaultContextMenu:
        return False
    standard = champ.createStandardContextMenu()
    menu = Menu(champ)
    for action in standard.actions():
        menu.addAction(action)
    standard.setParent(menu)  # ses choix restent valables tant que le menu est ouvert
    standard.hide()
    menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    menu.popup(position_globale)
    return True
