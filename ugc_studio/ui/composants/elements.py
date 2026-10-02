"""Petites fonctions pour créer les éléments de base de l'interface avec le bon style.

Le style lui-même est dans theme.py : ici, on se contente d'indiquer le « rôle » de chaque
élément (titre de page, légende, bouton principal…), et la feuille de style fait le reste.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QFontMetrics, QFontMetricsF, QIcon, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStyle,
    QStyleOptionButton,
    QStyleOptionComboBox,
    QStyleOptionSlider,
    QStylePainter,
    QVBoxLayout,
    QWidget,
)

from ...sous_titres import typographie
from ..icones import icone
from ..polices import police
from ..theme import Couleurs, Dimensions, Durees, Espacements, Hauteurs, Opacites, Typo, qcolor
from .bouton import Bouton, dessiner_texte_centre_a_l_oeil
from .bulle import PROPRIETE_MAISON, cacher_bulle, montrer_bulle, texte_en_lignes
from .liste_deroulante import DelegueChoix, VueChoix, preparer_la_liste


# Entre un titre et ce qu'il précise (V3.2) : une puce, « Voix • Sérum Glowzy », « Voix • Conseils »
# (une barre oblique « / » jusqu'à la 3.1.0 ; elle garde son sens de « sur » : « 0:03 / 0:07 »).
SEPARATEUR_DE_TITRE = " • "


def titre_avec(titre: str, precision: str) -> str:
    """« Voix • Sérum Glowzy » : un titre (le module, la fenêtre…), puis ce qu'il précise."""
    return f"{titre}{SEPARATEUR_DE_TITRE}{precision}"


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


class ChampNomme(QWidget):
    """Un champ sous son nom (V3.1, §9.4 ter) : le nom en petit (12 px, gris), 8 px visibles au-dessus
    du champ (V3.2, voir Dimensions.ECART_NOM_CHAMP), comme dans le brief du module Script. Le même
    partout dans l'app : un nom à gauche du champ prenait une colonne de plus, et l'œil devait faire
    l'aller-retour.

    - `element` : le champ (ou une rangée : un champ et son unité, une liste et sa durée…) ;
    - `a_cote` : un petit bouton posé à droite du champ (ex. ↺) ;
    - `etire` : le champ prend toute la largeur (ex. une glissière) ; sinon, sa largeur naturelle.
    Griser le ChampNomme grise aussi son nom ; le cacher cache les deux."""

    def __init__(
        self,
        nom: str | None,
        element: QWidget | QLayout,
        a_cote: QWidget | None = None,
        etire: bool = False,
        aide: str | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Dimensions.ECART_NOM_CHAMP)
        self.nom = libelle(nom, "legende", retour_a_la_ligne=False) if nom else None
        # `aide` : une icône « i » devant le nom, qui explique le réglage au survol (V3.1 ; après le
        # nom jusqu'à la 3.1.0).
        self.aide = BoutonInfo(aide) if aide and nom else None
        if self.aide is not None:
            disposition.addLayout(ligne_avec_aide(self.nom, self.aide))
        elif self.nom is not None:
            disposition.addWidget(self.nom)
        ligne = QHBoxLayout()
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(Espacements.S)
        if isinstance(element, QWidget):
            ligne.addWidget(element, 1 if etire else 0)
        else:
            ligne.addLayout(element, 1 if etire else 0)
        if a_cote is not None:
            ligne.addWidget(a_cote)
        if not etire:
            ligne.addStretch(1)
        disposition.addLayout(ligne)
        self.element = element
        self.a_cote = a_cote
        politique = QSizePolicy.Policy.Expanding if etire else QSizePolicy.Policy.Preferred
        self.setSizePolicy(politique, QSizePolicy.Policy.Fixed)


def champ_nomme(nom: str | None, element: QWidget | QLayout, etire: bool = False, aide: str | None = None) -> ChampNomme:
    """Un champ sous son nom (voir ChampNomme)."""
    return ChampNomme(nom, element, etire=etire, aide=aide)


TOUTE_LA_RANGEE = "toute la rangée"


