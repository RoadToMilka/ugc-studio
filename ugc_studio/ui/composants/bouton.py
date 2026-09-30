"""Bouton de l'app (§9), dessiné « à la main » comme les entrées de la barre latérale.

Pourquoi ne pas utiliser le bouton standard de Qt (QPushButton) ? Il colle l'icône au texte
(environ 4 px) et cet espace ne se règle pas dans la feuille de style. Ici :
- l'icône et le texte sont toujours centrés en hauteur ;
- l'espace entre l'icône et le texte est le même partout dans l'app :
  `Dimensions.ECART_ICONE_TEXTE` (theme.py), comme dans la barre latérale.

Quatre styles, un rôle chacun (§9.4 bis), pour qu'un bouton ressemble toujours à un bouton et
que son importance se lise d'un coup d'œil :
- « principal » : contour mauve, fond mauve léger ; l'action principale d'une zone (une seule) ;
- « normal » (secondaire) : fond gris et bordure fine ; les actions importantes à côté du
  principal, les boutons du bas des fenêtres ;
- « contour » : contour gris bien visible, sans fond (le fond du bloc reste visible) ; les outils
  à l'intérieur d'un bloc (Ajouter une réplique, Accentuer, Actualiser…) ;
- « icone » : petit bouton carré avec une icône seule (⋯, ▶…), fond au survol.
Un bouton « normal » ou « contour » qui peut rester enfoncé (onglet actif, variante écoutée)
prend l'état « sélectionné » : contour mauve et fond mauve très léger, comme le module actif de la
barre latérale. Variante à part : « projet » (nom du projet dans le bandeau, flèche à droite).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QMenu, QSizePolicy, QWidget
from shiboken6 import isValid

from ..icones import icone
from ..polices import police
from ..theme import Arrondis, Couleurs, Dimensions, Espacements, Hauteurs, Opacites, Typo, qcolor

VARIANTES = ("normal", "principal", "contour", "icone", "projet")
_TOUCHES_ENTREE = (Qt.Key.Key_Return, Qt.Key.Key_Enter)


# ---------------------------------------------------------------------------------------------
# Dessin commun : icône + texte (aussi utilisé par la barre latérale)
# ---------------------------------------------------------------------------------------------


def hauteur_majuscules(mesures: QFontMetricsF) -> float:
    """Hauteur d'une majuscule (ex. « H ») dans cette police."""
    return mesures.capHeight() or mesures.tightBoundingRect("H").height()


def ligne_de_base_a_l_oeil(zone: QRectF, mesures: QFontMetricsF, texte: str) -> float:
    """Ligne de base qui centre à l'œil un mot court dans `zone` (noms de balises, « Retenue »…).

    Pourquoi ? Qt centre la « boîte » de la police, qui garde de la place au-dessus des lettres
    pour les majuscules et les accents : un mot en minuscules paraît alors 1 à 2 px trop bas.
    Centrer seulement les minuscules (la hauteur du « x ») ne suffit pas non plus : un mot qui
    commence par une majuscule, comme « Retenue », paraît alors trop haut. L'app vise donc le
    milieu entre le centre de l'encre du mot (du haut de sa lettre la plus haute au bas de sa
    lettre la plus basse) et le centre de ses minuscules."""
    encre = mesures.tightBoundingRect(texte)  # coordonnées depuis la ligne de base (négatif = au-dessus)
    milieu_minuscules = -mesures.xHeight() / 2
    milieu_encre = (encre.top() + encre.bottom()) / 2 if texte and not encre.isEmpty() else milieu_minuscules
    return round(zone.center().y() - (milieu_encre + milieu_minuscules) / 2)


def dessiner_texte_centre_a_l_oeil(
    peintre: QPainter, zone: QRectF, texte: str, police_texte: QFont, couleur: QColor
) -> None:
    """Dessine `texte` centré dans `zone` : au milieu en largeur, centré à l'œil en hauteur
    (voir ligne_de_base_a_l_oeil)."""
    mesures = QFontMetricsF(police_texte)
    x = round(zone.center().x() - mesures.horizontalAdvance(texte) / 2)
    peintre.setFont(police_texte)
    peintre.setPen(couleur)
    peintre.drawText(QPointF(x, ligne_de_base_a_l_oeil(zone, mesures, texte)), texte)


