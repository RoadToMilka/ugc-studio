"""Petits outils communs aux onglets du studio des sous-titres (V2) : réglages sous leur nom, côte à
côte, et nombres écrits à la française."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from ...composants.elements import ChampNomme
from ...composants.flux import DispositionFlux
from ...theme import Espacements


def nombre_lisible(valeur: float, decimales: int = 1) -> str:
    """2.5 → « 2,5 » ; 3.0 → « 3 »."""
    texte = f"{valeur:.{decimales}f}".rstrip("0").rstrip(".")
    return texte.replace(".", ",").replace("-", "−") or "0"


class GrilleDeReglages(DispositionFlux):
    """Réglages sous leur nom (V3.1, §9.4 ter), côte à côte, qui passent à la ligne quand la place
    manque : 16 px entre deux réglages d'une rangée, 12 px entre deux rangées. Jusqu'à la 3.0.0, le
    nom était à gauche de chaque champ, un réglage par ligne. `champs` : nom → ChampNomme."""

    def __init__(self):
        super().__init__(espacement=Espacements.L, espacement_vertical=Espacements.M)
        self.champs: dict[str, ChampNomme] = {}

    def ajouter(self, nom: str | None, element, a_cote: QWidget | None = None, etire: bool = False) -> ChampNomme:
        """Un réglage sous son nom. `etire` : il prend une rangée à lui seul, sur toute la largeur (ex.
        une glissière) ; sans nom (ex. une case à cocher qui active les réglages suivants) aussi."""
        champ = ChampNomme(nom, element, a_cote=a_cote, etire=etire)
        if etire or nom is None:
            self.ajouter_sur_toute_la_largeur(champ)
        else:
            self.addWidget(champ)
        if nom:
            self.champs[nom] = champ
        return champ


def grille(lignes, etirees: tuple[int, ...] = ()) -> GrilleDeReglages:
    """Réglages sous leur nom, côte à côte (voir GrilleDeReglages) ; les lignes `etirees` prennent une
    rangée à elles seules, sur toute la largeur (ex. une glissière)."""
    disposition = GrilleDeReglages()
    for rang, (texte, element) in enumerate(lignes):
        disposition.ajouter(texte, element, etire=rang in etirees)
    return disposition
