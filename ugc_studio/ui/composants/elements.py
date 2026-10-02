"""Petites fonctions pour créer les éléments de base de l'interface avec le bon style.

Le style lui-même est dans theme.py : ici, on se contente d'indiquer le « rôle » de chaque
élément (titre de page, légende, bouton principal…), et la feuille de style fait le reste.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QEvent, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QFontMetricsF, QIcon, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ..icones import icone
from ..polices import police
from ..theme import LISTES_INTEGREES, Couleurs, Dimensions, Espacements, Hauteurs, Opacites, Typo, qcolor
from .bouton import Bouton, dessiner_texte_centre_a_l_oeil
from .liste_deroulante import DelegueChoix, VueChoix


def libelle(
    texte: str,
    role: str | None = None,
    selectionnable: bool = False,
    retour_a_la_ligne: bool = True,
) -> QLabel:
    """Texte. Rôles : « titre-page », « titre-bloc », « secondaire », « legende », « discret »,
    « succes », « avertissement », « erreur ».

    `retour_a_la_ligne=False` pour les textes courts placés sur une ligne avec d'autres éléments
    (titres de bloc à côté d'une pastille…) : ils gardent alors leur largeur naturelle."""
    etiquette = QLabel(texte)
    # Texte brut : sans cela, Qt prendrait « <laugh> » pour une balise HTML et l'effacerait.
    etiquette.setTextFormat(Qt.TextFormat.PlainText)
    if role:
        etiquette.setProperty("role", role)
    etiquette.setWordWrap(retour_a_la_ligne)
    if selectionnable:
        etiquette.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return etiquette


class EtiquetteAbregee(QLabel):
    """Texte sur une seule ligne, abrégé par « … » quand la place manque, texte complet au survol
    (ex. le nom d'un modèle dans Réglages → Modèles et prix, à la plus petite largeur de fenêtre).
    text() renvoie toujours le texte complet ; definir_aide() ajoute une infobulle permanente
    (ex. l'identifiant technique d'un modèle), sous le texte complet quand il est abrégé."""

    def __init__(self, texte: str = "", role: str | None = None):
        super().__init__()
        self.setTextFormat(Qt.TextFormat.PlainText)
        if role:
            self.setProperty("role", role)
        # Peut se resserrer jusqu'à « … » (voir minimumSizeHint) : le texte est alors abrégé.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._complet = texte
        self._aide = ""
        self._mettre_a_jour()

    def definir_aide(self, aide: str) -> None:
        self._aide = aide
        self._mettre_a_jour()

    def text(self) -> str:
        return self._complet

    def est_abrege(self) -> bool:
        """Vrai si le texte affiché est raccourci par « … » (la place manque pour l'écrire en entier)."""
        return QLabel.text(self) != self._complet

    def setText(self, texte: str) -> None:  # noqa: N802 — même nom que chez QLabel
        self._complet = texte
        self._mettre_a_jour()

    def sizeHint(self) -> QSize:  # noqa: N802 — nom imposé par Qt
        taille = super().sizeHint()
        marges = self.contentsMargins()
        largeur = self.fontMetrics().horizontalAdvance(self._complet) + marges.left() + marges.right()
        return QSize(largeur, taille.height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 — nom imposé par Qt
        return QSize(self.fontMetrics().horizontalAdvance("…"), super().minimumSizeHint().height())

    def resizeEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        super().resizeEvent(evenement)
        self._mettre_a_jour()

    def changeEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        super().changeEvent(evenement)
        if evenement.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._mettre_a_jour()  # la feuille de style a changé la taille du texte

    def _mettre_a_jour(self) -> None:
        affiche = self.fontMetrics().elidedText(self._complet, Qt.TextElideMode.ElideRight, self.contentsRect().width())
        if QLabel.text(self) != affiche:
            QLabel.setText(self, affiche)
        infobulle = [self._complet] if affiche != self._complet else []
        if self._aide:
            infobulle.append(self._aide)
        self.setToolTip("\n".join(infobulle))


def libelle_abrege(texte: str, role: str | None = None) -> EtiquetteAbregee:
    """Texte sur une seule ligne, abrégé par « … » s'il manque de place (voir EtiquetteAbregee)."""
    return EtiquetteAbregee(texte, role)


def minutes_secondes(secondes: float) -> str:
    """Durée lisible : 75,4 s → « 1:15 »."""
    secondes = max(0, round(secondes))
    return f"{secondes // 60}:{secondes % 60:02d}"


class Pastille(QLabel):
    """Petite étiquette arrondie (ex. « Retenue », « Par défaut ») : contour mauve, fond mauve
    léger. Dessinée ici plutôt que par la feuille de style, pour centrer le texte à l'œil (voir
    bouton.ligne_de_base_a_l_oeil) : centré par Qt, il paraissait 1 à 2 px trop bas."""

    def __init__(self, texte: str):
        super().__init__(texte)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self._police = police(Typo.LEGENDE, Typo.GRAISSE_MOYENNE)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802 — nom imposé par Qt
        largeur = QFontMetricsF(self._police).horizontalAdvance(self.text())
        return QSize(math.ceil(largeur) + 2 * (Espacements.S + Dimensions.BORDURE), Hauteurs.PASTILLE)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 — nom imposé par Qt
        return self.sizeHint()

    def paintEvent(self, _evenement) -> None:  # noqa: N802 — nom imposé par Qt
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        demi = Dimensions.BORDURE / 2
        zone = QRectF(self.rect()).adjusted(demi, demi, -demi, -demi)
        peintre.setPen(QPen(qcolor(Couleurs.ACCENT), Dimensions.BORDURE))
        peintre.setBrush(qcolor(Couleurs.ACCENT, Opacites.TEINTE_SELECTION))
        peintre.drawRoundedRect(zone, zone.height() / 2, zone.height() / 2)
        couleur = Couleurs.ACCENT_SURVOL if self.isEnabled() else Couleurs.TEXTE_DESACTIVE
        dessiner_texte_centre_a_l_oeil(peintre, QRectF(self.rect()), self.text(), self._police, qcolor(couleur))
        peintre.end()


class Ampoule(QWidget):
    """Petite ampoule dessinée devant une info : l'icône Lucide « lightbulb », à la taille des
    icônes de boutons (donc avec la même épaisseur de trait), dans la couleur du texte secondaire.
    `largeur` : largeur de la colonne où l'ampoule est centrée (par défaut, celle de l'icône)."""

    def __init__(self, largeur: int = Dimensions.ICONE_PETITE):
        super().__init__()
        self._icone = icone("lightbulb", Couleurs.TEXTE_SECONDAIRE, taille=Dimensions.ICONE_PETITE)
        self.setFixedSize(largeur, Dimensions.ICONE_PETITE)

    def paintEvent(self, _evenement) -> None:  # noqa: N802 — nom imposé par Qt
        peintre = QPainter(self)
        mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        cote = Dimensions.ICONE_PETITE
        zone = QRect((self.width() - cote) // 2, 0, cote, cote)  # centrée dans sa colonne
        self._icone.paint(peintre, zone, Qt.AlignmentFlag.AlignCenter, mode)
        peintre.end()


class Info(QWidget):
    """Info placée sous un bloc ou un champ (§9) : une ampoule, puis le texte, qui passe à la ligne.
    Toujours la même ampoule, dans toute l'app : on repère une info d'un coup d'œil.

    `role` : « legende » (petit texte, sous un champ) ou « secondaire » (texte courant gris, pour
    une explication en haut d'un bloc ou d'une fenêtre). `largeur_ampoule` : largeur de la colonne
    de l'ampoule (ex. celle d'une case à cocher, pour aligner le texte sur celui de la case).

    Le même emplacement peut aussi montrer une donnée ou un message d'état (« Mot 3 sur 120 »,
    « Récupération… », une erreur) : afficher_etat() l'écrit alors sans ampoule, car ce n'est pas une
    aide ; setText() remet l'info avec son ampoule."""

    def __init__(self, texte: str = "", role: str = "legende", largeur_ampoule: int = Dimensions.ICONE_PETITE):
        super().__init__()
        self._role = role
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.S)
        self.ampoule = Ampoule(largeur_ampoule)
        self.etiquette = libelle(texte, role)
        # L'ampoule est centrée sur la première ligne du texte (le texte peut en avoir plusieurs).
        taille = Typo.LEGENDE if role == "legende" else Typo.COURANT
        ligne = QFontMetricsF(police(taille)).lineSpacing()
        ecart = round(abs(ligne - Dimensions.ICONE_PETITE) / 2)
        colonne = QVBoxLayout()
        colonne.setContentsMargins(0, ecart if ligne > Dimensions.ICONE_PETITE else 0, 0, 0)
        colonne.addWidget(self.ampoule)
        colonne.addStretch(1)
        self.etiquette.setContentsMargins(0, ecart if ligne < Dimensions.ICONE_PETITE else 0, 0, 0)
        disposition.addLayout(colonne)
        disposition.addWidget(self.etiquette, 1)

    def text(self) -> str:
        return self.etiquette.text()

    def setText(self, texte: str) -> None:  # noqa: N802 — même nom que chez QLabel
        """Affiche une info : avec l'ampoule, dans le style choisi à la création."""
        self._afficher(texte, self._role, avec_ampoule=True)

    def afficher_etat(self, texte: str, erreur: bool = False) -> None:
        """Affiche une donnée ou un message d'état à la place de l'info, sans ampoule.
        `erreur=True` : message d'erreur, en rouge (à la taille de l'info)."""
        role = self._role
        if erreur:
            role = "legende-erreur" if self._role == "legende" else "erreur"
        self._afficher(texte, role, avec_ampoule=False)

    def _afficher(self, texte: str, role: str, avec_ampoule: bool) -> None:
        self.etiquette.setText(texte)
        if self.etiquette.property("role") != role:
            self.etiquette.setProperty("role", role)
            self.etiquette.style().unpolish(self.etiquette)  # applique le nouveau style
            self.etiquette.style().polish(self.etiquette)
        self.ampoule.setVisible(avec_ampoule)


def info(texte: str = "", role: str = "legende") -> Info:
    """Info avec son ampoule (voir Info). Pour toute phrase d'aide sous un bloc ou un champ ; pas
    pour un nom de champ, une donnée (durée, coût…), une traduction ni un message d'état."""
    return Info(texte, role)


def pastille(texte: str) -> Pastille:
    """Petite étiquette arrondie (ex. « Étape 2 »)."""
    return Pastille(texte)


def bouton(
    texte: str,
    variante: str | None = None,
    nom_icone: str | None = None,
    action: Callable[[], None] | None = None,
) -> Bouton:
    """Bouton de l'app (voir composants/bouton.py). Variantes : « principal » (l'action principale
    d'une zone), None (normal, dit secondaire), « contour » (outils dans un bloc), « icone » (petit
    bouton carré, icône seule)."""
    resultat = Bouton(texte, variante, nom_icone)
    if action is not None:
        resultat.clicked.connect(action)
    return resultat


class _SansMolette:
    """Un champ ne change pas quand la molette de la souris passe dessus en faisant défiler la
    page (ex. le choix du modèle, ou le moment de lecture) : il faut d'abord cliquer dedans."""

    def wheelEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        if self.hasFocus():
            super().wheelEvent(evenement)
        else:
            evenement.ignore()  # la page défile normalement


class ListeDeroulante(_SansMolette, QComboBox):
    """Liste déroulante de l'app (voir liste_deroulante()).

    - Liste « intégrée au champ » (§9.4 quinquies) : elle s'ouvre sous le champ, sans le choix
      actuel, que le champ montre déjà (voir composants/liste_deroulante.py).
    - Texte trop long pour le champ fermé : abrégé par « … » (Qt le coupait au milieu d'une lettre),
      avec le texte complet au survol."""

    def __init__(self):
        super().__init__()
        self.setView(VueChoix())
        self.setItemDelegate(DelegueChoix(self))
        self.setMaxVisibleItems(Dimensions.LISTE_CHOIX_VISIBLES)

    # --- Liste ouverte ---------------------------------------------------------------------------

    def showPopup(self) -> None:  # noqa: N802 — nom imposé par Qt
        vue, actuel = self.view(), self.currentIndex()
        for rang in range(self.count()):
            vue.setRowHidden(rang, LISTES_INTEGREES and rang == actuel)  # le champ le montre déjà
        super().showPopup()

    def hidePopup(self) -> None:  # noqa: N802 — nom imposé par Qt
        super().hidePopup()
        for rang in range(self.count()):
            self.view().setRowHidden(rang, False)

    # --- Champ fermé : texte abrégé par « … » ----------------------------------------------------

    def _option(self) -> QStyleOptionComboBox:
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        return option

    def _place_du_texte(self, option: QStyleOptionComboBox) -> int:
        zone = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxEditField, self
        )
        largeur = zone.width()
        if not option.currentIcon.isNull():
            largeur -= option.iconSize.width() + Espacements.XS
        return largeur

    def texte_affiche(self) -> str:
        """Le texte tel qu'il s'affiche dans le champ fermé (abrégé par « … » s'il est trop long)."""
        option = self._option()
        return self.fontMetrics().elidedText(option.currentText, Qt.TextElideMode.ElideRight, self._place_du_texte(option))

    def paintEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        if self.isEditable():  # le texte est alors dans un champ de saisie, qui se dessine seul
            super().paintEvent(evenement)
            return
        # Comme QComboBox.paintEvent(), mais avec le texte abrégé.
        peintre = QStylePainter(self)
        peintre.setPen(self.palette().color(QPalette.ColorRole.Text))
        option = self._option()
        peintre.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        if self.currentIndex() < 0 and self.placeholderText():
            option.palette.setBrush(QPalette.ColorRole.ButtonText, option.palette.placeholderText())
            option.currentText = self.placeholderText()
        else:
            option.currentText = self.texte_affiche()
        peintre.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)

    def event(self, evenement) -> bool:
        if evenement.type() == QEvent.Type.ToolTip and not self.isEditable():
            texte = self.currentText()
            if texte and self.texte_affiche() != texte:
                aide = self.toolTip()
                QToolTip.showText(evenement.globalPos(), f"{texte}\n{aide}" if aide else texte, self)
                return True
        return super().event(evenement)


