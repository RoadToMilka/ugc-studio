"""Studio sous-titres (§7) : des mots horodatés aux sous-titres, puis au fichier SRT (§8.1).

1. Texte affiché (§7.2) : sans les hésitations (si l'option est cochée), ponctuation affichée ou
   masquée, typographie de la langue (français : espace insécable avant « ! ? : ; »), « Tout en
   majuscules » en option. Les temps des mots ne changent pas.
2. Découpage (§7.3) : les mots sont regroupés en sous-titres qui respectent les nombres maximum
   de caractères, de mots et de lignes. Parmi tous les découpages possibles, l'app retient celui
   qui donne des sous-titres bien remplis et équilibrés, en coupant de préférence après une
   ponctuation. Une fin de phrase, un changement de personne ou un long silence terminent
   toujours un sous-titre. Un mot n'est jamais coupé en deux.
3. Écran (§7.3) : la largeur de chaque ligne est mesurée en pixels, avec la police et la taille
   du texte. Elle doit tenir dans la zone de sécurité de la plateforme ; sinon elle peut
   déborder dans la marge, jusqu'à la marge maximum, jamais au-delà (le sous-titre est alors
   redécoupé). Seul un mot affiché seul et trop large est rapetissé : il est signalé en orange.
4. Temps : un sous-titre va du début de son premier mot à la fin du dernier, dure au moins la
   durée minimale (prolongé sans chevaucher le suivant), et les petits trous entre deux
   sous-titres sont comblés (pas de clignotement).
5. Réorganisation à la main (V1.1) : monter le premier mot au sous-titre précédent, descendre le
   dernier au suivant, couper, fusionner. Chaque sous-titre ajusté garde ses mots quand les
   réglages changent ; le reste est redécoupé autour de lui. Les mêmes règles s'appliquent (une
   action qui ne les respecte pas est refusée, avec la raison), et le temps des mots ne change
   jamais.

Ce module ne dépend pas de l'interface : la largeur d'un texte en pixels est mesurée par une
fonction fournie (le moteur de dessin dans l'app, rendu/moteur.py ; une règle simple dans les tests).

V2, lot 3 : le style (police, taille, casse, ponctuation, couleur, ombre) et la position sont décrits
dans style_sous_titres.py ; la largeur utile d'une ligne dépend de l'alignement et de la largeur
maximale des lignes ; format personnalisé ; projet au format 7 (forme écrite documentée, §7.9).
"""

from __future__ import annotations

import bisect
import math
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, fields
from pathlib import Path

from .style_sous_titres import (
    CASSE_MAJUSCULES,
    CASSE_MINUSCULES,
    CENTRE,
    DROITE,
    GAUCHE,
    Position,
    StyleTexte,
    VideoApercu,
    en_dict,
    lire,
)
from .transcription import PONCTUATION, Mot, mots_affiches

Mesure = Callable[[str], float]  # largeur d'un texte, en pixels, à la taille normale du texte

# --- Formats de vidéo (§7.1) -------------------------------------------------------------------

FORMAT_AUTO = "auto"  # celui de la vidéo, sinon 9:16 (valeur des projets de la V1)
FORMAT_PERSONNALISE = "personnalise"  # largeur × hauteur choisies (V2)
FORMATS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "4:5": (1080, 1350),
    "3:4": (1080, 1440),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}
FORMAT_PAR_DEFAUT = "9:16"
# Formats proposés quand aucune vidéo n'impose le sien (avec une vidéo, la liste est grisée).
NOMS_FORMATS = {
    "9:16": "9:16 (TikTok, Reels, Snap, Shorts)",
    "4:5": "4:5 (fil Facebook, Instagram)",
    "3:4": "3:4",
    "1:1": "1:1 (carré)",
    "16:9": "16:9 (horizontal)",
    FORMAT_PERSONNALISE: "Personnalisé",
}
COTE_MIN, COTE_MAX = 240, 4096  # format personnalisé : de 240 à 4 096 px de côté


def cote_pair(valeur: float) -> int:
    """Côté d'un format personnalisé : entier pair entre 240 et 4 096 px (la plupart des formats
    vidéo exigent des dimensions paires)."""
    return int(min(max(math.floor(valeur / 2 + 0.5) * 2, COTE_MIN), COTE_MAX))  # 1081 → 1082


# --- Zones de sécurité des plateformes (§7.3) ---------------------------------------------------


@dataclass(frozen=True)
class Plateforme:
    """Zone de sécurité : les bords de l'écran que l'interface de la plateforme recouvre (nom du
    compte, légende, boutons…). En part de la largeur (côtés) et de la hauteur (haut, bas)."""

    identifiant: str
    nom: str
    gauche: float
    droite: float
    haut: float
    bas: float
    source: str = ""


PLATEFORMES = (
    Plateforme(
        "tiktok", "TikTok", 120 / 1080, 120 / 1080, 240 / 1920, 660 / 1920,
        "modèle de zone de sécurité de TikTok Ads (avril 2025)",
    ),
    Plateforme(
        "meta", "Instagram, Facebook (Reels, Stories)", 0.06, 0.06, 0.14, 0.35,
        "guide des publicités Meta",
    ),
    Plateforme("youtube", "YouTube Shorts", 0.0, 0.10, 0.10, 0.25, "Google Ads, emplacement Shorts"),
    Plateforme(
        "snapchat", "Snapchat", 40 / 1080, 40 / 1080, 200 / 1920, 370 / 1920,
        "valeurs courantes, non confirmées par Snapchat",
    ),
    Plateforme("aucune", "Aucune (marge maximum seulement)", 0.0, 0.0, 0.0, 0.0),
)
PLATEFORME_PAR_DEFAUT = "tiktok"


def plateforme(identifiant: str) -> Plateforme:
    return next((p for p in PLATEFORMES if p.identifiant == identifiant), PLATEFORMES[0])


# --- Réglages -----------------------------------------------------------------------------------

LIGNES_POSSIBLES = (1, 2)
LIMITES: dict[str, tuple] = {  # valeurs permises (champs de la page Sous-titres, relecture d'un projet)
    "caracteres_max": (8, 120),
    "mots_max": (1, 20),
    "lignes_max": (1, 2),
    "duree_min_s": (0.0, 5.0),
    "marge_max_pct": (0.0, 20.0),
    "taille_pct": StyleTexte.LIMITES["taille_pct"],
    "largeur_lignes_pct": Position.LIMITES["largeur_lignes_pct"],
    "largeur_perso": (COTE_MIN, COTE_MAX),
    "hauteur_perso": (COTE_MIN, COTE_MAX),
}
_DECOUPAGE = ("caracteres_max", "mots_max", "lignes_max", "couper_sur_ponctuation", "duree_min_s")


