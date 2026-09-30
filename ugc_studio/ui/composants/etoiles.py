"""Note d'une prise (§5.6) : cinq étoiles cliquables."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize

from ..icones import icone
from ..theme import Couleurs, Dimensions
from .bouton import Bouton
from .elements import bouton

NOTE_MAX = 5


def boutons_etoiles(note: int, noter: Callable[[int], None]) -> list[Bouton]:
    """Les cinq étoiles d'une note. Cliquer sur l'étoile de la note actuelle retire la note."""
    etoiles = []
    for rang in range(1, NOTE_MAX + 1):
        allumee = rang <= note
        etoile = bouton("", variante="icone")
        etoile.setIcon(
            icone("star", Couleurs.AVERTISSEMENT if allumee else Couleurs.TEXTE_DESACTIVE, rempli=allumee, taille=Dimensions.ETOILE)
        )
        etoile.setIconSize(QSize(Dimensions.ETOILE, Dimensions.ETOILE))
        etoile.setToolTip(f"Noter {rang}/{NOTE_MAX}")
        etoile.clicked.connect(lambda _c=False, r=rang: noter(0 if r == note else r))
        etoiles.append(etoile)
    return etoiles