def champs_en_colonnes(champs, colonnes: int = 2) -> QGridLayout:
    """Champs sous leur nom, en colonnes de même largeur, comme le brief du module Script (16 px
    entre deux colonnes, 12 px entre deux rangées) : pour des champs qui s'étirent (listes, textes).

    `champs` : des couples (nom, champ), ou des triplets (nom, champ, TOUTE_LA_RANGEE) pour un champ
    qui prend toute la rangée (ex. un texte de plusieurs lignes) ; None laisse une case vide.
    Renvoie la grille ; chaque ChampNomme est dans `grille.champs` (par nom)."""
    grille = QGridLayout()
    grille.setContentsMargins(0, 0, 0, 0)
    grille.setHorizontalSpacing(Espacements.L)
    grille.setVerticalSpacing(Espacements.M)
    grille.champs = {}
    rang = colonne = 0
    for entree in champs:
        if entree is None:
            colonne += 1
        else:
            nom, element, *options = entree
            champ = ChampNomme(nom, element, etire=True)
            grille.champs[nom] = champ
            if TOUTE_LA_RANGEE in options:
                if colonne:
                    rang, colonne = rang + 1, 0
                grille.addWidget(champ, rang, 0, 1, colonnes)
                rang += 1
                continue
            grille.addWidget(champ, rang, colonne)
            colonne += 1
        if colonne >= colonnes:
            rang, colonne = rang + 1, 0
    for numero in range(colonnes):
        grille.setColumnStretch(numero, 1)
    return grille


def noms_de_colonnes(noms, largeur_fin: int = 0) -> QHBoxLayout:
    """Les noms des colonnes d'une liste de champs (ex. « Mot tel qu'écrit dans le script », « Se
    prononce »), chacun au-dessus de sa colonne : colonnes de même largeur, 8 px entre elles, puis
    8 px et `largeur_fin` px pour les colonnes des petits boutons au bout de chaque ligne (▶,
    corbeille ; 8 px entre deux de ces colonnes, compris dans `largeur_fin`). À placer
    Dimensions.ECART_NOM_CHAMP au-dessus de la grille des champs (V3.2) : 8 px visibles sous les noms,
    comme sous le nom d'un champ, alors que deux lignes de champs restent à 8 px l'une de l'autre."""
    ligne = QHBoxLayout()
    ligne.setContentsMargins(0, 0, 0, 0)
    ligne.setSpacing(Espacements.S)
    for nom in noms:
        etiquette = libelle(nom, "legende")
        # La largeur vient des colonnes, pas du texte (qui passe à la ligne s'il le faut).
        etiquette.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        ligne.addWidget(etiquette, 1, Qt.AlignmentFlag.AlignBottom)
    if largeur_fin:
        ligne.addSpacing(Espacements.S + largeur_fin)
    return ligne


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
    aide ; setText() remet l'info avec son ampoule. Une erreur s'efface après 8 s, comme tous les
    messages après une action (V3.2) : ce qui était affiché avant elle revient (sans rien, l'Info se
    cache)."""

    def __init__(self, texte: str = "", role: str = "legende", largeur_ampoule: int = Dimensions.ICONE_PETITE):
        super().__init__()
        self._role = role
        self._avant_l_erreur = (texte, role, True)  # ce qui revient quand une erreur s'efface
        self._fin_de_l_erreur = QTimer(self)
        self._fin_de_l_erreur.setSingleShot(True)
        self._fin_de_l_erreur.timeout.connect(self._effacer_l_erreur)
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
        `erreur=True` : message d'erreur, en rouge (à la taille de l'info), qui s'efface après 8 s."""
        role = self._role
        if erreur:
            role = "legende-erreur" if self._role == "legende" else "erreur"
        self._afficher(texte, role, avec_ampoule=False, erreur=erreur)

    def _effacer_l_erreur(self) -> None:
        texte, role, avec_ampoule = self._avant_l_erreur
        self._afficher(texte, role, avec_ampoule)
        if not texte:
            self.hide()

    def _afficher(self, texte: str, role: str, avec_ampoule: bool, erreur: bool = False) -> None:
        if erreur and texte:
            self._fin_de_l_erreur.start(Durees.MESSAGE_MS)
        else:
            self._fin_de_l_erreur.stop()
            self._avant_l_erreur = (texte, role, avec_ampoule)
        self.etiquette.setText(texte)
        if self.etiquette.property("role") != role:
            self.etiquette.setProperty("role", role)
            self.etiquette.style().unpolish(self.etiquette)  # applique le nouveau style
            self.etiquette.style().polish(self.etiquette)
        self.ampoule.setVisible(avec_ampoule)