@dataclass
class ReglagesSousTitres:
    """Réglages des sous-titres du projet (§7), enregistrés dans projet.json.

    - Découpage (§7.3) : caractères, mots et lignes au plus, coupure sur la ponctuation, durée minimale.
    - Style : texte (§7.4, style_sous_titres.StyleTexte) et position (onglet « Position »).
    - Écran (§7.1, §7.3) : format, zone de sécurité de la plateforme, marge maximum.
    - Vidéo choisie seulement pour l'aperçu (projet sans vidéo).

    Dans projet.json (format 7), ils sont rangés en trois parties : « style » (texte, position,
    découpage : le contenu d'un préréglage, lot 7), « ecran » et « apercu » (voir en_dict)."""

    caracteres_max: int = 24  # par sous-titre, espaces comprises
    mots_max: int = 5
    lignes_max: int = 2
    couper_sur_ponctuation: bool = True
    duree_min_s: float = 0.6
    texte: StyleTexte = StyleTexte()
    position: Position = Position()
    format: str = FORMAT_AUTO
    largeur_perso: int = 1080  # format personnalisé
    hauteur_perso: int = 1920
    plateforme: str = PLATEFORME_PAR_DEFAUT
    marge_max_pct: float = 5.0  # de chaque bord : le texte ne la dépasse jamais
    apercu: VideoApercu = VideoApercu()

    def en_dict(self) -> dict:
        """Forme écrite documentée (format 7 des projets, §7.9 du cahier des charges)."""
        return {
            "style": {
                "texte": en_dict(self.texte),
                "position": en_dict(self.position),
                "decoupage": {nom: getattr(self, nom) for nom in _DECOUPAGE},
            },
            "ecran": {
                "format": self.format,
                "largeur": self.largeur_perso,
                "hauteur": self.hauteur_perso,
                "plateforme": self.plateforme,
                "marge_max_pct": self.marge_max_pct,
            },
            "apercu": en_dict(self.apercu),
        }

    @classmethod
    def depuis_dict(cls, brut) -> ReglagesSousTitres:
        """Réglages lus dans un projet : une valeur absente ou illisible garde sa valeur par
        défaut ; une valeur hors limites est ramenée dans les limites. Lit le format 7 (style,
        écran, aperçu) comme les formats 4 à 6 (une seule liste de réglages, sans style ni position :
        l'apparence de la V1, qui garde exactement le découpage)."""
        reglages = cls()
        if not isinstance(brut, dict):
            return reglages
        if isinstance(brut.get("style"), dict) or isinstance(brut.get("ecran"), dict):
            style = brut.get("style") if isinstance(brut.get("style"), dict) else {}
            ecran_brut = brut.get("ecran") if isinstance(brut.get("ecran"), dict) else {}
            plats = dict(style.get("decoupage") or {}) if isinstance(style.get("decoupage"), dict) else {}
            plats.update({
                "format": ecran_brut.get("format"),
                "largeur_perso": ecran_brut.get("largeur"),
                "hauteur_perso": ecran_brut.get("hauteur"),
                "plateforme": ecran_brut.get("plateforme"),
                "marge_max_pct": ecran_brut.get("marge_max_pct"),
            })
            reglages = _lire_plats(reglages, {cle: valeur for cle, valeur in plats.items() if valeur is not None})
            reglages.texte = lire(StyleTexte, style.get("texte"))
            reglages.position = lire(Position, style.get("position"))
            reglages.apercu = lire(VideoApercu, brut.get("apercu"))
        else:
            # Formats 4 à 6 : « Tout en majuscules », ponctuation et taille passent dans le style du texte.
            reglages = _lire_plats(reglages, brut)
            texte = {"ponctuation": brut.get("ponctuation"), "taille_pct": brut.get("taille_pct")}
            if brut.get("majuscules"):
                texte["casse"] = CASSE_MAJUSCULES
            reglages.texte = lire(StyleTexte, {cle: valeur for cle, valeur in texte.items() if valeur is not None})
        if reglages.format not in (FORMAT_AUTO, FORMAT_PERSONNALISE, *FORMATS):
            reglages.format = FORMAT_AUTO
        if reglages.plateforme not in {p.identifiant for p in PLATEFORMES}:
            reglages.plateforme = PLATEFORME_PAR_DEFAUT
        reglages.largeur_perso, reglages.hauteur_perso = cote_pair(reglages.largeur_perso), cote_pair(reglages.hauteur_perso)
        return reglages


def _lire_plats(reglages: ReglagesSousTitres, brut: dict) -> ReglagesSousTitres:
    """Réglages simples (nombres, cases, textes) : valeur convertie, ramenée dans les limites."""
    for champ in fields(ReglagesSousTitres):
        if champ.name not in brut or champ.name in ("texte", "position", "apercu"):
            continue
        defaut = getattr(reglages, champ.name)
        try:
            if isinstance(defaut, bool):
                valeur = bool(brut[champ.name])
            elif isinstance(defaut, int):
                valeur = int(brut[champ.name])
            elif isinstance(defaut, float):
                valeur = float(brut[champ.name])
            else:
                valeur = str(brut[champ.name])
        except (TypeError, ValueError):
            continue
        if champ.name in LIMITES:
            bas, haut = LIMITES[champ.name]
            valeur = type(defaut)(min(max(valeur, bas), haut))
        setattr(reglages, champ.name, valeur)
    return reglages


# --- Écran ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Ecran:
    """Dimensions utiles pour vérifier la largeur des sous-titres (en pixels de la vidéo)."""

    largeur: int
    hauteur: int
    taille_texte: float  # taille du texte (px)
    largeur_securite: float  # largeur d'une ligne dans la zone de sécurité (limite souple)
    largeur_max: float  # largeur d'une ligne jusqu'à la marge maximum (limite stricte)


def resolution(reglages: ReglagesSousTitres, resolution_source: tuple[int, int] | None = None) -> tuple[int, int]:
    """Largeur × hauteur de la vidéo (§7.1). Une vidéo (celle du projet, ou celle choisie pour
    l'aperçu) impose la sienne : l'overlay de la V3 doit avoir sa taille exacte. Sinon le format
    choisi (« auto », valeur des projets de la V1 : 9:16), ou le format personnalisé."""
    if resolution_source:
        return resolution_source
    if reglages.format == FORMAT_PERSONNALISE:
        return reglages.largeur_perso, reglages.hauteur_perso
    return FORMATS.get(reglages.format, FORMATS[FORMAT_PAR_DEFAUT])


@dataclass(frozen=True)
class Cadre:
    """Où un sous-titre peut se placer, en pixels de la vidéo (§7.3, §7.4) : la zone de sécurité de
    la plateforme, la marge maximum, et la ligne de départ selon l'alignement."""

    largeur: int
    hauteur: int
    marge_x: float  # marge maximum à gauche et à droite
    marge_y: float  # en haut et en bas
    securite_gauche: float  # bords de la zone de sécurité
    securite_droite: float
    securite_haut: float
    securite_bas: float
    alignement: str
    x_depart: float  # gauche : début des lignes ; droite : leur fin ; centre : le milieu de l'écran
    largeur_securite: float  # largeur d'une ligne dans la zone de sécurité (limite souple)
    largeur_max: float  # largeur d'une ligne jusqu'à la marge maximum (limite stricte)