def largeur_icone_et_texte(mesures: QFontMetricsF, texte: str, cote_icone: int) -> float:
    """Largeur occupée par l'icône (0 si aucune), l'écart et le texte."""
    largeur_texte = mesures.horizontalAdvance(texte) if texte else 0.0
    if cote_icone and texte:
        return cote_icone + Dimensions.ECART_ICONE_TEXTE + largeur_texte
    return cote_icone or largeur_texte


def dessiner_icone_et_texte(
    peintre: QPainter,
    zone: QRectF,
    image: QPixmap | None,
    cote_icone: int,
    texte: str,
    police_texte: QFont,
    couleur_texte: QColor,
    centrer: bool = True,
    icone_a_droite: bool = False,
) -> None:
    """Dessine l'icône et le texte dans `zone`, centrés en hauteur, séparés par l'écart du thème.

    Le texte est centré sur la hauteur de ses majuscules (et non sur la boîte de la police, qui
    réserve de la place aux accents et aux jambages) : c'est ce que l'œil perçoit comme centré.
    """
    mesures = QFontMetricsF(police_texte)
    cote = cote_icone if image is not None else 0
    ecart = Dimensions.ECART_ICONE_TEXTE if (cote and texte) else 0
    place_texte = max(0.0, zone.width() - cote - ecart)
    if texte and mesures.horizontalAdvance(texte) > place_texte:
        texte = mesures.elidedText(texte, Qt.TextElideMode.ElideRight, place_texte)
    largeur = largeur_icone_et_texte(mesures, texte, cote)
    x = zone.left() + (zone.width() - largeur) / 2 if centrer else zone.left()
    x = round(x)
    y_icone = round(zone.top() + (zone.height() - cote) / 2)
    ligne_de_base = round(zone.top() + (zone.height() + hauteur_majuscules(mesures)) / 2)

    largeur_texte = mesures.horizontalAdvance(texte) if texte else 0.0
    if icone_a_droite:
        x_texte, x_icone = x, round(x + largeur_texte + ecart)
    else:
        x_icone, x_texte = x, x + cote + ecart
    if image is not None:
        peintre.drawPixmap(QPointF(x_icone, y_icone), image)
    if texte:
        peintre.setFont(police_texte)
        peintre.setPen(couleur_texte)
        peintre.drawText(QPointF(x_texte, ligne_de_base), texte)


# ---------------------------------------------------------------------------------------------
# Bouton
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Apparence:
    fond: QColor | None
    contour: QColor | None
    texte: str  # couleur du texte (theme.Couleurs)