def info(texte: str = "", role: str = "legende") -> Info:
    """Info avec son ampoule (voir Info), toujours visible. Seulement pour une phrase indispensable
    pour savoir quoi faire à ce moment (V3.1) ; les autres explications vont dans une icône « i »
    (voir BoutonInfo). Pas pour un nom de champ, une donnée (durée, coût…), une traduction ni un
    message d'état."""
    return Info(texte, role)


# Messages qui s'effacent seuls (V3.2) : réussi (vert), erreur (rouge), à vérifier (orange).
ROLES_EPHEMERES = ("succes", "erreur", "avertissement", "legende-erreur", "legende-avertissement")


def afficher_message(etiquette: QLabel, texte: str, role: str, cacher_vide: bool = True) -> None:
    """Message d'état après une action, dans `etiquette` (V3.2, §9.4 ter) : le texte, dans le style du
    rôle (« succes » vert, « erreur » rouge, « avertissement » orange, « secondaire » gris…).

    Un message vert, rouge ou orange s'efface tout seul après 8 s (Durees.MESSAGE_MS), le même délai
    partout dans l'app ; un message gris (un travail en cours, une donnée) reste jusqu'au suivant.
    `cacher_vide` : sans texte, l'étiquette disparaît (sinon elle reste, vide, à sa place)."""
    etiquette.setText(texte)
    if etiquette.property("role") != role:
        etiquette.setProperty("role", role)
        etiquette.style().unpolish(etiquette)  # applique le nouveau style
        etiquette.style().polish(etiquette)
    if cacher_vide:
        etiquette.setVisible(bool(texte))
    minuterie = getattr(etiquette, "_fin_du_message", None)
    if texte and role in ROLES_EPHEMERES:
        if minuterie is None:
            minuterie = QTimer(etiquette)
            minuterie.setSingleShot(True)
            minuterie.timeout.connect(lambda: _effacer_le_message(etiquette, cacher_vide))
            etiquette._fin_du_message = minuterie
        minuterie.start(Durees.MESSAGE_MS)
    elif minuterie is not None:
        minuterie.stop()


def _effacer_le_message(etiquette: QLabel, cacher_vide: bool) -> None:
    etiquette.clear()
    if cacher_vide:
        etiquette.hide()

