"""Éditeur de transcription (§6.4) : le texte mot par mot, synchronisé avec la lecture.

- Le mot en cours de lecture est surligné (mauve léger) ; le mot choisi pour être corrigé est
  surligné en mauve soutenu.
- Clic sur un mot : il est choisi (pour le corriger) et la lecture se place à ce moment.
- Hésitations (« euh »…) : en gris ; barrées quand elles sont masquées dans les sous-titres.
- Voix séparées : chaque changement de personne commence un paragraphe « Personne 2 : ».
Le texte ne se modifie pas directement ici : les corrections passent par le panneau du mot
choisi, pour garder le timing de chaque mot.
"""

from __future__ import annotations

import bisect

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

from ...transcription import Mot, est_hesitation
from ..theme import Couleurs, Dimensions, Opacites, Typo, qcolor


def nom_de_personne(locuteur: str) -> str:
    """« spk_2 » → « Personne 2 »."""
    numero = locuteur.rsplit("_", 1)[-1]
    return f"Personne {numero}" if numero.isdigit() else locuteur


class EditeurTranscription(QTextEdit):
    mot_clique = Signal(int)  # indice du mot cliqué

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMinimumHeight(Dimensions.EDITEUR_HAUTEUR_MIN)
        self._debuts: list[int] = []  # position de chaque mot dans le texte affiché
        self._fins: list[int] = []
        self._lecture = -1
        self._choisi = -1

    # --- Affichage ---------------------------------------------------------------------------

    def afficher(self, mots: list[Mot], hesitations: set[str], masquer: bool) -> None:
        """(Re)construit le texte ; la position de défilement est gardée."""
        defilement = self.verticalScrollBar().value()
        self.clear()
        self._debuts, self._fins = [], []
        curseur = QTextCursor(self.document())
        normal = QTextCharFormat()
        normal.setForeground(QBrush(qcolor(Couleurs.TEXTE)))
        hesitation = QTextCharFormat()
        hesitation.setForeground(QBrush(qcolor(Couleurs.TEXTE_DESACTIVE)))
        hesitation.setFontStrikeOut(masquer)
        personne = QTextCharFormat()
        personne.setForeground(QBrush(qcolor(Couleurs.ACCENT_SURVOL)))
        personne.setFontWeight(QFont.Weight(Typo.GRAISSE_FORTE))
        plusieurs = len({m.locuteur for m in mots if m.locuteur}) > 1
        precedent = None
        for index, mot in enumerate(mots):
            if plusieurs and mot.locuteur and mot.locuteur != precedent:
                if index:
                    curseur.insertBlock()
                curseur.insertText(f"{nom_de_personne(mot.locuteur)} : ", personne)
                precedent = mot.locuteur
            elif index:
                curseur.insertText(" ", normal)
            self._debuts.append(curseur.position())
            curseur.insertText(mot.texte, hesitation if est_hesitation(mot, hesitations) else normal)
            self._fins.append(curseur.position())
        self._choisi = min(self._choisi, len(mots) - 1)
        self._lecture = -1
        self._surligner()
        self.verticalScrollBar().setValue(defilement)

    def mettre_en_lecture(self, index: int) -> None:
        """Mot en cours de lecture (-1 : aucun)."""
        if index == self._lecture:
            return
        self._lecture = index
        self._surligner()
        if index >= 0:
            self._rendre_visible(index)

    def choisir(self, index: int) -> None:
        """Mot choisi pour être corrigé (-1 : aucun)."""
        self._choisi = index
        self._surligner()
        if index >= 0:
            self._rendre_visible(index)

    @property
    def mot_choisi(self) -> int:
        return self._choisi

    def _selection(self, index: int, fond: str, opacite: float, texte: str | None = None):
        selection = QTextEdit.ExtraSelection()
        curseur = QTextCursor(self.document())
        curseur.setPosition(self._debuts[index])
        curseur.setPosition(self._fins[index], QTextCursor.MoveMode.KeepAnchor)
        selection.cursor = curseur
        format_selection = QTextCharFormat()
        format_selection.setBackground(QBrush(qcolor(fond, opacite)))
        if texte is not None:
            format_selection.setForeground(QBrush(qcolor(texte)))
        selection.format = format_selection
        return selection

    def _surligner(self) -> None:
        selections = []
        if 0 <= self._lecture < len(self._debuts):
            selections.append(self._selection(self._lecture, Couleurs.ACCENT, Opacites.TEINTE_SURVOL))
        if 0 <= self._choisi < len(self._debuts):
            selections.append(self._selection(self._choisi, Couleurs.ACCENT, 1.0, Couleurs.TEXTE))
        self.setExtraSelections(selections)

    def _rendre_visible(self, index: int) -> None:
        curseur = QTextCursor(self.document())
        curseur.setPosition(self._debuts[index])
        zone = self.cursorRect(curseur)
        if not self.viewport().rect().contains(zone):
            self.setTextCursor(curseur)
            self.ensureCursorVisible()

    # --- Clic sur un mot ---------------------------------------------------------------------

    def index_a(self, position: int) -> int:
        """Indice du mot à cette position du texte (-1 si c'est entre deux mots)."""
        index = bisect.bisect_right(self._debuts, position) - 1
        if 0 <= index < len(self._fins) and position <= self._fins[index]:
            return index
        return -1

    def mouseReleaseEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        super().mouseReleaseEvent(evenement)
        if evenement.button() != Qt.MouseButton.LeftButton or self.textCursor().hasSelection():
            return  # sélection d'un passage (pour le copier) : pas un clic sur un mot
        index = self.index_a(self.cursorForPosition(evenement.position().toPoint()).position())
        if index >= 0:
            self.mot_clique.emit(index)