class Glissiere(_SansMolette, QSlider):
    pass


class ChampEntier(_SansMolette, QSpinBox):
    pass


class ChampDecimal(_SansMolette, QDoubleSpinBox):
    pass


def liste_deroulante(info: str | None = None) -> QComboBox:
    """Liste déroulante de l'app (toujours créée ici, jamais avec QComboBox() directement).

    Elle prend la largeur de son plus long choix quand il y a de la place, et peut rétrécir sinon
    (texte abrégé par « … », texte complet au survol). Sans cela, un choix très long (ex. le nom
    d'une voix créée) élargirait toute la page au-delà de la fenêtre, et le bord droit serait
    coupé. La liste s'ouvre sous le champ (voir ListeDeroulante). La molette ne la change qu'après
    un clic dedans (voir _SansMolette). `info` : texte de l'infobulle."""
    liste = ListeDeroulante()
    liste.setMinimumContentsLength(Dimensions.LISTE_CARACTERES_MIN)
    liste.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    if info:
        liste.setToolTip(info)
    return liste


def glissiere() -> QSlider:
    """Barre de position horizontale (lecture d'un audio). La molette ne la déplace qu'après un
    clic dedans : sinon, elle bloquerait le défilement de la page quand la souris passe dessus."""
    barre = Glissiere(Qt.Orientation.Horizontal)
    barre.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return barre


