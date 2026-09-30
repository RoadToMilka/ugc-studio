"""MontantLabel : affichage d'un montant en euros au format du cahier des charges (§4.4).

Exemple : 0.0071 € s'affiche « 0.00 » en taille et couleur normales, puis « 71 » plus petit
(~70 %) et plus sombre, puis « € ».
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QFont, QFontMetricsF
from PySide6.QtWidgets import QLabel, QStyledItemDelegate

from ...montants import Montant, decouper_montant, en_decimal, formater_montant
from ..polices import police
from ..theme import COULEUR_PETITES_DECIMALES, RATIO_PETITES_DECIMALES, Couleurs, Dimensions, Espacements, Typo, qcolor


class MontantLabel(QLabel):
    def __init__(self, montant: Montant = 0, taille: int = Typo.COURANT, parent=None):
        super().__init__(parent)
        self._taille = taille
        self._montant = en_decimal(montant)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setProperty("role", "montant")
        self.definir_montant(montant)

    @property
    def montant(self):
        return self._montant

    def definir_montant(self, montant: Montant) -> None:
        self._montant = en_decimal(montant)
        principal, petites = decouper_montant(self._montant)
        petite_taille = round(self._taille * RATIO_PETITES_DECIMALES)
        # Texte « riche » (mini-HTML) : chaque morceau a sa propre taille (et couleur) de police.
        self.setText(
            f'<span style="font-size:{self._taille}px">{principal}</span>'
            f'<span style="font-size:{petite_taille}px; color:{COULEUR_PETITES_DECIMALES}">{petites}</span>'
            f'<span style="font-size:{self._taille}px">&nbsp;€</span>'
        )
        self.setAccessibleName(formater_montant(self._montant))


ROLE_MONTANT = Qt.ItemDataRole.UserRole + 1  # montant d'une case de tableau (texte décimal, ou vide : prix inconnu)
PRIX_INCONNU = "prix inconnu"


class DelegueMontant(QStyledItemDelegate):
    """Montant dans une case de tableau, au même format que MontantLabel (§4.4), aligné à droite.

    Pourquoi pas un MontantLabel dans chaque case ? Sa largeur n'était connue qu'une fois affiché :
    le tableau calculait trop court et le montant était coupé à droite. Ici, le montant est mesuré
    avec les polices qui le dessinent : la colonne a toujours la bonne largeur."""

    def __init__(self, parent=None, taille: int = Typo.COURANT):
        super().__init__(parent)
        self._normale = police(taille, Typo.GRAISSE_FORTE)
        self._petite = police(round(taille * RATIO_PETITES_DECIMALES), Typo.GRAISSE_FORTE)

    def _morceaux(self, index) -> list[tuple[str, QFont, str]]:
        """(texte, police, couleur) de chaque morceau, de gauche à droite."""
        brut = index.data(ROLE_MONTANT)
        if not brut:
            return [(PRIX_INCONNU, police(Typo.COURANT), Couleurs.AVERTISSEMENT)]
        principal, petites = decouper_montant(str(brut))
        return [
            (principal, self._normale, Couleurs.TEXTE),
            (petites, self._petite, COULEUR_PETITES_DECIMALES),
            (" €", self._normale, Couleurs.TEXTE),
        ]

    @staticmethod
    def _largeur(morceaux) -> float:
        return sum(QFontMetricsF(police_morceau).horizontalAdvance(texte) for texte, police_morceau, _c in morceaux)

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 — nom imposé par Qt
        taille = super().sizeHint(option, index)
        largeur = math.ceil(self._largeur(self._morceaux(index))) + 2 * Espacements.M + Dimensions.BORDURE
        return QSize(max(taille.width(), largeur), taille.height())

    def paint(self, peintre, option, index) -> None:
        super().paint(peintre, option, index)  # fond, sélection et trait du bas (la case n'a pas de texte)
        morceaux = self._morceaux(index)
        zone = option.rect.adjusted(Espacements.M, 0, -Espacements.M, 0)
        x = zone.right() + 1 - self._largeur(morceaux)
        mesures = QFontMetricsF(self._normale)
        ligne_de_base = zone.center().y() + (mesures.ascent() - mesures.descent()) / 2
        peintre.save()
        for texte, police_morceau, couleur in morceaux:
            peintre.setFont(police_morceau)
            peintre.setPen(qcolor(couleur))
            peintre.drawText(QPointF(x, ligne_de_base), texte)
            x += QFontMetricsF(police_morceau).horizontalAdvance(texte)
        peintre.restore()