def cadre(reglages: ReglagesSousTitres, largeur: int, hauteur: int) -> Cadre:
    """Largeur utile d'une ligne selon l'alignement (§7.4) :
    - centre : la zone de sécurité retient le plus large des deux côtés (comme en V1) ;
    - gauche ou droite : les vrais côtés (la ligne part du bord de la zone, jamais de la marge) ;
    puis la largeur maximale des lignes (en % de cette largeur utile) la réduit."""
    zone = plateforme(reglages.plateforme)
    marge_x = largeur * reglages.marge_max_pct / 100
    marge_y = hauteur * reglages.marge_max_pct / 100
    gauche, droite = largeur * zone.gauche, largeur * (1 - zone.droite)
    haut, bas = hauteur * zone.haut, hauteur * (1 - zone.bas)
    alignement = reglages.position.alignement
    if alignement == GAUCHE:
        x_depart = max(gauche, marge_x)
        securite = min(droite, largeur - marge_x) - x_depart
        maximum = largeur - marge_x - x_depart
    elif alignement == DROITE:
        x_depart = min(droite, largeur - marge_x)
        securite = x_depart - max(gauche, marge_x)
        maximum = x_depart - marge_x
    else:
        x_depart = largeur / 2
        maximum = largeur * (1 - 2 * reglages.marge_max_pct / 100)
        # Sous-titres centrés : un côté plus large que l'autre réduit d'autant les deux côtés.
        securite = min(maximum, largeur * (1 - 2 * max(zone.gauche, zone.droite)))
    part = reglages.position.largeur_lignes_pct / 100
    return Cadre(
        largeur, hauteur, marge_x, marge_y, gauche, droite, haut, bas, alignement if alignement in (GAUCHE, DROITE) else CENTRE,
        x_depart, max(0.0, securite) * part, max(0.0, maximum) * part,
    )


def ecran(reglages: ReglagesSousTitres, resolution_source: tuple[int, int] | None = None) -> Ecran:
    largeur, hauteur = resolution(reglages, resolution_source)
    zone = cadre(reglages, largeur, hauteur)
    return Ecran(largeur, hauteur, hauteur * reglages.texte.taille_pct / 100, zone.largeur_securite, zone.largeur_max)


# --- Texte affiché (§7.2) -----------------------------------------------------------------------

ESPACE_INSECABLE = " "
FINS_DE_PHRASE = ".!?…"
PONCTUATION_DE_COUPURE = ",;:" + FINS_DE_PHRASE
FERMANTES = "»”’\"')]}"
OUVRANTES = "«“‘„([{¿¡"


def _fin_sans_fermantes(texte: str) -> str:
    return texte.rstrip(FERMANTES + " " + ESPACE_INSECABLE)


def finit_une_phrase(texte: str) -> bool:
    """« pas… », « semaines ! », « dessous.» » terminent une phrase."""
    fin = _fin_sans_fermantes(texte)
    return bool(fin) and fin[-1] in FINS_DE_PHRASE


def finit_par_ponctuation(texte: str) -> bool:
    """Virgule, point-virgule, deux-points, ou fin de phrase."""
    fin = _fin_sans_fermantes(texte)
    return bool(fin) and fin[-1] in PONCTUATION_DE_COUPURE


def typographie(texte: str, langue: str) -> str:
    """Espaces autour de la ponctuation, selon la langue. Français : espace insécable avant
    « ! ? ; : » et à l'intérieur des guillemets « » (la ponctuation ne se retrouve jamais seule
    en début de ligne). Autres langues : pas d'espace avant « ! ? ; : »."""
    texte = re.sub(r"\s+([,.…)\]}])", r"\1", texte)  # jamais d'espace avant , . … ) ] }
    texte = re.sub(r"([(\[{¿¡])\s+", r"\1", texte)  # ni après ( [ { ¿ ¡
    if (langue or "").split("-")[0].lower() == "fr":
        texte = re.sub(r"(?<=\S)\s*([!?;]+)", lambda m: ESPACE_INSECABLE + m.group(1), texte)
        texte = re.sub(r"(?<=\S)\s*:(?=\s|$)", ESPACE_INSECABLE + ":", texte)  # pas « 10:30 »
        texte = re.sub(r"«\s*", "«" + ESPACE_INSECABLE, texte)
        texte = re.sub(r"(?<=\S)\s*»", ESPACE_INSECABLE + "»", texte)
    else:
        texte = re.sub(r"\s+([!?;:])", r"\1", texte)
    return texte


def sans_ponctuation(texte: str) -> str:
    """Retire la ponctuation autour des mots ; celle à l'intérieur reste (« l'huile », « anti-rides »,
    « 3.5 »)."""
    morceaux = (m.strip(PONCTUATION) for m in texte.split())
    return " ".join(m for m in morceaux if m)


def texte_affiche(texte: str, reglages: ReglagesSousTitres, langue: str) -> str:
    texte = " ".join(texte.split())
    texte = typographie(texte, langue) if reglages.texte.ponctuation else sans_ponctuation(texte)
    if reglages.texte.casse == CASSE_MAJUSCULES:
        return texte.upper()
    return texte.lower() if reglages.texte.casse == CASSE_MINUSCULES else texte


@dataclass
class MotAffiche:
    texte: str  # tel qu'affiché
    original: str  # texte d'origine (sert à repérer la ponctuation, même masquée)
    debut: float
    fin: float
    locuteur: str = ""


def _ponctuation_seule(texte: str) -> bool:
    return bool(texte) and all(c in PONCTUATION for c in texte)


def accrocher_la_ponctuation(mots: list[Mot]) -> list[Mot]:
    """Une ponctuation transcrite comme un mot à part (« ! ») ne s'affiche jamais seule : elle
    rejoint le mot d'avant (« semaines ! »), ou le suivant pour « « » et « ( ». Les temps sont
    ceux du mot qui l'accueille."""
    resultat: list[Mot] = []
    en_attente = ""
    for mot in mots:
        texte = mot.texte.strip()
        if _ponctuation_seule(texte) and all(c in OUVRANTES for c in texte):
            en_attente += texte + " "
        elif _ponctuation_seule(texte) and resultat and not en_attente:
            dernier = resultat[-1]
            resultat[-1] = Mot(f"{dernier.texte} {texte}", dernier.debut, dernier.fin, dernier.locuteur)
        else:
            resultat.append(Mot(en_attente + texte, mot.debut, mot.fin, mot.locuteur))
            en_attente = ""
    if en_attente and resultat:
        dernier = resultat[-1]
        resultat[-1] = Mot(f"{dernier.texte} {en_attente.strip()}", dernier.debut, dernier.fin, dernier.locuteur)
    return resultat


