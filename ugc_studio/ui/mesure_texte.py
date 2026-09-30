"""Largeur réelle d'un sous-titre en pixels (§7.3), mesurée par Qt avec la police du texte.

V1 : police Inter SemiBold (celle de l'app), à la taille choisie dans les réglages des
sous-titres. Le style complet (police, graisse, contour…) arrive avec le Studio de style (V2) ;
la mesure utilisera alors la police choisie.
"""

from __future__ import annotations

from PySide6.QtGui import QFontMetricsF

from ..sous_titres import Ecran, Mesure
from .polices import police
from .theme import Typo


def mesure_sous_titres(ecran: Ecran) -> Mesure:
    """Fonction qui donne la largeur d'un texte, en pixels de la vidéo."""
    metriques = QFontMetricsF(police(max(1, round(ecran.taille_texte)), Typo.GRAISSE_FORTE))
    return metriques.horizontalAdvance