class BoutonInfo(QWidget):
    """Icône « i » (V3.1, §9.4 ter), posée devant le texte qu'elle explique (V3.2 : un titre, le nom
    d'un champ ; sur une case à cocher, entre la case et son texte ; après un bouton) : au survol,
    l'explication s'affiche tout de suite dans une bulle ; un clic la montre aussi. Elle remplace les
    phrases d'aide qui n'ont pas besoin d'être lues pour savoir quoi faire : l'interface reste légère,
    l'explication reste à portée de souris. text() et setText() comme une étiquette (le texte peut
    changer, ex. la vidéo HDR d'un export)."""

    def __init__(self, texte: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._texte = texte
        self._icones = {
            survol: icone("info", Couleurs.TEXTE if survol else Couleurs.TEXTE_SECONDAIRE, taille=Dimensions.ICONE_INFO)
            for survol in (False, True)
        }
        self.setFixedSize(Dimensions.ICONE_INFO, Dimensions.ICONE_INFO)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        self.setAccessibleDescription(texte)
        self.setProperty(PROPRIETE_MAISON, True)  # elle montre sa bulle elle-même, dès le survol

    def text(self) -> str:
        return self._texte

    def setText(self, texte: str) -> None:  # noqa: N802 — même nom que chez QLabel
        self._texte = texte
        self.setAccessibleDescription(texte)

    def montrer(self) -> None:
        """Affiche l'explication dans la bulle de l'app, sous l'icône (espaces insécables à la
        française : un « : » ne commence jamais une ligne de la bulle)."""
        if self._texte:
            position = self.mapToGlobal(QPoint(0, self.height() + Espacements.XS))
            montrer_bulle(texte_en_lignes(typographie(self._texte, "fr")), position, self, sous_le_curseur=False)

    def event(self, evenement) -> bool:
        # L'infobulle habituelle de Qt (après un temps d'arrêt, aussi sur une icône grisée) : la même
        # bulle, au même endroit, plutôt qu'une seconde bulle sous la souris.
        if evenement.type() == QEvent.Type.ToolTip:
            self.montrer()
            return True
        return super().event(evenement)

    def enterEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        self._redessiner()
        self.montrer()  # tout de suite, sans le délai habituel des infobulles
        super().enterEvent(evenement)

    def leaveEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        self._redessiner()
        cacher_bulle(self)
        super().leaveEvent(evenement)

    def _redessiner(self) -> None:
        """L'icône change de couleur au survol ; ce qui la porte aussi (une case à cocher, le titre
        d'une section : ils ne s'éclairent pas quand la souris est sur l'icône)."""
        self.update()
        if self.parentWidget() is not None:
            self.parentWidget().update()

    def mousePressEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        self.montrer()
        evenement.accept()

    def paintEvent(self, _evenement) -> None:  # noqa: N802 — nom imposé par Qt
        peintre = QPainter(self)
        mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        self._icones[self.underMouse()].paint(peintre, self.rect(), Qt.AlignmentFlag.AlignCenter, mode)
        peintre.end()


def ligne_avec_aide(element: QWidget, aide: BoutonInfo | None, fin: bool = True, apres: bool = False) -> QHBoxLayout:
    """Une ligne : l'icône « i », puis `element` (un titre, le nom d'un champ) 8 px après elle (V3.2 :
    l'icône est au début du texte qu'elle explique), centrée sur la hauteur du texte ; puis la place
    qui reste (sauf `fin=False`, pour ajouter d'autres éléments à droite). `apres=True` : l'icône
    reste après l'élément, 8 px après lui (après un bouton : « Choisir les modèles… (i) »)."""
    ligne = QHBoxLayout()
    ligne.setContentsMargins(0, 0, 0, 0)
    ligne.setSpacing(Dimensions.ECART_INFO)
    if aide is not None and not apres:
        ligne.addWidget(aide, 0, Qt.AlignmentFlag.AlignVCenter)
    ligne.addWidget(element)
    if aide is not None and apres:
        ligne.addWidget(aide, 0, Qt.AlignmentFlag.AlignVCenter)
    if fin:
        ligne.addStretch(1)
    ligne.aide = aide
    return ligne


def avec_aide(element: QWidget, aide: str | None) -> QWidget | QHBoxLayout:
    """`element` (un texte) précédé de son icône « i » si `aide` : une ligne (voir ligne_avec_aide),
    dont l'icône est dans `.aide`. Sans aide : l'élément seul."""
    if not aide:
        return element
    return ligne_avec_aide(element, BoutonInfo(aide))


def intitule(texte: str, aide: str | None = None) -> QWidget:
    """Petit titre dans un bloc (« Balises », « Réorganiser à la main »…), précédé de son icône « i »
    quand il a une explication. Renvoie un élément à placer (l'étiquette est dans `.etiquette`,
    l'icône dans `.aide`)."""
    zone = QWidget()
    zone.etiquette = libelle(texte, "intitule", retour_a_la_ligne=False)
    zone.aide = BoutonInfo(aide) if aide else None
    zone.setLayout(ligne_avec_aide(zone.etiquette, zone.aide))
    return zone


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
    bouton carré, icône seule).

    `action` est appelée sans argument. Le signal `clicked` de Qt transmet « coché ou non » : passé
    tel quel, il remplacerait le premier paramètre d'une action qui en a un par défaut (ex.
    `lambda groupe=titre: …` recevrait False au lieu du titre)."""
    resultat = Bouton(texte, variante, nom_icone)
    if action is not None:
        resultat.clicked.connect(lambda _coche=False: action())
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

    - Liste « intégrée au champ » (§9.4 quinquies, revue en V3.1) : elle s'ouvre 8 px sous le champ,
      coins arrondis, avec tous les choix, l'actuel sur un fond mauve léger (voir
      composants/liste_deroulante.py).
    - Texte trop long pour le champ fermé : abrégé par « … » (Qt le coupait au milieu d'une lettre),
      avec le texte complet au survol."""

    def __init__(self):
        super().__init__()
        self.setView(VueChoix())
        self.setItemDelegate(DelegueChoix(self))
        self.setMaxVisibleItems(Dimensions.LISTE_CHOIX_VISIBLES)
        preparer_la_liste(self)
        self.setProperty(PROPRIETE_MAISON, True)  # sa bulle donne aussi le texte abrégé (voir event)

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
        if evenement.type() == QEvent.Type.ToolTip:
            # La bulle de l'app : le texte complet s'il est abrégé, puis l'infobulle de la liste.
            texte, aide = self.currentText(), self.toolTip()
            abrege = not self.isEditable() and texte and self.texte_affiche() != texte
            bulle = "\n".join(t for t in ((texte if abrege else ""), aide) if t)
            if not bulle:
                evenement.ignore()  # rien à dire ici : l'élément parent peut avoir son infobulle
                return False
            montrer_bulle(bulle, evenement.globalPos(), self)
            return True
        return super().event(evenement)


