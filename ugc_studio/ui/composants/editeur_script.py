"""Éditeur de script avec badges de balises (§5.2).

- Les balises (<laugh>, <sigh>…) apparaissent comme des pastilles colorées par famille. Techniquement,
  chaque badge est un seul « caractère objet » du document : il s'efface d'un retour arrière et se
  déplace par couper/coller comme une lettre.
- Le bouton « Accentuer » met un mot en valeur : il s'affiche en MAJUSCULES (et en mauve) et sera
  envoyé en majuscules au TTS, mais le texte d'origine est conservé pour les sous-titres.
- Copier/coller : entre deux éditeurs de l'app, badges et accents sont conservés ; depuis un autre
  logiciel, les balises écrites « <laugh> » deviennent automatiquement des badges.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QMimeData, QRectF, QSizeF, Qt, Signal
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
    QTextOption,
)
from PySide6.QtWidgets import QTextEdit

from ...balises import famille_de
from ...script import depuis_texte, normaliser, texte_pour_api
from ..polices import police
from ..theme import Couleurs, CouleursBalises, Dimensions, Hauteurs, Opacites, Typo, qcolor

CARACTERE_OBJET = "￼"  # caractère « objet » (remplacé à l'écran par le dessin du badge)
TYPE_BALISE = int(QTextFormat.ObjectTypes.UserObject.value) + 1
PROP_BALISE = int(QTextFormat.Property.UserProperty.value) + 1
PROP_ACCENTUE = int(QTextFormat.Property.UserProperty.value) + 2
TYPE_MIME_SCRIPT = "application/x-ugc-studio-script"


class DessinBadge(QPyTextObject):
    """Dessine un badge de balise dans le texte."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._police = police(Typo.LEGENDE, Typo.GRAISSE_MOYENNE)

    def intrinsicSize(self, _document, _position, format_texte) -> QSizeF:
        nom = str(format_texte.property(PROP_BALISE) or "")
        largeur = QFontMetricsF(self._police).horizontalAdvance(nom)
        return QSizeF(largeur + 2 * Dimensions.BADGE_MARGE_HORIZONTALE + 2 * Dimensions.BADGE_ECART, Hauteurs.PASTILLE)

    def drawObject(self, peintre: QPainter, zone: QRectF, _document, _position, format_texte) -> None:
        nom = str(format_texte.property(PROP_BALISE) or "")
        famille = famille_de(nom)
        couleur = CouleursBalises.de(famille.identifiant if famille else "")
        pastille = QRectF(zone).adjusted(Dimensions.BADGE_ECART, 0, -Dimensions.BADGE_ECART, 0)
        rayon = pastille.height() / 2
        peintre.save()
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        peintre.setPen(QPen(qcolor(couleur, Opacites.CONTOUR_BADGE), Dimensions.BORDURE))
        peintre.setBrush(QBrush(qcolor(couleur, Opacites.FOND_BADGE)))
        peintre.drawRoundedRect(pastille, rayon, rayon)
        peintre.setFont(self._police)
        peintre.setPen(qcolor(couleur))
        peintre.drawText(pastille, nom, QTextOption(Qt.AlignmentFlag.AlignCenter))
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setMinimumHeight(Dimensions.EDITEUR_HAUTEUR_MIN)
        self.setPlaceholderText(
            "Écris ou colle ton script ici. Pour ajouter une balise (rire, pause…), clique à l'endroit "
            "voulu dans le texte, puis sur la balise dans la palette."
        )
        self._dessin = DessinBadge(self)
        self.document().documentLayout().registerHandler(TYPE_BALISE, self._dessin)
        self.textChanged.connect(self.script_modifie.emit)
        self.cursorPositionChanged.connect(self._format_propre_apres_badge)

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