def case_a_cocher(texte: str, explication: str | None = None) -> tuple[QWidget, QCheckBox]:
    """Case à cocher au texte court, avec son explication dessous : une info (ampoule sous la case,
    texte aligné sur celui de la case). Renvoie la zone à placer dans la page et la case elle-même ;
    pour griser la case, griser la zone (l'explication l'est alors aussi).

    Pourquoi ? Le texte d'une case à cocher ne passe jamais à la ligne : une longue phrase
    imposerait sa largeur à toute la page, qui déborderait à droite dans une fenêtre étroite.
    L'explication, elle, passe à la ligne. (Un test vérifie que le texte des cases reste court.)"""
    zone = QWidget()
    disposition = QVBoxLayout(zone)
    disposition.setContentsMargins(0, 0, 0, 0)
    disposition.setSpacing(Espacements.XS)
    case = QCheckBox(texte)
    disposition.addWidget(case)
    if explication:
        # La colonne de l'ampoule a la largeur de la case (18 px plus sa bordure de chaque côté,
        # voir QCheckBox dans la feuille de style) : l'ampoule est centrée sous la case, et le
        # texte commence au même endroit que celui de la case (même espace de 8 px avant).
        largeur_case = Dimensions.CASE_A_COCHER + 2 * Dimensions.BORDURE
        disposition.addWidget(Info(explication, largeur_ampoule=largeur_case))
    return zone, case


