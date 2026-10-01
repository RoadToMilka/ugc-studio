"""Style des sous-titres (V2) : tout ce qui décide de leur apparence, rangé sous une forme écrite et
documentée (cahier des charges §7.4 et §7.9).

Ce fichier ne dépend pas de l'interface : il décrit le style ; le moteur de dessin
(rendu/moteur.py) le dessine.

- Toutes les tailles sont en **% de la hauteur de la vidéo** : un même style garde le même aspect
  dans tous les formats. L'interface les affiche en pixels de la vidéo actuelle.
- Les couleurs s'écrivent « #RRGGBB », avec une opacité de 0 à 100 %. Ce sont des choix de la
  vidéo (comme son texte), pas des couleurs de l'interface : elles ne sont donc pas dans theme.py.

Lot 3 (version 1.4.0) : texte (police, graisse, taille, casse, ponctuation, couleur, ombre) et
position (haut, centre ou bas, réglage fin, alignement, largeur des lignes).
Lot 4 (version 1.5.0) : tout le style du texte se règle (dégradé, contour, ombre, lueur, fond,
espaces). Les valeurs par défaut ci-dessous restent l'apparence de la V1 (Inter SemiBold, blanc,
ombre légère, sans contour ni fond) : un projet plus ancien, à qui il manque ces réglages, garde
exactement son apparence et son découpage. Un nouveau projet prend le style de départ
(style_de_depart.json : Montserrat ExtraBold, blanc, contour noir).
Lot 5 (version 1.6.0) : les mots (onglet « Mots ») : trois états (à venir, actif, déjà dits), plus
les mots accentués du script, chacun avec ses propres réglages ; un réglage d'un état laissé vide
(None) vaut « comme le texte ».
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields, is_dataclass, replace
from typing import ClassVar

from .chemins import dossier_ressources
from .stockage import lire_json

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


# Remplissage en dégradé, contour, ombre, lueur, fond (lot 4, §7.4).
DIRECTIONS = {"vertical": "Vertical", "horizontal": "Horizontal", "biais": "En biais"}
ANGLES = {"arrondis": "Arrondis", "nets": "Nets"}
PORTEES = {"texte": "Par le texte", "fond": "Par le fond"}
FOND_AUCUN, FOND_MOT, FOND_LIGNE, FOND_BLOC = "aucun", "mot", "ligne", "bloc"
FONDS = {
    FOND_AUCUN: "Aucun",
    FOND_MOT: "Derrière chaque mot",
    FOND_LIGNE: "Derrière chaque ligne",
    FOND_BLOC: "Un seul bloc",
}


@dataclass(frozen=True)
class Degrade:
    """Remplissage en dégradé de deux couleurs : celle du texte, puis `couleur` (sur chaque ligne)."""

    actif: bool = False
    couleur: Couleur = Couleur(250, 204, 21)
    direction: str = "vertical"

    CHOIX: ClassVar[dict] = {"direction": tuple(DIRECTIONS)}


@dataclass(frozen=True)
class Contour:
    """Contour dessiné autour des lettres (pas à moitié dedans : elles gardent leur épaisseur)."""

    actif: bool = False
    couleur: Couleur = NOIR
    epaisseur_pct: float = 0.3  # 6 px dans une vidéo de 1920 px de haut
    angles: str = "arrondis"

    LIMITES: ClassVar[dict] = {"epaisseur_pct": (0.0, 3.0)}
    CHOIX: ClassVar[dict] = {"angles": tuple(ANGLES)}


@dataclass(frozen=True)
class Ombre:
    """Ombre portée par le texte (ou par son fond) : couleur, flou et décalage (en % de la hauteur)."""

    active: bool = True
    couleur: Couleur = Couleur(0, 0, 0, 55.0)
    flou_pct: float = 0.4  # 8 px dans une vidéo de 1920 px de haut
    decalage_x_pct: float = 0.0
    decalage_y_pct: float = 0.2  # 4 px vers le bas
    portee: str = "texte"

    LIMITES: ClassVar[dict] = {"flou_pct": (0.0, 5.0), "decalage_x_pct": (-5.0, 5.0), "decalage_y_pct": (-5.0, 5.0)}
    CHOIX: ClassVar[dict] = {"portee": tuple(PORTEES)}


@dataclass(frozen=True)
class Lueur:
    """Halo lumineux autour des lettres."""

    active: bool = False
    couleur: Couleur = Couleur(245, 158, 11)
    taille_pct: float = 1.0  # 19 px dans une vidéo de 1920 px de haut
    intensite_pct: float = 80.0

    LIMITES: ClassVar[dict] = {"taille_pct": (0.0, 5.0), "intensite_pct": (0.0, 100.0)}


@dataclass(frozen=True)
class Fond:
    """Fond derrière le texte : derrière chaque mot, chaque ligne, ou un seul bloc."""

    mode: str = FOND_AUCUN
    couleur: Couleur = Couleur(0, 0, 0, 60.0)
    marge_x_pct: float = 0.8  # marge intérieure à gauche et à droite (15 px en 1920)
    marge_y_pct: float = 0.3  # en haut et en bas
    arrondi_pct: float = 0.6
    bordure: bool = False
    bordure_couleur: Couleur = BLANC
    bordure_epaisseur_pct: float = 0.15

    LIMITES: ClassVar[dict] = {
        "marge_x_pct": (0.0, 5.0), "marge_y_pct": (0.0, 5.0), "arrondi_pct": (0.0, 5.0), "bordure_epaisseur_pct": (0.0, 2.0),
    }
    CHOIX: ClassVar[dict] = {"mode": tuple(FONDS)}

    @property
    def visible(self) -> bool:
        return self.mode != FOND_AUCUN


@dataclass(frozen=True)
class Espaces:
    """Interlignage (en % de celui de la police), espace entre les lettres et entre les mots (en %
    de la hauteur de la vidéo, ajouté à l'espace normal ; négatif : plus serré)."""

    interligne_pct: float = 100.0
    lettres_pct: float = 0.0
    mots_pct: float = 0.0

    LIMITES: ClassVar[dict] = {"interligne_pct": (50.0, 250.0), "lettres_pct": (-1.0, 3.0), "mots_pct": (-1.0, 5.0)}


@dataclass(frozen=True)
class StyleTexte:
    """Ce qui vaut pour tous les mots (onglet « Texte »). Police, graisse, taille et espaces sont les
    mêmes pour tous les mots d'un sous-titre : sinon, les mots bougeraient pendant la lecture."""

    police: str = "Inter"
    graisse: int = 600  # SemiBold
    taille_pct: float = 4.0  # taille du texte, en % de la hauteur de la vidéo
    casse: str = CASSE_NORMALE
    ponctuation: bool = True  # ponctuation affichée
    couleur: Couleur = BLANC
    degrade: Degrade = Degrade()
    contour: Contour = Contour()
    ombre: Ombre = Ombre()
    lueur: Lueur = Lueur()
    fond: Fond = Fond()
    espaces: Espaces = Espaces()

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
    fichier plus ancien (ou écrit à la main) s'ouvre toujours. Un champ qui vaut None par défaut
    (« comme le texte », états des mots) est lu d'après son type, donné par TYPES."""
    objet = base if base is not None else classe()
    if not isinstance(brut, dict):
        return objet
    limites = getattr(classe, "LIMITES", {})
    choix = getattr(classe, "CHOIX", {})
    types = getattr(classe, "TYPES", {})
    valeurs = {}
    for champ in fields(classe):
        if champ.name not in brut:
            continue
        defaut = getattr(objet, champ.name)
        if defaut is None and champ.name in types:
            defaut = types[champ.name]()  # lu comme une valeur de ce type (ex. une couleur)
        valeur = _convertir(brut[champ.name], defaut)
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


# --- Mots (lot 5, §7.5) : trois états, plus les mots accentués du script ---------------------

A_VENIR, ACTIF, DITS, ACCENTUES = "a_venir", "actif", "dits", "accentues"
ETATS = {A_VENIR: "À venir", ACTIF: "Mot actif", DITS: "Déjà dits", ACCENTUES: "Accentués"}


@dataclass(frozen=True)
class FondMot:
    """Fond surligné derrière un mot (d'un état des mots). Pour le mot actif, il peut glisser d'un
    mot à l'autre (sur une même ligne)."""

    couleur: Couleur = Couleur(124, 58, 237)
    marge_x_pct: float = 0.94  # 18 px en 1920
    marge_y_pct: float = 0.16  # 3 px
    arrondi_pct: float = 1.25  # 24 px
    glisse: bool = False
    duree_glisse_ms: int = 140

    LIMITES: ClassVar[dict] = {
        "marge_x_pct": (0.0, 5.0), "marge_y_pct": (0.0, 5.0), "arrondi_pct": (0.0, 5.0), "duree_glisse_ms": (0, 1000),
    }


@dataclass(frozen=True)
class Soulignement:
    """Trait sous le mot : couleur, épaisseur, distance sous la ligne de base (en % de la hauteur)."""

    couleur: Couleur = BLANC
    epaisseur_pct: float = 0.25  # 5 px en 1920
    distance_pct: float = 0.35  # 7 px

    LIMITES: ClassVar[dict] = {"epaisseur_pct": (0.05, 2.0), "distance_pct": (-2.0, 3.0)}


@dataclass(frozen=True)
class EtatMot:
    """Apparence d'un état des mots. Chaque réglage laissé à None vaut « comme le texte » (onglet
    Texte) : opacité 100 %, taille 100 %, sans décalage, sans fond surligné ni soulignement. Un mot
    invisible garde sa place (rien ne bouge pendant la lecture)."""

    visible: bool = True
    opacite_pct: float | None = None
    couleur: Couleur | None = None
    degrade: Degrade | None = None
    contour: Contour | None = None
    lueur: Lueur | None = None
    fond: FondMot | None = None
    soulignement: Soulignement | None = None
    taille_pct: float | None = None  # agrandissement autour du centre du mot (100 : comme le texte)
    decalage_y_pct: float | None = None  # vers le bas (négatif : vers le haut)

    TYPES: ClassVar[dict] = {
        "opacite_pct": float, "couleur": Couleur, "degrade": Degrade, "contour": Contour, "lueur": Lueur,
        "fond": FondMot, "soulignement": Soulignement, "taille_pct": float, "decalage_y_pct": float,
    }
    LIMITES: ClassVar[dict] = {"opacite_pct": (0.0, 100.0), "taille_pct": (50.0, 200.0), "decalage_y_pct": (-5.0, 5.0)}

    @property
    def change(self) -> bool:
        """Au moins un réglage qui n'est pas « comme le texte » ?"""
        return self != EtatMot()

    @property
    def echelle(self) -> float:
        return (self.taille_pct if self.taille_pct is not None else 100.0) / 100

    @property
    def opacite(self) -> float:
        return (self.opacite_pct if self.opacite_pct is not None else 100.0) / 100

    @property
    def decalage_pct(self) -> float:
        return self.decalage_y_pct or 0.0


RACCOURCI_FIXE, RACCOURCI_SURLIGNAGE, RACCOURCI_KARAOKE = "fixe", "surlignage", "karaoke"
RACCOURCI_APPARITION, RACCOURCI_MOT_PAR_MOT = "apparition", "mot_par_mot"
RACCOURCIS = {
    RACCOURCI_FIXE: "Sous-titre fixe",
    RACCOURCI_SURLIGNAGE: "Surlignage",
    RACCOURCI_KARAOKE: "Karaoké",
    RACCOURCI_APPARITION: "Apparition",
    RACCOURCI_MOT_PAR_MOT: "Mot par mot",
}
JAUNE_ACTIF = Couleur(255, 212, 59)  # « Blanc contour noir » (annexe B du document V2)
JAUNE_KARAOKE = Couleur(250, 204, 21)


@dataclass(frozen=True)
class Mots:
    """Onglet « Mots » : l'apparence des mots à venir, du mot actif (en train d'être dit), des mots
    déjà dits et, si `accentues_actifs`, des mots accentués du script d'une prise ; `avance_ms` :
    les mots s'allument un peu plus tôt (positif) ou plus tard à l'écran (leur moment ne change pas)."""

    a_venir: EtatMot = EtatMot()
    actif: EtatMot = EtatMot()
    dits: EtatMot = EtatMot()
    accentues_actifs: bool = False
    accentues: EtatMot = EtatMot(couleur=JAUNE_ACTIF)
    avance_ms: int = 0

    LIMITES: ClassVar[dict] = {"avance_ms": (-200, 200)}

    def etat(self, nom: str) -> EtatMot:
        return getattr(self, nom)

    @property
    def fixe(self) -> bool:
        """Aucun état ne change l'apparence des mots : le sous-titre est dessiné d'un bloc."""
        return not (self.a_venir.change or self.actif.change or self.dits.change or self.accentues_actifs)


def etats_du_raccourci(nom: str) -> dict[str, EtatMot]:
    """Ce qu'un raccourci met dans les trois états (à venir, actif, déjà dits)."""
    a_venir = actif = dits = EtatMot()
    if nom == RACCOURCI_SURLIGNAGE:
        actif = EtatMot(couleur=JAUNE_ACTIF, taille_pct=108.0)
    elif nom == RACCOURCI_KARAOKE:
        actif = EtatMot(couleur=JAUNE_KARAOKE, taille_pct=106.0)
        dits = EtatMot(couleur=JAUNE_KARAOKE)
    elif nom == RACCOURCI_APPARITION:
        a_venir = EtatMot(visible=False)
    elif nom == RACCOURCI_MOT_PAR_MOT:
        a_venir = dits = EtatMot(visible=False)
    return {A_VENIR: a_venir, ACTIF: actif, DITS: dits}


def appliquer_raccourci(mots: Mots, nom: str) -> Mots:
    """Un raccourci remplit les trois états ; tout reste modifiable ensuite (accentués et avance
    de l'allumage ne changent pas)."""
    return replace(mots, **etats_du_raccourci(nom))


def raccourci_de(mots: Mots) -> str | None:
    """Le raccourci dont les états sont exactement ceux-ci (None : réglages personnalisés)."""
    for nom in RACCOURCIS:
        if {A_VENIR: mots.a_venir, ACTIF: mots.actif, DITS: mots.dits} == etats_du_raccourci(nom):
            return nom
    return None


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


FICHIER_STYLE_DE_DEPART = "style_de_depart.json"


def style_de_depart() -> StyleTexte:
    """Style du texte des nouveaux projets (lot 4) : ressources/style_de_depart.json (Montserrat
    ExtraBold, blanc, contour noir). Un fichier illisible donne l'apparence de la V1."""
    brut = lire_json(dossier_ressources() / FICHIER_STYLE_DE_DEPART, {})
    return lire(StyleTexte, brut.get("texte") if isinstance(brut, dict) else None)