class Glissiere(_SansMolette, QSlider):
    """Barre de position d'un lecteur (vidéo, audio). V3.2 : un clic n'importe où sur la barre y place
    la lecture tout de suite (avant, un clic avançait ou reculait d'un pas) ; on peut ensuite glisser
    sans relâcher. Les lecteurs écoutent `sliderMoved` : il est émis pour ce clic aussi."""

    def mousePressEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        if evenement.button() == Qt.MouseButton.LeftButton and self.maximum() > self.minimum():
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            style = self.style()
            poignee = style.subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self)
            point = evenement.position().toPoint()
            if not poignee.contains(point):
                rainure = style.subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderGroove, self)
                if self.orientation() == Qt.Orientation.Horizontal:
                    debut, longueur, ici = rainure.x(), rainure.width() - poignee.width(), point.x() - poignee.width() // 2
                else:
                    debut, longueur, ici = rainure.y(), rainure.height() - poignee.height(), point.y() - poignee.height() // 2
                valeur = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), ici - debut, max(1, longueur), option.upsideDown)
                self.setSliderDown(True)  # comme une poignée saisie : sliderMoved est émis
                self.setSliderPosition(valeur)
        # La poignée est maintenant sous la souris : Qt la saisit, pour glisser sans relâcher.
        super().mousePressEvent(evenement)

    def mouseReleaseEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        super().mouseReleaseEvent(evenement)
        if self.isSliderDown() and not evenement.buttons():
            self.setSliderDown(False)  # jamais « saisie » une fois la souris relâchée


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


class CaseACocher(QCheckBox):
    """Case à cocher dont l'icône « i » se place entre la case et son texte (V3.2) : la case, 8 px,
    l'icône, 8 px, le texte. L'icône est posée sur la case à cocher elle-même : le texte reste le sien
    (un clic dessus coche la case, il passe en mauve quand un effet est changé…) ; la feuille de style
    lui laisse la place entre la case et le texte (propriété « aide », voir theme.py). Un clic sur
    l'icône montre l'explication, sans cocher la case."""

    def __init__(self, texte: str, explication: str | None = None, parent: QWidget | None = None):
        super().__init__(texte, parent)
        self.aide = BoutonInfo(explication, self) if explication else None
        if self.aide is not None:
            self.setProperty("aide", True)

    def _placer_l_aide(self) -> None:
        """L'icône 8 px après la case, centrée sur elle (la case est centrée sur la ligne du texte)."""
        if self.aide is None:
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        case = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
        haut = case.top() + (case.height() - self.aide.height()) // 2
        self.aide.move(case.right() + 1 + Dimensions.ECART_INFO, haut)

    def resizeEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        super().resizeEvent(evenement)
        self._placer_l_aide()

    def changeEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        super().changeEvent(evenement)
        if evenement.type() == QEvent.Type.StyleChange:
            self._placer_l_aide()

    def paintEvent(self, _evenement) -> None:  # noqa: N802 — nom imposé par Qt
        # Comme QCheckBox.paintEvent(), mais la case ne s'éclaire pas quand la souris est sur l'icône :
        # un clic sur l'icône ne coche pas la case.
        peintre = QStylePainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        survol = QStyle.StateFlag.State_MouseOver
        if self.aide is not None and self.aide.underMouse() and option.state & survol:
            option.state ^= survol
        peintre.drawControl(QStyle.ControlElement.CE_CheckBox, option)