def _preparer_champ(champ: QAbstractSpinBox, suffixe: str, info: str | None) -> None:
    champ.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)  # on tape la valeur (ou ↑ ↓)
    champ.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    champ.setFixedWidth(Dimensions.CHAMP_NOMBRE_LARGEUR)
    # Même hauteur que les autres champs (§9.4) : sans cela, Qt donne à un champ de nombre quelques
    # pixels de plus, et il dépasse des listes posées sur la même ligne (ex. « Durée » du brief).
    champ.setFixedHeight(Hauteurs.CONTROLE)
    champ.setSuffix(suffixe)
    champ.setKeyboardTracking(False)  # valeur prise en compte à la fin de la saisie
    if info:
        champ.setToolTip(info)


def champ_entier(minimum: int, maximum: int, suffixe: str = "", info: str | None = None) -> ChampEntier:
    """Champ pour un nombre entier, limité à [minimum, maximum]."""
    champ = ChampEntier()
    champ.setRange(minimum, maximum)
    _preparer_champ(champ, suffixe, info)
    return champ


def champ_decimal(
    minimum: float, maximum: float, pas: float, decimales: int = 1, suffixe: str = "", info: str | None = None
) -> ChampDecimal:
    """Champ pour un nombre à virgule, limité à [minimum, maximum] (↑ ↓ : ± `pas`)."""
    champ = ChampDecimal()
    champ.setDecimals(decimales)
    champ.setRange(minimum, maximum)
    champ.setSingleStep(pas)
    _preparer_champ(champ, suffixe, info)
    return champ


