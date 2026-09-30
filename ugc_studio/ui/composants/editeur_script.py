"""Éditeur de script avec badges de balises (§5.2).

- Les balises (<laugh>, <sigh>…) apparaissent comme des pastilles colorées par famille, avec leur
  nom français (« rire », « soupir »…) ; leur vrai nom, celui envoyé à Google, s'affiche au survol.
  Techniquement, chaque badge est un seul « caractère objet » du document : il s'efface d'un
  retour arrière et se déplace par couper/coller comme une lettre.
- Le bouton « Accentuer » met un mot en valeur : il s'affiche en MAJUSCULES (et en mauve) et sera
  envoyé en majuscules au TTS, mais le texte d'origine est conservé pour les sous-titres.
- Copier/coller : entre deux éditeurs de l'app, badges et accents sont conservés ; depuis un autre
  logiciel, les balises écrites « <laugh> » ou « <rire> » deviennent automatiquement des badges.
  Vers un autre logiciel, les balises sont copiées avec leur vrai nom anglais (« <laugh> »).
"""

from __future__ import annotations

import json

import math

from PySide6.QtCore import QEvent, QMimeData, QPoint, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QFont,
    QFontMetricsF,
    QPainter,
    QPen,
    QPyTextObject,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import QTextEdit, QToolTip

from ...balises import famille_de, info_balise, nom_affiche
from ...script import depuis_texte, normaliser, texte_pour_api
from ..polices import police
from ..theme import Couleurs, CouleursBalises, Dimensions, Hauteurs, Opacites, Typo, qcolor
from .bouton import dessiner_texte_centre_minuscules

CARACTERE_OBJET = "￼"  # caractère « objet » (remplacé à l'écran par le dessin du badge)
TYPE_BALISE = int(QTextFormat.ObjectTypes.UserObject.value) + 1
PROP_BALISE = int(QTextFormat.Property.UserProperty.value) + 1
PROP_ACCENTUE = int(QTextFormat.Property.UserProperty.value) + 2
TYPE_MIME_SCRIPT = "application/x-ugc-studio-script"