def mots_a_afficher(
    mots: list[Mot],
    reglages: ReglagesSousTitres,
    langue: str,
    hesitations: Iterable[str] = (),
    masquer_hesitations: bool = True,
) -> list[MotAffiche]:
    """Mots des sous-titres, avec leur texte affiché (options du §7.2 appliquées)."""
    gardes = mots_affiches(mots, set(hesitations), masquer_hesitations)
    resultat = []
    for mot in accrocher_la_ponctuation(gardes):
        affiche = texte_affiche(mot.texte, reglages, langue)
        if affiche:
            resultat.append(MotAffiche(affiche, mot.texte, mot.debut, mot.fin, mot.locuteur))
    return resultat


# --- Découpage (§7.3) ---------------------------------------------------------------------------

PAUSE_COUPURE_S = 0.8  # un silence plus long termine toujours le sous-titre
ECART_COMBLE_S = 0.3  # un trou plus court entre deux sous-titres est comblé (pas de clignotement)
TAILLE_REDUITE_MIN = 0.6  # un mot seul trop large est rapetissé, jusqu'à 60 % de la taille du texte
# Poids des critères du meilleur découpage (voir _cout) :
BONUS_PONCTUATION = 0.25  # sous-titre qui finit sur une ponctuation
PENALITE_MARGE = 0.05  # ligne qui déborde de la zone de sécurité (autorisé, mais moins bien)
PREFERENCE_COUPURE_PONCTUATION = 0.85  # 2 lignes : passage à la ligne après une ponctuation


@dataclass
class SousTitre:
    debut: float
    fin: float
    lignes: list[str]
    premier_mot: int  # indices dans les mots affichés
    dernier_mot: int  # (exclu)
    echelle: float = 1.0  # < 1 : un mot seul trop large, affiché plus petit (signalé en orange)
    dans_la_marge: bool = False  # déborde de la zone de sécurité (jusqu'à la marge maximum)
    trop_large: bool = False  # même à la taille minimum, le mot dépasse la marge maximum
    ajustement: Ajustement | None = None  # réorganisé à la main (sinon : découpage automatique)

    @property
    def texte(self) -> str:
        return "\n".join(self.lignes)

    @property
    def ajuste(self) -> bool:
        """« Ajusté à la main » : ses mots ont été choisis à la main (V1.1)."""
        return self.ajustement is not None

    @property
    def signale(self) -> bool:
        """À signaler en orange (§7.3, étape 4) : un mot rapetissé pour tenir dans l'écran."""
        return self.echelle < 1.0 or self.trop_large

    @property
    def duree(self) -> float:
        return self.fin - self.debut


@dataclass(frozen=True)
class _Disposition:
    lignes: tuple[str, ...]
    dans_la_marge: bool = False
    echelle: float = 1.0
    trop_large: bool = False


def disposer(groupe: list[MotAffiche], lignes_max: int, ecran: Ecran, mesure: Mesure) -> _Disposition | None:
    """Place les mots d'un sous-titre sur 1 ou 2 lignes : d'abord dans la zone de sécurité (une
    ligne, sinon deux lignes équilibrées), sinon jusqu'à la marge maximum. None : ça ne tient pas
    (il faudra redécouper). Un mot seul trop large est rapetissé (et signalé)."""
    textes = [m.texte for m in groupe]
    for limite, dans_la_marge in ((ecran.largeur_securite, False), (ecran.largeur_max, True)):
        une_ligne = " ".join(textes)
        if mesure(une_ligne) <= limite:
            return _Disposition((une_ligne,), dans_la_marge)
        if lignes_max >= 2 and len(textes) >= 2:
            meilleure: tuple[float, tuple[str, str]] | None = None
            for coupe in range(1, len(textes)):
                haut, bas = " ".join(textes[:coupe]), " ".join(textes[coupe:])
                largeur = max(mesure(haut), mesure(bas))
                if largeur > limite:
                    continue
                if finit_par_ponctuation(groupe[coupe - 1].original):
                    largeur *= PREFERENCE_COUPURE_PONCTUATION
                if meilleure is None or largeur < meilleure[0]:
                    meilleure = (largeur, (haut, bas))
            if meilleure is not None:
                return _Disposition(meilleure[1], dans_la_marge)
    if len(textes) == 1:
        largeur = mesure(textes[0])
        echelle = ecran.largeur_max / largeur if largeur > 0 else 1.0
        return _Disposition((textes[0],), True, max(TAILLE_REDUITE_MIN, echelle), echelle < TAILLE_REDUITE_MIN)
    return None


def coupure_obligatoire(mot: MotAffiche, suivant: MotAffiche, reglages: ReglagesSousTitres) -> bool:
    """Entre ces deux mots, le sous-titre se termine toujours : changement de personne, long
    silence, ou fin de phrase (si « couper sur la ponctuation » est coché)."""
    if mot.locuteur and suivant.locuteur and mot.locuteur != suivant.locuteur:
        return True
    if suivant.debut - mot.fin > PAUSE_COUPURE_S:
        return True
    return reglages.couper_sur_ponctuation and finit_une_phrase(mot.original)


def _cout(groupe: list[MotAffiche], disposition: _Disposition, reglages: ReglagesSousTitres) -> float:
    """Plus c'est bas, mieux c'est : sous-titres bien remplis et de longueurs proches (l'écart au
    maximum compte au carré), qui finissent si possible sur une ponctuation."""
    caracteres = len(" ".join(m.texte for m in groupe))
    cout = (1.0 - min(1.0, caracteres / reglages.caracteres_max)) ** 2
    if disposition.dans_la_marge:
        cout += PENALITE_MARGE
    if reglages.couper_sur_ponctuation and finit_par_ponctuation(groupe[-1].original):
        cout -= BONUS_PONCTUATION
    return cout


def decouper(mots: list[MotAffiche], reglages: ReglagesSousTitres, ecran: Ecran, mesure: Mesure) -> list[SousTitre]:
    """Meilleur découpage des mots en sous-titres (programmation dynamique : pour chaque mot, le
    meilleur découpage de tout ce qui précède est calculé une fois, puis réutilisé)."""
    nombre_de_mots = len(mots)
    meilleur = [0.0] + [math.inf] * nombre_de_mots
    choix: list[tuple[int, _Disposition] | None] = [None] * (nombre_de_mots + 1)
    for fin in range(1, nombre_de_mots + 1):
        for debut in range(fin - 1, -1, -1):
            groupe = mots[debut:fin]
            if len(groupe) > 1 and (
                len(groupe) > reglages.mots_max
                or coupure_obligatoire(mots[debut], mots[debut + 1], reglages)
                or len(" ".join(m.texte for m in groupe)) > reglages.caracteres_max
            ):
                break  # un groupe plus grand dépasserait aussi
            disposition = disposer(groupe, reglages.lignes_max, ecran, mesure)
            if disposition is None:
                break  # ne tient pas dans l'écran : un groupe plus grand non plus
            cout = meilleur[debut] + _cout(groupe, disposition, reglages)
            if cout < meilleur[fin]:
                meilleur[fin], choix[fin] = cout, (debut, disposition)
    sous_titres: list[SousTitre] = []
    fin = nombre_de_mots
    while fin > 0:
        debut, disposition = choix[fin]
        sous_titres.append(
            SousTitre(
                mots[debut].debut,
                mots[fin - 1].fin,
                list(disposition.lignes),
                debut,
                fin,
                disposition.echelle,
                disposition.dans_la_marge,
                disposition.trop_large,
            )
        )
        fin = debut
    sous_titres.reverse()
    return sous_titres


