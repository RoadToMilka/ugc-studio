"""Style des sous-titres (V2) : tout ce qui décide de leur apparence, rangé sous une forme écrite et
documentée (cahier des charges §7.4 et §7.9).

Ce fichier ne dépend pas de l'interface : il décrit le style ; le moteur de dessin
(rendu/moteur.py) le dessine.

- Toutes les tailles sont en **% de la hauteur de la vidéo** : un même style garde le même aspect
  dans tous les formats. L'interface les affiche en pixels de la vidéo actuelle.
- Les couleurs s'écrivent « #RRGGBB », avec une opacité de 0 à 100 %. Ce sont des choix de la
  vidéo (comme son texte), pas des couleurs de l'interface : elles ne sont donc pas dans theme.py.

Lot 3 (version 1.4.0) : texte (police, graisse, taille, casse, ponctuation, couleur, ombre) et
position (haut, centre ou bas, réglage fin, alignement, largeur des lignes). La police, la couleur
et l'ombre ne se règlent pas encore (lot 4) : leurs valeurs ci-dessous sont l'apparence de la V1
(Inter SemiBold, blanc, ombre légère), qui garde exactement le découpage d'un projet de la 1.1.0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields, is_dataclass, replace
from typing import ClassVar

_CODE_COULEUR = re.compile(r"#?([0-9A-Fa-f]{6})")


@dataclass(frozen=True)
class Couleur:
    """Couleur du style : rouge, vert, bleu (0 à 255) et opacité (0 à 100 %)."""

    rouge: int = 0
    vert: int = 0
    bleu: int = 0
    opacite: float = 100.0

    @property
    def code(self) -> str:
        """Code de la couleur, « #RRGGBB » en hexadécimal (sans l'opacité)."""
        return f"#{self.rouge:02X}{self.vert:02X}{self.bleu:02X}"

    def en_dict(self) -> dict:
        return {"code": self.code, "opacite": round(self.opacite, 1)}

    @classmethod
    def depuis(cls, brut) -> Couleur | None:
        """Couleur lue dans un projet ou un préréglage : {"code": "#RRGGBB", "opacite": 80}, ou
        simplement « #RRGGBB ». None si elle est illisible."""
        code, opacite = (brut.get("code"), brut.get("opacite", 100.0)) if isinstance(brut, dict) else (brut, 100.0)
        trouve = _CODE_COULEUR.fullmatch(code.strip()) if isinstance(code, str) else None
        if trouve is None:
            return None
        try:
            opacite = min(max(float(opacite), 0.0), 100.0)
        except (TypeError, ValueError):
            opacite = 100.0
        valeur = int(trouve.group(1), 16)
        return cls(valeur >> 16, (valeur >> 8) & 0xFF, valeur & 0xFF, opacite)


BLANC = Couleur(255, 255, 255)
NOIR = Couleur(0, 0, 0)

# Casse (§7.2) : le texte des mots ne change pas, seul l'affichage.
CASSE_NORMALE = "normale"
CASSE_MAJUSCULES = "majuscules"
CASSE_MINUSCULES = "minuscules"
CASSES = {CASSE_NORMALE: "Comme écrit", CASSE_MAJUSCULES: "TOUT EN MAJUSCULES", CASSE_MINUSCULES: "tout en minuscules"}

# Position verticale (§7.3, §7.4) : le point fixe du bloc est son haut, son milieu ou son bas.
HAUT, CENTRE, BAS = "haut", "centre", "bas"
POSITIONS = {HAUT: "Haut", CENTRE: "Centre", BAS: "Bas"}
GAUCHE, DROITE = "gauche", "droite"
ALIGNEMENTS = {GAUCHE: "Gauche", CENTRE: "Centre", DROITE: "Droite"}


@dataclass(frozen=True)
class Ombre:
    """Ombre portée par le texte : couleur, flou et décalage (en % de la hauteur de la vidéo)."""

    active: bool = True
    couleur: Couleur = Couleur(0, 0, 0, 55.0)
    flou_pct: float = 0.4  # 8 px dans une vidéo de 1920 px de haut
    decalage_x_pct: float = 0.0
    decalage_y_pct: float = 0.2  # 4 px vers le bas

    LIMITES: ClassVar[dict] = {"flou_pct": (0.0, 5.0), "decalage_x_pct": (-5.0, 5.0), "decalage_y_pct": (-5.0, 5.0)}


