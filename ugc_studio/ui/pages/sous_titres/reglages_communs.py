"""Petits outils communs aux onglets du studio des sous-titres (V2) : réglages sous leur nom, un par
ligne (V3.2), nombres écrits à la française, et (V3.1) ce qui compare les réglages au préréglage du
projet : le nom d'un réglage qui s'en écarte passe en mauve, et le ↺ de son groupe apparaît."""

from __future__ import annotations

from dataclasses import is_dataclass

from PySide6.QtWidgets import QCheckBox, QLabel, QWidget

from ....style_sous_titres import Couleur, en_dict
from ...composants.elements import ChampNomme
from ...composants.flux import DispositionFlux
from ...theme import Espacements


def nombre_lisible(valeur: float, decimales: int = 1) -> str:
    """2.5 → « 2,5 » ; 3.0 → « 3 »."""
    texte = f"{valeur:.{decimales}f}".rstrip("0").rstrip(".")
    return texte.replace(".", ",").replace("-", "−") or "0"


class GrilleDeReglages(DispositionFlux):
    """Réglages sous leur nom (V3.1, §9.4 ter), **un par ligne** (V3.2) : la couleur d'un contour,
    puis son épaisseur dessous, et ainsi de suite ; 12 px entre deux réglages. On lit les réglages
    d'un effet de haut en bas, et la colonne de l'apparence peut être plus étroite. De la 3.0.1 à la
    3.1.3, ils étaient côte à côte et passaient à la ligne quand la place manquait ; jusqu'à la 3.0.0,
    le nom était à gauche de chaque champ. `champs` : nom → ChampNomme."""

    def __init__(self):
        super().__init__(espacement=Espacements.L, espacement_vertical=Espacements.M)
        self.champs: dict[str, ChampNomme] = {}

    def ajouter(
        self, nom: str | None, element, a_cote: QWidget | None = None, etire: bool = False, aide: str | None = None
    ) -> ChampNomme:
        """Un réglage sous son nom, sur sa propre ligne. `etire` : le champ prend toute la largeur (ex.
        une glissière) ; sinon, il garde sa largeur. `aide` : son explication, dans une icône « i »
        devant le nom (V3.1 ; après lui jusqu'à la 3.1.0)."""
        champ = ChampNomme(nom, element, a_cote=a_cote, etire=etire, aide=aide)
        self.ajouter_sur_toute_la_largeur(champ)  # une ligne par réglage (V3.2)
        if nom:
            self.champs[nom] = champ
        return champ


def grille(lignes, etirees: tuple[int, ...] = ()) -> GrilleDeReglages:
    """Réglages sous leur nom, un par ligne (voir GrilleDeReglages) : des couples (nom, champ), ou des
    triplets (nom, champ, aide) pour un réglage expliqué par une icône « i » ; le champ des lignes
    `etirees` prend toute la largeur (ex. une glissière)."""
    disposition = GrilleDeReglages()
    for rang, (texte, element, *aide) in enumerate(lignes):
        disposition.ajouter(texte, element, etire=rang in etirees, aide=aide[0] if aide else None)
    return disposition


# --- Comparaison avec le préréglage du projet (V3.1) -----------------------------------------------


def _forme(valeur):
    """Une valeur du style telle qu'elle s'écrit dans le projet (nombres à 3 chiffres après la
    virgule, couleurs « #RRGGBB » et opacité à 1 chiffre) : deux valeurs qui s'écrivent pareil sont
    la même valeur."""
    if isinstance(valeur, Couleur):
        return valeur.en_dict()
    if is_dataclass(valeur):
        return en_dict(valeur)
    if isinstance(valeur, float):
        return round(valeur, 3)
    return valeur


def meme_valeur(a, b) -> bool:
    """Deux valeurs du style identiques, à l'arrondi du projet près (None : « comme le texte »)."""
    return _forme(a) == _forme(b)


def valeur_au_chemin(objet, chemin: str):
    """La valeur au bout d'un chemin d'attributs (« contour.epaisseur_pct ») ; None si un maillon
    vaut None (« comme le texte »)."""
    for nom in chemin.split("."):
        if objet is None:
            return None
        objet = getattr(objet, nom)
    return objet


def marquer(element: QWidget | None, change: bool) -> None:
    """Un réglage qui s'écarte du préréglage : son nom en mauve (rôle « legende-modifiee » ; pour un
    effet qu'on coche, le texte de sa case à cocher, propriété « modifie »)."""
    if isinstance(element, QCheckBox):
        if (element.property("modifie") is True) != change:
            element.setProperty("modifie", change)
            element.style().unpolish(element)
            element.style().polish(element)
    elif isinstance(element, QLabel):
        role = "legende-modifiee" if change else "legende"
        if element.property("role") != role:
            element.setProperty("role", role)
            element.style().unpolish(element)
            element.style().polish(element)


def marque_de(champ: ChampNomme | QWidget) -> QWidget | None:
    """Ce qui passe en mauve pour un réglage : le nom d'un ChampNomme, sinon le texte de sa case à
    cocher (un effet qu'on coche se nomme lui-même)."""
    if isinstance(champ, QCheckBox):
        return champ
    if isinstance(champ, ChampNomme) and champ.nom is not None:
        return champ.nom
    return champ.findChild(QCheckBox)