def caler_les_temps(sous_titres: list[SousTitre], duree_min: float, duree_totale: float | None = None) -> None:
    """Durée minimale (prolongé après, sinon avant, sans chevaucher les voisins), puis petits trous
    comblés : le sous-titre reste affiché jusqu'au suivant."""
    for index, sous_titre in enumerate(sous_titres):
        precedent = sous_titres[index - 1].fin if index else 0.0
        suivant = sous_titres[index + 1].debut if index + 1 < len(sous_titres) else (duree_totale or math.inf)
        if sous_titre.duree < duree_min:
            sous_titre.fin = max(sous_titre.fin, min(sous_titre.debut + duree_min, suivant))
        if sous_titre.duree < duree_min:
            sous_titre.debut = min(sous_titre.debut, max(sous_titre.fin - duree_min, precedent))
    for sous_titre, suivant in zip(sous_titres, sous_titres[1:], strict=False):
        if 0 < suivant.debut - sous_titre.fin <= ECART_COMBLE_S:
            sous_titre.fin = suivant.debut
    for sous_titre in sous_titres:
        sous_titre.debut, sous_titre.fin = round(sous_titre.debut, 3), round(sous_titre.fin, 3)


def sous_titre_au_temps(sous_titres: list[SousTitre], temps: float, debuts: list[float] | None = None) -> int:
    """Indice du sous-titre affiché à cet instant (-1 : aucun). `debuts` : les débuts des
    sous-titres, s'ils sont déjà rangés dans une liste (recherche plus rapide pendant la lecture)."""
    debuts = debuts if debuts is not None else [s.debut for s in sous_titres]
    index = bisect.bisect_right(debuts, temps) - 1
    if 0 <= index < len(sous_titres) and temps < sous_titres[index].fin:
        return index
    return -1


# --- Réorganisation à la main (V1.1) ----------------------------------------------------------


@dataclass(frozen=True)
class Ajustement:
    """Sous-titre réorganisé à la main. Il est repéré par le temps, pas par la place de ses mots
    dans la liste : ses mots sont ceux dont le milieu tombe entre `debut` et `fin` (le début de son
    premier mot et la fin de son dernier, au moment de l'ajustement). Il suit ainsi les mots
    corrigés dans le module Transcription (fusion, coupe, suppression) et les réglages du texte
    affiché (hésitations, ponctuation), sans que le temps d'aucun mot ne change."""

    debut: float
    fin: float

    def contient(self, mot: MotAffiche) -> bool:
        return self.debut <= _milieu(mot) <= self.fin


def _milieu(mot: MotAffiche) -> float:
    return (mot.debut + mot.fin) / 2


# Règles qu'un sous-titre choisi à la main doit respecter (les mêmes que le découpage automatique).
PERSONNE = "personne"  # changement de personne : coupure toujours faite
SILENCE = "silence"  # silence de plus de 0,8 s : coupure toujours faite
PHRASE = "phrase"  # fin de phrase, si « Couper de préférence après la ponctuation » est coché
MOTS = "mots"  # « Mots au plus »
CARACTERES = "caracteres"  # « Caractères au plus »
LIGNES = "lignes"  # tiendrait sur 2 lignes, mais « Lignes au plus » est réglé sur 1
ECRAN = "ecran"  # trop large pour l'écran, même jusqu'à la marge maximum
SANS_MOT = "sans-mot"  # plus aucun de ses mots n'est affiché
CHEVAUCHEMENT = "chevauchement"  # deux mots au même moment : impossible de les séparer


def _nombre(valeur: float) -> str:
    """27 → « 27 » ; 1.25 → « 1,25 »."""
    if float(valeur).is_integer():
        return str(int(valeur))
    return f"{valeur:.2f}".rstrip("0").rstrip(".").replace(".", ",")


@dataclass(frozen=True)
class Refus:
    """Pourquoi des mots ne peuvent pas former un sous-titre (action refusée, ou ajustement défait)."""

    regle: str
    nombre: float = 0  # ex. 27 caractères, 6 mots, 1,2 s de silence
    limite: float = 0  # ex. 24 (« Caractères au plus »)
    mot: str = ""  # ex. « semaines ! » (fin de phrase)
    suivant: str = ""

    def pour_une_action(self, sujet: str = "ce sous-titre") -> str:
        """Raison complète, après « Impossible : ». Ex. « le sous-titre 3 ferait 27 caractères, et
        « Caractères au plus » est réglé sur 24 »."""
        nombre, limite = _nombre(self.nombre), _nombre(self.limite)
        textes = {
            PERSONNE: f"« {self.mot} » et « {self.suivant} » ne sont pas dits par la même personne, et un "
            "changement de personne termine toujours le sous-titre",
            SILENCE: f"il y a un silence de {nombre} s entre « {self.mot} » et « {self.suivant} », et un silence "
            f"de plus de {_nombre(PAUSE_COUPURE_S)} s termine toujours le sous-titre",
            PHRASE: f"« {self.mot} » termine une phrase, et « Couper de préférence après la ponctuation » est "
            "coché : une fin de phrase termine alors toujours le sous-titre",
            MOTS: f"{sujet} aurait {nombre} mots, et « Mots au plus » est réglé sur {limite}",
            CARACTERES: f"{sujet} ferait {nombre} caractères, et « Caractères au plus » est réglé sur {limite}",
            LIGNES: f"{sujet} ne tiendrait pas sur une ligne dans l'écran, et « Lignes au plus » est réglé sur 1",
            ECRAN: f"{sujet} serait trop large pour l'écran, même jusqu'à la marge maximum (réglages « Taille "
            "du texte » et « Marge maximum »)",
            SANS_MOT: f"{sujet} n'aurait plus aucun mot",
            CHEVAUCHEMENT: f"« {self.mot} » et « {self.suivant} » ont le même moment dans la transcription : "
            "corrige d'abord leur moment (« Corriger les mots »)",
        }
        return textes[self.regle]

    def pour_un_reglage(self) -> str:
        """Raison courte, après le nom du sous-titre. Ex. « 22 caractères, pour 20 au plus »."""
        nombre, limite = _nombre(self.nombre), _nombre(self.limite)
        textes = {
            PERSONNE: f"« {self.mot} » et « {self.suivant} » ne sont pas dits par la même personne",
            SILENCE: f"silence de {nombre} s entre « {self.mot} » et « {self.suivant} »",
            PHRASE: f"« {self.mot} » termine une phrase (« Couper de préférence après la ponctuation »)",
            MOTS: f"{nombre} mots, pour {limite} au plus",
            CARACTERES: f"{nombre} caractères, pour {limite} au plus",
            LIGNES: "ne tient plus sur une ligne dans l'écran",
            ECRAN: "trop large pour l'écran, même jusqu'à la marge maximum",
            SANS_MOT: "plus aucun de ses mots n'est affiché",
            CHEVAUCHEMENT: f"« {self.mot} » et « {self.suivant} » ont le même moment",
        }
        return textes[self.regle]