class DessinBadge(QPyTextObject):
    """Dessine un badge de balise dans le texte : le nom français, centré à l'œil."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._police = police(Typo.LEGENDE, Typo.GRAISSE_MOYENNE)

    def largeur(self, balise: str) -> float:
        """Largeur occupée dans le texte par le badge de cette balise (espaces autour compris)."""
        largeur_nom = QFontMetricsF(self._police).horizontalAdvance(nom_affiche(balise))
        return largeur_nom + 2 * Dimensions.BADGE_MARGE_HORIZONTALE + 2 * Dimensions.BADGE_ECART

    def intrinsicSize(self, _document, _position, format_texte) -> QSizeF:
        return QSizeF(self.largeur(str(format_texte.property(PROP_BALISE) or "")), Hauteurs.PASTILLE)

    def drawObject(self, peintre: QPainter, zone: QRectF, _document, _position, format_texte) -> None:
        balise = str(format_texte.property(PROP_BALISE) or "")
        famille = famille_de(balise)
        couleur = CouleursBalises.de(famille.identifiant if famille else "")
        pastille = QRectF(zone).adjusted(Dimensions.BADGE_ECART, 0, -Dimensions.BADGE_ECART, 0)
        rayon = pastille.height() / 2
        peintre.save()
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        peintre.setPen(QPen(qcolor(couleur, Opacites.CONTOUR_BADGE), Dimensions.BORDURE))
        peintre.setBrush(QBrush(qcolor(couleur, Opacites.FOND_BADGE)))
        peintre.drawRoundedRect(pastille, rayon, rayon)
        dessiner_texte_centre_minuscules(peintre, pastille, nom_affiche(balise), self._police, qcolor(couleur))
        peintre.restore()


def format_balise(nom: str) -> QTextCharFormat:
    format_texte = QTextCharFormat()
    format_texte.setObjectType(TYPE_BALISE)
    format_texte.setProperty(PROP_BALISE, nom)
    format_texte.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignMiddle)
    return format_texte


def format_texte(accentue: bool = False) -> QTextCharFormat:
    format_normal = QTextCharFormat()
    if accentue:
        format_normal.setProperty(PROP_ACCENTUE, True)
        format_normal.setFontCapitalization(QFont.Capitalization.AllUppercase)
        format_normal.setForeground(QBrush(qcolor(Couleurs.ACCENT_SURVOL)))
    return format_normal


class EditeurScript(QTextEdit):
    script_modifie = Signal()
    focus_recu = Signal()  # l'éditeur devient celui où la palette insère ses balises

    def __init__(self, parent=None, hauteur_auto: bool = False):
        """`hauteur_auto` : l'éditeur grandit avec son texte (répliques), au lieu d'avoir sa propre
        barre de défilement dans une page qui défile déjà."""
        super().__init__(parent)
        self.setAcceptRichText(False)
        self._hauteur_auto = hauteur_auto
        self._hauteur_min = Dimensions.EDITEUR_REPLIQUE_HAUTEUR_MIN if hauteur_auto else Dimensions.EDITEUR_HAUTEUR_MIN
        self.setMinimumHeight(self._hauteur_min)
        self.setPlaceholderText(
            "Écris ou colle ton script ici. Pour ajouter une balise (rire, pause…), clique à l'endroit "
            "voulu dans le texte, puis sur la balise dans la palette."
        )
        self._dessin = DessinBadge(self)
        self.document().documentLayout().registerHandler(TYPE_BALISE, self._dessin)
        self.textChanged.connect(self.script_modifie.emit)
        self.cursorPositionChanged.connect(self._format_propre_apres_badge)
        if hauteur_auto:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.document().documentLayout().documentSizeChanged.connect(self._ajuster_hauteur)

    def focusInEvent(self, evenement) -> None:
        super().focusInEvent(evenement)
        self.focus_recu.emit()

    def resizeEvent(self, evenement) -> None:
        super().resizeEvent(evenement)
        if self._hauteur_auto:
            self._ajuster_hauteur()

    def _ajuster_hauteur(self, *_args) -> None:
        """Hauteur = hauteur du texte + bordures et marges intérieures (au moins la hauteur minimale).

        Bordures et marges = ce qui sépare le bord de l'éditeur de sa zone de texte (« viewport »).
        """
        cadre = self.height() - self.viewport().height()
        hauteur = max(self._hauteur_min, math.ceil(self.document().size().height()) + cadre)
        if hauteur != self.height():
            self.setFixedHeight(hauteur)

    # --- Contenu -----------------------------------------------------------------------------

    def definir_segments(self, segments: list[dict]) -> None:
        self.blockSignals(True)
        self.clear()
        curseur = self.textCursor()
        self._inserer(curseur, segments)
        self.blockSignals(False)
        self.document().clearUndoRedoStacks()
        curseur.movePosition(QTextCursor.MoveOperation.Start)
        self.setTextCursor(curseur)

    def segments(self, debut: int | None = None, fin: int | None = None) -> list[dict]:
        """Le script (ou la partie [debut, fin[) sous forme de segments."""
        texte = self.document().toPlainText()
        debut = 0 if debut is None else debut
        fin = len(texte) if fin is None else fin
        curseur = QTextCursor(self.document())
        resultat: list[dict] = []
        for position in range(debut, fin):
            caractere = texte[position]
            curseur.setPosition(position)
            curseur.setPosition(position + 1, QTextCursor.MoveMode.KeepAnchor)
            format_car = curseur.charFormat()
            if caractere == CARACTERE_OBJET and format_car.objectType() == TYPE_BALISE:
                resultat.append({"balise": str(format_car.property(PROP_BALISE))})
            elif caractere != CARACTERE_OBJET:
                accentue = bool(format_car.property(PROP_ACCENTUE))
                resultat.append({"texte": caractere, "accentue": True} if accentue else {"texte": caractere})
        return normaliser(resultat)

    def texte_api(self) -> str:
        return texte_pour_api(self.segments())

    # --- Infobulle des badges : le vrai nom de la balise -------------------------------------

    def balise_sous(self, point: QPoint) -> str | None:
        """Nom anglais de la balise dont le badge est sous `point` (coordonnées de la zone de
        texte), ou None s'il n'y a pas de badge à cet endroit."""
        curseur = self.cursorForPosition(point)
        derniere = self.document().characterCount() - 1  # la fin du document
        texte = self.document().toPlainText()
        for position in (curseur.position() - 1, curseur.position()):
            if not 0 <= position < min(derniere, len(texte)) or texte[position] != CARACTERE_OBJET:
                continue
            caractere = QTextCursor(self.document())
            caractere.setPosition(position)
            caractere.setPosition(position + 1, QTextCursor.MoveMode.KeepAnchor)
            format_car = caractere.charFormat()
            if format_car.objectType() != TYPE_BALISE:
                continue
            balise = str(format_car.property(PROP_BALISE))
            caractere.setPosition(position)
            debut = self.cursorRect(caractere)  # la ligne du badge ; son bord gauche
            badge = QRectF(debut.left(), debut.top(), self._dessin.largeur(balise), debut.height())
            if badge.contains(point.x(), point.y()):
                return balise
        return None

    def viewportEvent(self, evenement) -> bool:  # noqa: N802 — nom imposé par Qt
        if evenement.type() == QEvent.Type.ToolTip:
            balise = self.balise_sous(evenement.pos())
            if balise:
                QToolTip.showText(evenement.globalPos(), info_balise(balise), self.viewport())
            else:
                QToolTip.hideText()
                evenement.ignore()
            return True
        return super().viewportEvent(evenement)

    def position_curseur(self) -> int:
        """Position du curseur, en caractères (un badge compte pour 1), pour « Découper ici »."""
        return self.textCursor().position()

    # --- Actions -----------------------------------------------------------------------------

    def inserer_balise(self, nom: str) -> None:
        curseur = self.textCursor()
        curseur.insertText(CARACTERE_OBJET, format_balise(nom))
        curseur.setCharFormat(format_texte())
        self.setTextCursor(curseur)
        self.setCurrentCharFormat(format_texte())
        self.setFocus()

    def basculer_accent(self) -> None:
        """Accentue le texte sélectionné (ou le mot sous le curseur), ou retire l'accent s'il y est déjà."""
        curseur = self.textCursor()
        if not curseur.hasSelection():
            curseur.select(QTextCursor.SelectionType.WordUnderCursor)
            if not curseur.hasSelection():
                return
        debut, fin = curseur.selectionStart(), curseur.selectionEnd()
        deja = all(s.get("accentue") for s in self.segments(debut, fin) if "texte" in s)
        curseur.beginEditBlock()
        texte = self.document().toPlainText()
        for position in range(debut, fin):
            if texte[position] == CARACTERE_OBJET:
                continue
            morceau = QTextCursor(self.document())
            morceau.setPosition(position)
            morceau.setPosition(position + 1, QTextCursor.MoveMode.KeepAnchor)
            morceau.setCharFormat(format_texte(accentue=not deja))
        curseur.endEditBlock()
        self.setFocus()

    # --- Copier / coller ---------------------------------------------------------------------

    def createMimeDataFromSelection(self) -> QMimeData:
        curseur = self.textCursor()
        segments = self.segments(curseur.selectionStart(), curseur.selectionEnd())
        donnees = QMimeData()
        # Pour les autres logiciels : texte avec les balises écrites « <laugh> ».
        donnees.setText("".join(f"<{s['balise']}>" if "balise" in s else s["texte"] for s in segments))
        # Pour l'app elle-même : les segments complets (accents compris).
        donnees.setData(TYPE_MIME_SCRIPT, json.dumps(segments).encode("utf-8"))
        return donnees

    def canInsertFromMimeData(self, source: QMimeData) -> bool:
        return source.hasFormat(TYPE_MIME_SCRIPT) or source.hasText()

    def insertFromMimeData(self, source: QMimeData) -> None:
        if source.hasFormat(TYPE_MIME_SCRIPT):
            try:
                segments = json.loads(bytes(source.data(TYPE_MIME_SCRIPT)).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                segments = depuis_texte(source.text())
        else:
            segments = depuis_texte(source.text())
        curseur = self.textCursor()
        curseur.beginEditBlock()
        self._inserer(curseur, segments)
        curseur.endEditBlock()
        self.setTextCursor(curseur)

    # --- Interne -----------------------------------------------------------------------------

    @staticmethod
    def _inserer(curseur: QTextCursor, segments: list[dict]) -> None:
        for segment in segments:
            if "balise" in segment:
                curseur.insertText(CARACTERE_OBJET, format_balise(segment["balise"]))
            else:
                curseur.insertText(segment.get("texte", ""), format_texte(bool(segment.get("accentue"))))
        curseur.setCharFormat(format_texte())

    def _format_propre_apres_badge(self) -> None:
        """Le texte tapé juste après un badge ne doit pas hériter de son format de badge.

        Uniquement sans sélection : avec une sélection, setCurrentCharFormat() appliquerait le
        format à tout le texte sélectionné… et effacerait les badges qu'il contient.
        """
        if self.textCursor().hasSelection():
            return
        if self.currentCharFormat().objectType() == TYPE_BALISE:
            self.setCurrentCharFormat(format_texte())