class Bouton(QAbstractButton):
    def __init__(
        self,
        texte: str = "",
        variante: str | None = None,
        nom_icone: str | None = None,
        icone_a_droite: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._variante = variante or "normal"
        if self._variante not in VARIANTES:
            raise ValueError(f"Variante de bouton inconnue : {variante}")
        self._icone_a_droite = icone_a_droite
        self._menu: QMenu | None = None
        self._attenue = False
        self._focus_clavier = False
        self.setText(texte)
        cote = Dimensions.ICONE if self._variante == "icone" else Dimensions.ICONE_PETITE
        self.setIconSize(QSize(cote, cote))
        if nom_icone:
            couleur = Couleurs.TEXTE if self._variante == "principal" else Couleurs.TEXTE_SECONDAIRE
            self.setIcon(icone(nom_icone, couleur, taille=cote))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Le contour de « focus » n'apparaît qu'en naviguant au clavier (touche Tab),
        # pas après un simple clic de souris.
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

    # --- Propriétés --------------------------------------------------------------------------

    @property
    def variante(self) -> str:
        return self._variante

    def definir_attenue(self, attenue: bool) -> None:
        """Texte en gris secondaire (ex. « Aucun projet ouvert » dans le bandeau)."""
        self._attenue = attenue
        self.update()

    def est_attenue(self) -> bool:
        return self._attenue

    # --- Menu (comme QPushButton.setMenu) ----------------------------------------------------

    def setMenu(self, menu: QMenu | None) -> None:  # noqa: N802 — même nom que chez Qt
        if self._menu is None and menu is not None:
            self.pressed.connect(self.showMenu)
        elif self._menu is not None and menu is None:
            self.pressed.disconnect(self.showMenu)
        if menu is not None:
            # Menu ouvert : un clic à côté le ferme seulement (comme sous Windows). Sans cela, un
            # clic sur ce même bouton fermerait le menu… puis le rouvrirait aussitôt.
            menu.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay)
        self._menu = menu

    def menu(self) -> QMenu | None:
        return self._menu

    def showMenu(self) -> None:  # noqa: N802
        """Ouvre le menu sous le bouton ; le bouton reste enfoncé tant que le menu est ouvert."""
        if self._menu is None:
            return
        self.setDown(True)
        self._menu.exec(self.mapToGlobal(QPoint(0, self.height())))
        if isValid(self):  # le bouton a pu disparaître pendant ce temps (ex. prise supprimée)
            self.setDown(False)
            self.update()

    # --- Tailles -----------------------------------------------------------------------------

    def _police(self) -> QFont:
        if self._variante == "projet":
            return police(Typo.TITRE_BLOC, Typo.GRAISSE_FORTE)
        return police(Typo.COURANT, Typo.GRAISSE_MOYENNE)

    def _cote_icone(self) -> int:
        return 0 if self.icon().isNull() else self.iconSize().width()

    def sizeHint(self) -> QSize:
        if self._variante == "icone":
            return QSize(Hauteurs.PETIT_BOUTON, Hauteurs.PETIT_BOUTON)
        mesures = QFontMetricsF(self._police())
        largeur = math.ceil(largeur_icone_et_texte(mesures, self.text(), self._cote_icone()))
        if self._variante == "projet":
            return QSize(largeur, max(math.ceil(mesures.height()), self._cote_icone()))
        return QSize(largeur + 2 * Espacements.L, Hauteurs.CONTROLE)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    # --- Clavier -----------------------------------------------------------------------------

    def focusInEvent(self, evenement) -> None:
        self._focus_clavier = evenement.reason() in (
            Qt.FocusReason.TabFocusReason,
            Qt.FocusReason.BacktabFocusReason,
        )
        super().focusInEvent(evenement)

    def focusOutEvent(self, evenement) -> None:
        self._focus_clavier = False
        super().focusOutEvent(evenement)

    def keyPressEvent(self, evenement) -> None:
        # Bouton sélectionné au clavier : la touche Entrée le déclenche lui (et non le bouton
        # « par défaut » de la fenêtre, voir activer_avec_entree).
        if evenement.key() in _TOUCHES_ENTREE and not evenement.isAutoRepeat():
            if self._menu is not None:
                self.showMenu()
            else:
                self.animateClick()
            return
        super().keyPressEvent(evenement)

    # --- Survol : redessiner quand la souris entre ou sort ----------------------------------

    def enterEvent(self, evenement) -> None:
        self.update()
        super().enterEvent(evenement)

    def leaveEvent(self, evenement) -> None:
        self.update()
        super().leaveEvent(evenement)

    # --- Dessin ------------------------------------------------------------------------------

    def _apparence(self) -> _Apparence:
        actif = self.isEnabled()
        survol = actif and self.underMouse()
        enfonce = actif and self.isDown()
        focus = actif and self.hasFocus() and self._focus_clavier
        variante = self._variante
        if variante in ("normal", "contour") and self.isCheckable() and self.isChecked():
            variante = "selectionne"  # onglet actif, variante écoutée : comme le module actif de la barre latérale

        if variante == "projet":
            if not actif:
                texte = Couleurs.TEXTE_DESACTIVE
            elif survol or enfonce or focus:
                texte = Couleurs.ACCENT_SURVOL
            else:
                texte = Couleurs.TEXTE_SECONDAIRE if self._attenue else Couleurs.TEXTE
            return _Apparence(None, None, texte)

        sans_cadre = variante == "icone"
        if not actif:
            if sans_cadre:
                return _Apparence(None, None, Couleurs.TEXTE_DESACTIVE)
            if variante == "contour":
                return _Apparence(None, qcolor(Couleurs.BORDURE), Couleurs.TEXTE_DESACTIVE)
            return _Apparence(qcolor(Couleurs.SURFACE), qcolor(Couleurs.BORDURE), Couleurs.TEXTE_DESACTIVE)

        if variante == "principal":
            if enfonce:
                fond, contour = qcolor(Couleurs.ACCENT, Opacites.TEINTE_PRESSEE), qcolor(Couleurs.ACCENT_PRESSE)
            elif survol:
                fond, contour = qcolor(Couleurs.ACCENT, Opacites.TEINTE_SURVOL), qcolor(Couleurs.ACCENT_SURVOL)
            else:
                fond, contour = qcolor(Couleurs.ACCENT, Opacites.TEINTE), qcolor(Couleurs.ACCENT)
            texte = Couleurs.TEXTE
        elif variante == "selectionne":
            fond = qcolor(Couleurs.ACCENT, Opacites.TEINTE_SELECTION)
            contour = qcolor(Couleurs.ACCENT_SURVOL if (survol or enfonce) else Couleurs.ACCENT)
            texte = Couleurs.TEXTE
        elif variante == "contour":
            fond = qcolor(Couleurs.FOND) if enfonce else (qcolor(Couleurs.SURFACE_ELEVEE) if survol else None)
            opacite = Opacites.CONTOUR_BOUTON_SURVOL if (survol or enfonce) else Opacites.CONTOUR_BOUTON
            contour = qcolor(Couleurs.TEXTE_SECONDAIRE, opacite)
            texte = Couleurs.TEXTE if (survol or enfonce) else Couleurs.TEXTE_SECONDAIRE
        elif sans_cadre:
            fond = qcolor(Couleurs.FOND) if enfonce else (qcolor(Couleurs.SURFACE_ELEVEE) if survol else None)
            contour = None
            texte = Couleurs.TEXTE if (survol or enfonce) else Couleurs.TEXTE_SECONDAIRE
        else:
            fond = qcolor(Couleurs.FOND if enfonce else Couleurs.SURFACE_ELEVEE)
            contour = qcolor(Couleurs.TEXTE_DESACTIVE if survol else Couleurs.BORDURE)
            texte = Couleurs.TEXTE
        if focus:
            contour = qcolor(Couleurs.ACCENT_SURVOL)
        return _Apparence(fond, contour, texte)

    def _image_icone(self) -> QPixmap | None:
        if self.icon().isNull():
            return None
        mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        etat = QIcon.State.On if self.isChecked() else QIcon.State.Off
        return self.icon().pixmap(self.iconSize(), self.devicePixelRatioF(), mode, etat)

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        apparence = self._apparence()

        if apparence.fond is not None or apparence.contour is not None:
            demi_bordure = Dimensions.BORDURE / 2
            cadre = QRectF(self.rect()).adjusted(demi_bordure, demi_bordure, -demi_bordure, -demi_bordure)
            peintre.setPen(
                QPen(apparence.contour, Dimensions.BORDURE) if apparence.contour is not None else Qt.PenStyle.NoPen
            )
            peintre.setBrush(apparence.fond if apparence.fond is not None else Qt.BrushStyle.NoBrush)
            peintre.drawRoundedRect(cadre, Arrondis.CONTROLE, Arrondis.CONTROLE)

        zone = QRectF(self.rect())
        if self._variante not in ("icone", "projet"):
            zone = zone.adjusted(Espacements.L, 0, -Espacements.L, 0)
        dessiner_icone_et_texte(
            peintre,
            zone,
            self._image_icone(),
            self.iconSize().width(),
            self.text(),
            self._police(),
            qcolor(apparence.texte),
            centrer=self._variante != "projet",
            icone_a_droite=self._icone_a_droite,
        )
        peintre.end()