def message_de_refus(refus: Iterable[Refus], sujet: str = "ce sous-titre") -> str:
    """« Impossible : ce sous-titre ferait 27 caractères, et « Caractères au plus » est réglé sur 24. »"""
    return "Impossible : " + " ; ".join(r.pour_une_action(sujet) for r in refus) + "."


def _sur_une_ligne(texte: str) -> str:
    """Texte d'un sous-titre cité dans un message : ses lignes bout à bout."""
    return " ".join(texte.replace(ESPACE_INSECABLE, " ").split())


def _raisons(refus: Iterable[Refus]) -> str:
    return " ; ".join(r.pour_un_reglage() for r in refus)


def texte_reglage_qui_defait(concernes: list[tuple[int, str, tuple[Refus, ...]]]) -> str:
    """Question posée avant un réglage qui défait des sous-titres réorganisés à la main :
    (numéro du sous-titre, son texte, raisons). Ex. « Ce réglage défait ton ajustement du
    sous-titre 4 (« Mais ce Sérum Glowzy a ») : 22 caractères, pour 20 au plus. »"""
    if len(concernes) == 1:
        ((numero, texte, refus),) = concernes
        return f"Ce réglage défait ton ajustement du sous-titre {numero} (« {_sur_une_ligne(texte)} ») : {_raisons(refus)}."
    lignes = [f"Ce réglage défait tes ajustements de {len(concernes)} sous-titres :"]
    lignes += [f"• sous-titre {numero} (« {_sur_une_ligne(texte)} ») : {_raisons(refus)}." for numero, texte, refus in concernes]
    return "\n".join(lignes)


def texte_ajustements_defaits(defaits: list[tuple[int, Defait]]) -> str:
    """Message de la page Sous-titres quand des mots changés dans le module Transcription défont
    des ajustements : (numéro du sous-titre où se trouvent maintenant ses mots, ajustement défait)."""

    def decrire(numero: int, defait: Defait) -> str:
        if not defait.texte:
            return "un sous-titre ajusté n'a plus aucun mot affiché"
        return f"sous-titre {numero} (« {_sur_une_ligne(defait.texte)} ») : {_raisons(defait.refus)}"

    debut = "Des mots ont changé dans le module Transcription"
    if len(defaits) == 1:
        ((numero, defait),) = defaits
        if not defait.texte:
            return f"{debut} : un sous-titre ajusté à la main n'a plus aucun mot affiché, son ajustement est retiré."
        return (
            f"{debut} : ton ajustement du sous-titre {numero} (« {_sur_une_ligne(defait.texte)} ») ne tient plus "
            f"({_raisons(defait.refus)}). Il revient au découpage automatique."
        )
    lignes = [f"{debut} : ces ajustements ne tiennent plus et reviennent au découpage automatique."]
    lignes += [f"• {decrire(numero, defait)}." for numero, defait in defaits]
    return "\n".join(lignes)


def verifier_groupe(
    groupe: list[MotAffiche], reglages: ReglagesSousTitres, ecran: Ecran, mesure: Mesure
) -> tuple[_Disposition | None, tuple[Refus, ...]]:
    """Ces mots peuvent-ils former un sous-titre ? Mêmes règles que le découpage automatique : les
    coupures toujours faites (changement de personne, silence de plus de 0,8 s), la fin de phrase
    (si « Couper de préférence après la ponctuation » est coché), les maximums de mots et de
    caractères (un mot seul peut les dépasser), puis la place à l'écran. Renvoie la mise en lignes,
    ou les raisons du refus."""
    if not groupe:
        return None, (Refus(SANS_MOT),)
    for mot, suivant in zip(groupe, groupe[1:], strict=False):
        if mot.locuteur and suivant.locuteur and mot.locuteur != suivant.locuteur:
            return None, (Refus(PERSONNE, mot=mot.texte, suivant=suivant.texte),)
        silence = suivant.debut - mot.fin
        if silence > PAUSE_COUPURE_S:
            # Arrondi au centième, mais toujours affiché « plus de 0,8 s » (jamais « 0,8 s »).
            duree = max(round(silence, 2), PAUSE_COUPURE_S + 0.01)
            return None, (Refus(SILENCE, duree, PAUSE_COUPURE_S, mot.texte, suivant.texte),)
    refus = []
    if reglages.couper_sur_ponctuation:
        fin_de_phrase = next((m for m in groupe[:-1] if finit_une_phrase(m.original)), None)
        if fin_de_phrase is not None:
            refus.append(Refus(PHRASE, mot=fin_de_phrase.texte))
    if len(groupe) > 1:
        if len(groupe) > reglages.mots_max:
            refus.append(Refus(MOTS, len(groupe), reglages.mots_max))
        caracteres = len(" ".join(m.texte for m in groupe))
        if caracteres > reglages.caracteres_max:
            refus.append(Refus(CARACTERES, caracteres, reglages.caracteres_max))
    if refus:
        return None, tuple(refus)
    disposition = disposer(groupe, reglages.lignes_max, ecran, mesure)
    if disposition is None:
        tiendrait_sur_2_lignes = reglages.lignes_max == 1 and disposer(groupe, 2, ecran, mesure) is not None
        return None, (Refus(LIGNES if tiendrait_sur_2_lignes else ECRAN, limite=reglages.lignes_max),)
    return disposition, ()


@dataclass(frozen=True)
class Defait:
    """Ajustement fait à la main qui ne tient plus (réglage changé, mots corrigés) : ses mots
    reviennent au découpage automatique."""

    ajustement: Ajustement
    refus: tuple[Refus, ...]
    texte: str = ""  # ses mots, tels qu'ils s'afficheraient (vide s'il n'en a plus)
    premier_mot: int = -1  # indice de son premier mot dans les mots affichés (-1 s'il n'en a plus)


@dataclass
class Decoupage:
    """Résultat du calcul : les mots affichés, les sous-titres, et les ajustements qui ne tiennent plus."""

    mots: list[MotAffiche]
    sous_titres: list[SousTitre]
    defaits: list[Defait] = field(default_factory=list)


