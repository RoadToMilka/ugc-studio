"""Mise en page d'un sous-titre (V2, lot 3) : où va chaque ligne et chaque mot, en pixels de la vidéo.

Ce fichier ne dépend pas de l'interface : les largeurs viennent d'une fonction de mesure, et les
hauteurs des mesures de la police (le moteur de dessin les fournit, rendu/moteur.py ; une règle
simple dans les tests). Le moteur dessine ensuite exactement à ces places : l'aperçu et l'export de
la V3 partagent ce calcul.

Règles (§7.3, §7.4) :
- Position verticale : « Haut » = juste sous le haut de la zone de sécurité ; « Bas » = juste
  au-dessus de son bas ; « Centre » = milieu de l'écran. Le réglage fin décale à partir de là (en %
  de la hauteur) : un même style se place ainsi correctement sur TikTok comme sur Reels.
- Point fixe du bloc : son haut (Haut), son milieu (Centre) ou son bas (Bas). Un sous-titre de 2
  lignes grandit donc vers le bas, des deux côtés, ou vers le haut.
- Le bloc ne dépasse jamais la marge maximum, ni en haut ni en bas ; le réglage fin s'arrête à
  temps pour le plus grand sous-titre possible (« Lignes au plus »).
- Alignement : centre (chaque ligne centrée sur le milieu de l'écran), gauche (les lignes partent
  du bord gauche de la zone de sécurité, jamais de la marge) ou droite.
"""

from __future__ import annotations

from dataclasses import dataclass

from .sous_titres import Cadre, Mesure, MotAffiche, ReglagesSousTitres, SousTitre
from .style_sous_titres import CENTRE, DROITE, GAUCHE, HAUT


@dataclass(frozen=True)
class Metriques:
    """Mesures de la police à la taille du texte, en pixels de la vidéo."""

    ascendante: float  # de la ligne de base au haut des lettres les plus hautes (accents compris)
    descendante: float  # de la ligne de base au bas des jambages (p, g, j…)
    interligne: float  # d'une ligne de base à la suivante


@dataclass(frozen=True)
class MotPlace:
    index: int  # place du mot dans les mots affichés (comme SousTitre.premier_mot)
    texte: str
    x: float  # début du mot
    largeur: float
    ligne: int  # 0 : première ligne du sous-titre


@dataclass(frozen=True)
class LignePlacee:
    texte: str
    x: float
    base: float  # ligne de base (le bas des lettres sans jambage)
    largeur: float


@dataclass(frozen=True)
class Bloc:
    """Un sous-titre placé à l'écran : ses lignes, ses mots, et le rectangle du texte."""

    lignes: tuple[LignePlacee, ...]
    mots: tuple[MotPlace, ...]
    x: float
    y: float
    largeur: float
    hauteur: float
    echelle: float = 1.0  # taille appliquée au texte (moins de 1 : un mot seul rapetissé, §7.3)


def hauteur_du_bloc(lignes: int, metriques: Metriques, echelle: float = 1.0) -> float:
    """Du haut des lettres de la première ligne au bas des jambages de la dernière."""
    return ((max(lignes, 1) - 1) * metriques.interligne + metriques.ascendante + metriques.descendante) * echelle


def ancre(reglages: ReglagesSousTitres, zone: Cadre) -> float:
    """Ordonnée du point fixe du bloc (son haut, son milieu ou son bas), avant le réglage fin. Sans
    zone de sécurité (plateforme « Aucune »), la marge maximum en tient lieu."""
    verticale = reglages.position.verticale
    if verticale == HAUT:
        return max(zone.securite_haut, zone.marge_y)
    if verticale == CENTRE:
        return zone.hauteur / 2
    return min(zone.securite_bas, zone.hauteur - zone.marge_y)


def _part_au_dessus(reglages: ReglagesSousTitres) -> float:
    """Part de la hauteur du bloc au-dessus de son point fixe : 0 (haut), 0,5 (milieu), 1 (bas)."""
    return {HAUT: 0.0, CENTRE: 0.5}.get(reglages.position.verticale, 1.0)