@dataclass(frozen=True)
class StyleTexte:
    """Ce qui vaut pour tous les mots (onglet « Texte »)."""

    police: str = "Inter"
    graisse: int = 600  # SemiBold
    taille_pct: float = 4.0  # taille du texte, en % de la hauteur de la vidéo
    casse: str = CASSE_NORMALE
    ponctuation: bool = True  # ponctuation affichée
    couleur: Couleur = BLANC
    ombre: Ombre = Ombre()

    LIMITES: ClassVar[dict] = {"graisse": (100, 900), "taille_pct": (1.0, 15.0)}
    CHOIX: ClassVar[dict] = {"casse": tuple(CASSES)}


@dataclass(frozen=True)
class Position:
    """Place des sous-titres à l'écran (onglet « Position »)."""

    verticale: str = BAS
    decalage_pct: float = 0.0  # réglage fin, en % de la hauteur : positif vers le bas
    alignement: str = CENTRE
    largeur_lignes_pct: float = 100.0  # largeur maximale des lignes, en % de la largeur utile

    LIMITES: ClassVar[dict] = {"decalage_pct": (-100.0, 100.0), "largeur_lignes_pct": (30.0, 100.0)}
    CHOIX: ClassVar[dict] = {"verticale": tuple(POSITIONS), "alignement": tuple(ALIGNEMENTS)}


def lire(classe, brut, base=None):
    """Instance de `classe` (une des classes de ce fichier) d'après un dictionnaire lu dans un projet
    ou un préréglage. Une valeur absente ou illisible garde celle de `base` (sinon celle par défaut) ;
    une valeur hors limites est ramenée dans les limites ; un choix inconnu est ignoré. Ainsi, un
    fichier plus ancien (ou écrit à la main) s'ouvre toujours."""
    objet = base if base is not None else classe()
    if not isinstance(brut, dict):
        return objet
    limites = getattr(classe, "LIMITES", {})
    choix = getattr(classe, "CHOIX", {})
    valeurs = {}
    for champ in fields(classe):
        if champ.name not in brut:
            continue
        valeur = _convertir(brut[champ.name], getattr(objet, champ.name))
        if valeur is None:
            continue
        if champ.name in limites:
            bas, haut = limites[champ.name]
            valeur = type(valeur)(min(max(valeur, bas), haut))
        if champ.name in choix and valeur not in choix[champ.name]:
            continue
        valeurs[champ.name] = valeur
    return replace(objet, **valeurs)


def _convertir(brut, defaut):
    """Valeur lue → même type que la valeur par défaut (None : illisible)."""
    try:
        if isinstance(defaut, bool):
            return bool(brut)
        if isinstance(defaut, int):
            return int(brut)
        if isinstance(defaut, float):
            valeur = float(brut)
            return valeur if valeur == valeur and abs(valeur) != float("inf") else None
        if isinstance(defaut, str):
            return str(brut) if isinstance(brut, str | int | float) else None
    except (TypeError, ValueError):
        return None
    if isinstance(defaut, Couleur):
        return Couleur.depuis(brut)
    if is_dataclass(defaut):
        return lire(type(defaut), brut, defaut) if isinstance(brut, dict) else None
    return None


def en_dict(objet) -> dict:
    """Forme écrite d'un élément du style (pour projet.json et, au lot 7, les préréglages exportés) :
    les couleurs en « #RRGGBB » avec leur opacité, les nombres arrondis."""
    resultat = {}
    for champ in fields(objet):
        valeur = getattr(objet, champ.name)
        if isinstance(valeur, Couleur):
            resultat[champ.name] = valeur.en_dict()
        elif is_dataclass(valeur):
            resultat[champ.name] = en_dict(valeur)
        elif isinstance(valeur, float):
            resultat[champ.name] = round(valeur, 3)
        else:
            resultat[champ.name] = valeur
    return resultat


@dataclass(frozen=True)
class VideoApercu:
    """Vidéo choisie seulement pour l'aperçu, pour un projet sans vidéo (sous-titres d'une prise de
    voix) : par exemple le montage exporté de Premiere Pro. Elle n'est pas copiée dans le projet."""

    chemin: str = ""
    decalage_s: float = 0.0  # moment de la vidéo où la voix commence
    largeur: int = 0  # sa résolution (lue quand elle est choisie) : elle fixe le format
    hauteur: int = 0
    son_de_la_video: bool = True  # sinon : la voix de la prise, la vidéo est muette

    LIMITES: ClassVar[dict] = {"decalage_s": (0.0, 3600.0), "largeur": (0, 16384), "hauteur": (0, 16384)}

    @property
    def resolution(self) -> tuple[int, int] | None:
        return (self.largeur, self.hauteur) if self.chemin and self.largeur > 0 and self.hauteur > 0 else None