def _groupes_ajustes(
    mots: list[MotAffiche], ajustements: Iterable[Ajustement]
) -> tuple[list[tuple[Ajustement, int, int]], list[Ajustement]]:
    """Mots de chaque ajustement : (ajustement, premier mot, dernier mot exclu), dans l'ordre du
    temps ; puis les ajustements qui n'ont plus aucun mot. Un mot n'appartient qu'à un ajustement."""
    groupes, sans_mot = [], []
    libre = 0
    for ajustement in sorted(set(ajustements), key=lambda a: (a.debut, a.fin)):
        dedans = [index for index in range(libre, len(mots)) if ajustement.contient(mots[index])]
        if not dedans:
            sans_mot.append(ajustement)
            continue
        groupes.append((ajustement, dedans[0], dedans[-1] + 1))
        libre = dedans[-1] + 1
    return groupes, sans_mot


def decouper_avec_ajustements(
    mots: list[MotAffiche],
    ajustements: Iterable[Ajustement],
    reglages: ReglagesSousTitres,
    ecran: Ecran,
    mesure: Mesure,
) -> tuple[list[SousTitre], list[Defait]]:
    """Les sous-titres ajustés à la main gardent leurs mots ; les mots entre eux sont découpés
    automatiquement. Un ajustement qui ne respecte plus les règles est défait (ses mots reviennent
    au découpage automatique) et renvoyé avec la raison."""
    groupes, sans_mot = _groupes_ajustes(mots, ajustements)
    defaits = [Defait(ajustement, (Refus(SANS_MOT),)) for ajustement in sans_mot]
    gardes: list[tuple[int, int, _Disposition, Ajustement]] = []
    for ajustement, premier, dernier in groupes:
        groupe = mots[premier:dernier]
        disposition, refus = verifier_groupe(groupe, reglages, ecran, mesure)
        if disposition is None:
            defaits.append(Defait(ajustement, refus, " ".join(m.texte for m in groupe), premier))
        else:
            gardes.append((premier, dernier, disposition, ajustement))
    sous_titres: list[SousTitre] = []
    libre = 0  # premier mot pas encore placé
    for premier, dernier, disposition, ajustement in [*gardes, (len(mots), len(mots), None, None)]:
        if premier > libre:  # mots libres avant ce sous-titre ajusté : découpage automatique
            for sous_titre in decouper(mots[libre:premier], reglages, ecran, mesure):
                sous_titre.premier_mot += libre
                sous_titre.dernier_mot += libre
                sous_titres.append(sous_titre)
        if disposition is not None:
            sous_titres.append(
                SousTitre(
                    mots[premier].debut,
                    mots[dernier - 1].fin,
                    list(disposition.lignes),
                    premier,
                    dernier,
                    disposition.echelle,
                    disposition.dans_la_marge,
                    disposition.trop_large,
                    ajustement,
                )
            )
        libre = max(libre, dernier)
    defaits.sort(key=lambda d: (d.ajustement.debut, d.ajustement.fin))
    return sous_titres, defaits


def calculer_sous_titres(
    mots: list[Mot],
    reglages: ReglagesSousTitres,
    langue: str,
    ecran_video: Ecran,
    mesure: Mesure,
    hesitations: Iterable[str] = (),
    masquer_hesitations: bool = True,
    duree_totale: float | None = None,
    ajustements: Iterable[Ajustement] = (),
) -> Decoupage:
    """Des mots de la transcription aux sous-titres : texte affiché, découpage (autour des
    sous-titres ajustés à la main), temps."""
    affiches = mots_a_afficher(mots, reglages, langue, hesitations, masquer_hesitations)
    largeurs: dict[str, float] = {}  # une même ligne est mesurée une seule fois

    def mesure_memorisee(texte: str) -> float:
        if texte not in largeurs:
            largeurs[texte] = mesure(texte)
        return largeurs[texte]

    sous_titres, defaits = decouper_avec_ajustements(affiches, ajustements, reglages, ecran_video, mesure_memorisee)
    caler_les_temps(sous_titres, reglages.duree_min_s, duree_totale)
    return Decoupage(affiches, sous_titres, defaits)


def creer_sous_titres(
    mots: list[Mot],
    reglages: ReglagesSousTitres,
    langue: str,
    ecran_video: Ecran,
    mesure: Mesure,
    hesitations: Iterable[str] = (),
    masquer_hesitations: bool = True,
    duree_totale: float | None = None,
) -> tuple[list[MotAffiche], list[SousTitre]]:
    """Découpage automatique seul (sans ajustement fait à la main) : mots affichés et sous-titres."""
    decoupage = calculer_sous_titres(
        mots, reglages, langue, ecran_video, mesure, hesitations, masquer_hesitations, duree_totale
    )
    return decoupage.mots, decoupage.sous_titres


# --- Actions à la main sur les sous-titres (V1.1) -----------------------------------------------


@dataclass(frozen=True)
class Reorganisation:
    """Résultat d'une action à la main : les ajustements à enregistrer, ou les raisons du refus
    (rien ne change alors)."""

    ajustements: tuple[Ajustement, ...] = ()
    refus: tuple[Refus, ...] = ()
    sujet: str = "ce sous-titre"  # le sous-titre dont parlent les raisons du refus
    choisi: int = 0  # sous-titre à montrer ensuite

    @property
    def possible(self) -> bool:
        return not self.refus

    @property
    def message(self) -> str:
        return message_de_refus(self.refus, self.sujet) if self.refus else ""


def _bornes(mots: list[MotAffiche], premier: int, dernier: int) -> Ajustement:
    """Ajustement qui couvre exactement mots[premier] à mots[dernier] (inclus) : du début du premier
    mot à la fin du dernier. Si un voisin chevauche ce moment (temps de la transcription qui se
    recouvrent), la borne passe à mi-chemin entre les milieux des deux mots."""
    debut, fin = mots[premier].debut, mots[dernier].fin
    if premier > 0 and _milieu(mots[premier - 1]) >= debut:
        debut = (_milieu(mots[premier - 1]) + _milieu(mots[premier])) / 2
    if dernier + 1 < len(mots) and _milieu(mots[dernier + 1]) <= fin:
        fin = (_milieu(mots[dernier]) + _milieu(mots[dernier + 1])) / 2
    return Ajustement(debut, fin)