def haut_du_bloc(reglages: ReglagesSousTitres, zone: Cadre, hauteur: float) -> float:
    """Ordonnée du haut du bloc, réglage fin compris, sans jamais dépasser la marge maximum."""
    point = ancre(reglages, zone) + zone.hauteur * reglages.position.decalage_pct / 100
    haut = point - hauteur * _part_au_dessus(reglages)
    haut = min(haut, zone.hauteur - zone.marge_y - hauteur)
    return max(haut, zone.marge_y)


def limites_du_reglage_fin(reglages: ReglagesSousTitres, zone: Cadre, metriques: Metriques) -> tuple[float, float]:
    """Réglage fin permis (en % de la hauteur) : le plus grand sous-titre possible (« Lignes au
    plus » lignes) reste entre les marges maximum du haut et du bas."""
    hauteur = hauteur_du_bloc(reglages.lignes_max, metriques)
    depart = ancre(reglages, zone) - hauteur * _part_au_dessus(reglages)  # haut du bloc sans réglage fin
    bas = zone.marge_y - depart
    haut = zone.hauteur - zone.marge_y - hauteur - depart
    if bas > haut:  # plus de place : le bloc reste collé à la marge du haut
        bas = haut = zone.marge_y - depart
    return bas / zone.hauteur * 100, haut / zone.hauteur * 100


def x_de_la_ligne(zone: Cadre, largeur: float) -> float:
    if zone.alignement == GAUCHE:
        return zone.x_depart
    if zone.alignement == DROITE:
        return zone.x_depart - largeur
    return zone.x_depart - largeur / 2


def mots_par_ligne(textes: list[str], lignes: list[str]) -> list[list[int]] | None:
    """Indices (dans `textes`) des mots de chaque ligne : une ligne est faite de ses mots joints par
    une espace (sous_titres.disposer). None si les lignes ne correspondent pas aux mots."""
    resultat: list[list[int]] = []
    suivant = 0
    for ligne in lignes:
        groupe: list[int] = []
        assemble = ""
        while suivant < len(textes) and assemble != ligne:
            assemble = f"{assemble} {textes[suivant]}" if groupe else textes[suivant]
            groupe.append(suivant)
            suivant += 1
            if len(assemble) > len(ligne):
                return None
        if assemble != ligne or not groupe:
            return None
        resultat.append(groupe)
    return resultat if suivant == len(textes) else None


def placer(
    sous_titre: SousTitre,
    mots: list[MotAffiche],
    reglages: ReglagesSousTitres,
    zone: Cadre,
    metriques: Metriques,
    mesure: Mesure,
) -> Bloc:
    """Place les lignes et les mots d'un sous-titre (en pixels de la vidéo). Un mot commence là où
    finit la ligne, moins la largeur de ce qui le suit : ainsi, la ligne a exactement la largeur
    mesurée par le découpage."""
    echelle = sous_titre.echelle
    textes = [m.texte for m in mots[sous_titre.premier_mot : sous_titre.dernier_mot]]
    lignes = list(sous_titre.lignes) or [""]
    groupes = mots_par_ligne(textes, lignes)
    if groupes is None:  # ne devrait pas arriver : une seule ligne avec tous les mots
        lignes, groupes = [" ".join(textes)], [list(range(len(textes)))]
    largeurs = [mesure(ligne) * echelle for ligne in lignes]
    hauteur = hauteur_du_bloc(len(lignes), metriques, echelle)
    haut = haut_du_bloc(reglages, zone, hauteur)
    lignes_placees, mots_places = [], []
    for numero, (texte, groupe, largeur) in enumerate(zip(lignes, groupes, largeurs, strict=True)):
        x = x_de_la_ligne(zone, largeur)
        base = haut + (metriques.ascendante + numero * metriques.interligne) * echelle
        lignes_placees.append(LignePlacee(texte, x, base, largeur))
        for rang, index in enumerate(groupe):
            suite = " ".join(textes[i] for i in groupe[rang:])
            mots_places.append(
                MotPlace(
                    sous_titre.premier_mot + index,
                    textes[index],
                    x + largeur - mesure(suite) * echelle,
                    mesure(textes[index]) * echelle,
                    numero,
                )
            )
    gauche = min((ligne.x for ligne in lignes_placees), default=0.0)
    droite = max((ligne.x + ligne.largeur for ligne in lignes_placees), default=0.0)
    return Bloc(tuple(lignes_placees), tuple(mots_places), gauche, haut, droite - gauche, hauteur, echelle)