class _EntreeDeclenche(QObject):
    """Filtre de la fenêtre : la touche Entrée, non utilisée par l'élément actif, déclenche le bouton."""

    def __init__(self, bouton: QAbstractButton, fenetre: QWidget):
        super().__init__(fenetre)
        self._bouton = bouton

    def eventFilter(self, _objet, evenement) -> bool:  # noqa: N802 — nom imposé par Qt
        if evenement.type() == QEvent.Type.KeyPress and evenement.key() in _TOUCHES_ENTREE:
            if self._bouton.isEnabled() and self._bouton.isVisible():
                self._bouton.click()
            return True
        return False


def activer_avec_entree(bouton: QAbstractButton, fenetre: QWidget) -> None:
    """Dans cette fenêtre, la touche Entrée déclenche ce bouton (ex. « Créer le projet »).

    Remplace le « bouton par défaut » des boutons standard de Qt : quand on appuie sur Entrée
    dans un champ de texte, le champ ne s'en sert pas et la touche arrive à la fenêtre, qui
    déclenche ce bouton. Si un autre bouton est sélectionné au clavier, c'est lui qu'Entrée
    déclenche (voir Bouton.keyPressEvent).
    """
    fenetre.installEventFilter(_EntreeDeclenche(bouton, fenetre))