def _reorganiser(
    decoupage: Decoupage,
    remplaces: range,
    groupes: list[tuple[int, int, str]],
    reglages: ReglagesSousTitres,
    ecran: Ecran,
    mesure: Mesure,
    choisi: int,
) -> Reorganisation:
    """Les sous-titres `remplaces` (indices) deviennent `groupes` : (premier mot, dernier mot
    exclu, nom du sous-titre pour un éventuel refus). Ces groupes sont ajustés à la main ; les
    autres ajustements ne changent pas."""
    mots = decoupage.mots
    for premier, dernier, sujet in groupes:
        _disposition, refus = verifier_groupe(mots[premier:dernier], reglages, ecran, mesure)
        if refus:
            return Reorganisation(refus=refus, sujet=sujet)
    gardes = [
        (s.ajustement, s.premier_mot, s.dernier_mot)
        for index, s in enumerate(decoupage.sous_titres)
        if s.ajustement is not None and index not in remplaces
    ]
    crees = [(_bornes(mots, premier, dernier - 1), premier, dernier) for premier, dernier, _sujet in groupes]
    attendus = sorted(gardes + crees, key=lambda groupe: groupe[1])
    ajustements = tuple(ajustement for ajustement, _premier, _dernier in attendus)
    obtenus, _sans_mot = _groupes_ajustes(mots, ajustements)
    if set(obtenus) != set(attendus):
        # Deux mots au même moment (temps de la transcription) : le temps ne peut pas les séparer.
        for _ajustement, premier, dernier in crees:
            for index in (premier, dernier):
                if 0 < index < len(mots) and _milieu(mots[index - 1]) >= _milieu(mots[index]):
                    return Reorganisation(refus=(Refus(CHEVAUCHEMENT, mot=mots[index - 1].texte, suivant=mots[index].texte),))
        premier = crees[0][1]
        return Reorganisation(refus=(Refus(CHEVAUCHEMENT, mot=mots[max(premier - 1, 0)].texte, suivant=mots[premier].texte),))
    return Reorganisation(ajustements=ajustements, choisi=choisi)


def _sous_titre(decoupage: Decoupage, index: int) -> SousTitre:
    if not 0 <= index < len(decoupage.sous_titres):
        raise ValueError(f"Pas de sous-titre n° {index + 1}.")
    return decoupage.sous_titres[index]


def monter_premier_mot(
    decoupage: Decoupage, index: int, reglages: ReglagesSousTitres, ecran: Ecran, mesure: Mesure
) -> Reorganisation:
    """Le premier mot du sous-titre `index` passe à la fin du sous-titre précédent."""
    actuel = _sous_titre(decoupage, index)
    if index == 0:
        raise ValueError("Le premier sous-titre n'a pas de sous-titre avant lui.")
    precedent = decoupage.sous_titres[index - 1]
    groupes = [(precedent.premier_mot, actuel.premier_mot + 1, f"le sous-titre {index}")]
    if actuel.dernier_mot - actuel.premier_mot > 1:
        groupes.append((actuel.premier_mot + 1, actuel.dernier_mot, f"le sous-titre {index + 1}"))
    choisi = index if len(groupes) == 2 else index - 1
    return _reorganiser(decoupage, range(index - 1, index + 1), groupes, reglages, ecran, mesure, choisi)


def descendre_dernier_mot(
    decoupage: Decoupage, index: int, reglages: ReglagesSousTitres, ecran: Ecran, mesure: Mesure
) -> Reorganisation:
    """Le dernier mot du sous-titre `index` passe au début du sous-titre suivant."""
    actuel = _sous_titre(decoupage, index)
    if index + 1 >= len(decoupage.sous_titres):
        raise ValueError("Le dernier sous-titre n'a pas de sous-titre après lui.")
    suivant = decoupage.sous_titres[index + 1]
    groupes = []
    if actuel.dernier_mot - actuel.premier_mot > 1:
        groupes.append((actuel.premier_mot, actuel.dernier_mot - 1, f"le sous-titre {index + 1}"))
    groupes.append((actuel.dernier_mot - 1, suivant.dernier_mot, f"le sous-titre {index + 2}"))
    return _reorganiser(decoupage, range(index, index + 2), groupes, reglages, ecran, mesure, index)


def couper_avant(
    decoupage: Decoupage, index: int, mot: int, reglages: ReglagesSousTitres, ecran: Ecran, mesure: Mesure
) -> Reorganisation:
    """Le sous-titre `index` est coupé en deux : `mot` (indice dans les mots affichés) commence le
    nouveau sous-titre."""
    actuel = _sous_titre(decoupage, index)
    if not actuel.premier_mot < mot < actuel.dernier_mot:
        raise ValueError("Ce mot ne peut pas commencer un nouveau sous-titre.")
    groupes = [
        (actuel.premier_mot, mot, f"le sous-titre {index + 1}"),
        (mot, actuel.dernier_mot, f"le sous-titre {index + 2}"),
    ]
    return _reorganiser(decoupage, range(index, index + 1), groupes, reglages, ecran, mesure, index)


def fusionner_avec_le_suivant(
    decoupage: Decoupage, index: int, reglages: ReglagesSousTitres, ecran: Ecran, mesure: Mesure
) -> Reorganisation:
    """Le sous-titre `index` et le suivant n'en font plus qu'un."""
    actuel = _sous_titre(decoupage, index)
    if index + 1 >= len(decoupage.sous_titres):
        raise ValueError("Le dernier sous-titre n'a pas de sous-titre après lui.")
    suivant = decoupage.sous_titres[index + 1]
    groupes = [(actuel.premier_mot, suivant.dernier_mot, "le sous-titre fusionné")]
    return _reorganiser(decoupage, range(index, index + 2), groupes, reglages, ecran, mesure, index)


def retablir_automatique(decoupage: Decoupage, index: int | None = None) -> Reorganisation:
    """Le sous-titre `index` (ou tous, si None) revient au découpage automatique."""
    if index is None:
        return Reorganisation()
    _sous_titre(decoupage, index)
    gardes = tuple(
        s.ajustement for numero, s in enumerate(decoupage.sous_titres) if s.ajustement is not None and numero != index
    )
    return Reorganisation(ajustements=gardes, choisi=index)


# --- Export SRT (§8.1) --------------------------------------------------------------------------


def temps_srt(secondes: float) -> str:
    """1.25 → « 00:00:01,250 »."""
    millisecondes = max(0, round(secondes * 1000))
    heures, reste = divmod(millisecondes, 3_600_000)
    minutes, reste = divmod(reste, 60_000)
    secondes_entieres, millisecondes = divmod(reste, 1000)
    return f"{heures:02d}:{minutes:02d}:{secondes_entieres:02d},{millisecondes:03d}"


def srt(sous_titres: list[SousTitre]) -> str:
    """Texte du fichier SRT : numéro, temps, lignes ; un bloc par sous-titre, séparés par une
    ligne vide. Fins de ligne Windows (CRLF)."""
    blocs = [
        "\r\n".join([str(numero), f"{temps_srt(s.debut)} --> {temps_srt(s.fin)}", *s.lignes])
        for numero, s in enumerate(sous_titres, 1)
    ]
    return "\r\n\r\n".join(blocs) + ("\r\n" if blocs else "")


def ecrire_srt(chemin: Path, sous_titres: list[SousTitre]) -> None:
    """UTF-8 avec BOM : sans lui, Premiere Pro lit mal les lettres accentuées (é, à, ç…)."""
    chemin.write_text(srt(sous_titres), encoding="utf-8-sig", newline="")