def bloc(titre: str | None = None, marges: int = Espacements.XL) -> tuple[QFrame, QVBoxLayout]:
    """Bloc (panneau arrondi sur fond « surface »). Renvoie le bloc et sa disposition verticale."""
    cadre = QFrame()
    cadre.setProperty("role", "bloc")
    disposition = QVBoxLayout(cadre)
    disposition.setContentsMargins(marges, marges, marges, marges)
    disposition.setSpacing(Espacements.M)
    if titre:
        disposition.addWidget(libelle(titre, "titre-bloc"))
    return cadre, disposition


def separateur() -> QFrame:
    """Fine ligne horizontale."""
    ligne = QFrame()
    ligne.setProperty("role", "separateur")
    return ligne


def separateur_vertical(hauteur: int = Hauteurs.CONTROLE) -> QFrame:
    """Fine ligne verticale (ex. entre le titre du module et le coût de la session, dans le bandeau)."""
    ligne = QFrame()
    ligne.setProperty("role", "separateur-vertical")
    ligne.setFixedHeight(hauteur)
    return ligne


def vider_disposition(disposition) -> None:
    """Retire et détruit tout le contenu d'une disposition (y compris les dispositions imbriquées)."""
    while disposition.count():
        element = disposition.takeAt(0)
        if element.widget() is not None:
            element.widget().deleteLater()
        elif element.layout() is not None:
            vider_disposition(element.layout())
            element.layout().deleteLater()


def conteneur_vertical(espacement: int = Espacements.M) -> tuple[QWidget, QVBoxLayout]:
    """Zone transparente qui empile ses éléments verticalement."""
    zone = QWidget()
    disposition = QVBoxLayout(zone)
    disposition.setContentsMargins(0, 0, 0, 0)
    disposition.setSpacing(espacement)
    return zone, disposition