def case_a_cocher(texte: str, explication: str | None = None) -> tuple[QWidget, QCheckBox]:
    """Case à cocher au texte court, avec son explication dans une icône « i » entre la case et le
    texte (V3.2 ; après le texte jusqu'à la 3.1.0 ; V3.1 : l'explication se lit au survol, au lieu
    d'une phrase toujours affichée dessous). Renvoie la zone à placer dans la page et la case
    elle-même ; l'icône est dans `zone.aide` (None sans explication). Pour griser la case, griser la
    zone (l'icône l'est alors aussi).

    Pourquoi un texte court ? Le texte d'une case à cocher ne passe jamais à la ligne : une longue
    phrase imposerait sa largeur à toute la page, qui déborderait à droite dans une fenêtre étroite.
    (Un test vérifie que le texte des cases reste court.)"""
    zone = QWidget()
    case = CaseACocher(texte, explication)
    zone.aide = case.aide
    disposition = QHBoxLayout(zone)
    disposition.setContentsMargins(0, 0, 0, 0)
    disposition.addWidget(case)
    disposition.addStretch(1)
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


def marge_haute_titre(marges: int = Espacements.XL, hauteur_ligne: int = 0) -> int:
    """Marge du haut d'un bloc qui commence par son titre (V3.2) : le haut des majuscules du titre à
    `marges` px du bord du bloc, autant qu'à gauche (la police du titre garde 4 px au-dessus des
    majuscules, voir Dimensions.RESERVE_TITRE_BLOC). `hauteur_ligne` : la hauteur de la ligne du
    titre quand il la partage avec des boutons, centrés sur lui (ex. « Brief » et ses boutons de
    32 px) : la marge a alors de quoi garder le titre à la même place, les boutons un peu plus haut."""
    hauteur_titre = QFontMetrics(police(Typo.TITRE_BLOC, Typo.GRAISSE_FORTE)).height()
    decalage = max(0, (hauteur_ligne - hauteur_titre) // 2)  # le titre est centré dans sa ligne
    return max(0, marges - Dimensions.RESERVE_TITRE_BLOC - decalage)


def bloc(titre: str | None = None, marges: int = Espacements.XL, aide: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    """Bloc (panneau arrondi sur fond « surface »). Renvoie le bloc et sa disposition verticale.
    `aide` : explication du bloc, dans une icône « i » devant le titre (V3.1 ; après lui jusqu'à la
    3.1.0) ; le titre est dans `cadre.titre`, l'icône dans `cadre.aide`. Avec un titre, la marge du
    haut le place à `marges` px du bord, comme à gauche (voir marge_haute_titre)."""
    cadre = QFrame()
    cadre.setProperty("role", "bloc")
    disposition = QVBoxLayout(cadre)
    disposition.setContentsMargins(marges, marge_haute_titre(marges) if titre else marges, marges, marges)
    disposition.setSpacing(Espacements.M)
    cadre.titre = cadre.aide = None
    if titre:
        # Avec une icône, le titre garde sa largeur (l'icône le précède) ; seul, il peut passer à la ligne.
        cadre.titre = libelle(titre, "titre-bloc", retour_a_la_ligne=not aide)
        if aide:
            cadre.aide = BoutonInfo(aide)
            disposition.addLayout(ligne_avec_aide(cadre.titre, cadre.aide))
        else:
            disposition.addWidget(cadre.titre)
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
