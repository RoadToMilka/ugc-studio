"""Les copies d'une même photo, prouvées sans IA (V4.3).

Lot 1 (4.3.0) : la photo entière, à une autre taille ou une autre compression, dans un autre format, avec
d'autres couleurs, retournée en miroir, ou avec des bords unis ajoutés (mise au carré, cadre blanc).
Lot 2 (4.4.0) : aussi recadrée, zoomée ou rognée (la même mécanique, en cherchant l'une dans l'autre).

Comment : chaque photo est réduite en gris, telle quelle et sans ses bords unis. Une première
comparaison, très rapide, sur une vignette de 32 × 32 pixels, met de côté les paires qui ne peuvent pas
être la même photo (formes trop différentes, ou rien de commun). Les autres sont superposées à
128 pixels, droites puis retournées, et seuls leurs **contours** (les changements de clarté d'un pixel
à l'autre) sont comparés : des couleurs, une luminosité ou un contraste différents ne les changent
presque pas, alors que deux prises différentes, même très proches, n'ont pas les mêmes contours partout.

Aucune IA ici : c'est une preuve. Elle donne la note de la zone « Même photo » (95 à 99 %).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

# Bords unis : une bande dont tous les pixels sont à moins de TOLERANCE_BORD (sur 255) de la couleur des
# bords, presque sans variation (écart type d'au plus VARIATION_BORD), est retirée, sans jamais retirer
# plus de PART_MAX_BORD de la hauteur ou de la largeur par côté. Stricte : un mur ou un fond clair d'une
# vraie photo n'est pas assez uni pour être pris pour un bord ajouté.
TOLERANCE_BORD = 12
VARIATION_BORD = 3.0
PART_MAX_BORD = 0.45
COTE_DE_RECHERCHE_DES_BORDS = 256

COTE_VIGNETTE = 32  # première comparaison
GRAND_COTE_PREUVE = 128  # superposition
COTE_COULEURS = 16  # écart de couleurs

# Formes : deux copies d'une même photo entière ont les mêmes proportions (à l'arrondi près).
ECART_DE_PROPORTIONS_MAX = 0.04  # 4 %
# Première comparaison : ressemblance des vignettes (de -1 à 1) en dessous de laquelle la paire est
# écartée sans superposition. Très bas : elle ne sert qu'à gagner du temps.
SEUIL_VIGNETTES = 0.50
# Preuve : ressemblance des contours superposés (de -1 à 1) à partir de laquelle c'est la même photo.
# Réglée le 11/10/2026 sur le lot de l'utilisateur (121 photos différentes) et sur 61 de ses photos
# déclinées (autre taille et compression, autres couleurs, noir et blanc, filtre, miroir, bords ajoutés) :
# toutes les déclinaisons au-dessus de 0,71, toutes les paires de photos différentes en dessous de 0,37.
SEUIL_CONTOURS = 0.60

# Couleurs : écart moyen (sur 255) entre les deux photos superposées, en dessous duquel elles ont les
# mêmes couleurs (la compression seule fait varier de quelques niveaux).
ECART_DE_COULEURS_SANS_CHANGEMENT = 8.0


def rogner_bords_unis(image: Image.Image) -> tuple[Image.Image, bool]:
    """L'image sans ses bandes unies (blanches, noires ou d'une autre couleur) sur les côtés, et si des
    bandes ont été retirées. Une photo sans bande unie est rendue telle quelle."""
    petite = image.copy()
    petite.thumbnail((COTE_DE_RECHERCHE_DES_BORDS, COTE_DE_RECHERCHE_DES_BORDS))
    pixels = np.asarray(petite.convert("RGB"), dtype=np.float32)
    hauteur, largeur = pixels.shape[:2]
    if hauteur < 4 or largeur < 4:
        return image, False
    tour = np.concatenate([pixels[0], pixels[-1], pixels[:, 0], pixels[:, -1]])
    couleur = np.median(tour, axis=0)

    def unie(bande: np.ndarray) -> bool:
        return bool(np.abs(bande - couleur).max() <= TOLERANCE_BORD and bande.std(axis=0).max() <= VARIATION_BORD)

    haut, bas, gauche, droite = 0, hauteur, 0, largeur
    while haut < hauteur * PART_MAX_BORD and unie(pixels[haut]):
        haut += 1
    while bas > hauteur * (1 - PART_MAX_BORD) and unie(pixels[bas - 1]):
        bas -= 1
    while gauche < largeur * PART_MAX_BORD and unie(pixels[haut:bas, gauche]):
        gauche += 1
    while droite > largeur * (1 - PART_MAX_BORD) and unie(pixels[haut:bas, droite - 1]):
        droite -= 1
    if (haut, bas, gauche, droite) == (0, hauteur, 0, largeur):
        return image, False
    l, h = image.size
    boite = (round(gauche * l / largeur), round(haut * h / hauteur), round(droite * l / largeur), round(bas * h / hauteur))
    return image.crop(boite), True


def _centree_reduite(valeurs: np.ndarray) -> np.ndarray:
    valeurs = valeurs.astype(np.float32).ravel()
    valeurs = valeurs - valeurs.mean()
    norme = float(np.linalg.norm(valeurs))
    return valeurs / norme if norme > 1e-6 else valeurs


@dataclass(frozen=True)
class Vue:
    """La photo réduite pour la comparaison, telle quelle ou sans ses bords unis."""

    proportions: float  # largeur / hauteur
    vignette: np.ndarray  # 32 × 32 en gris, centrée réduite (1 024 valeurs)
    vignette_miroir: np.ndarray
    gris: np.ndarray  # en gris, 128 pixels de grand côté (proportions gardées)
    couleurs: np.ndarray  # 16 × 16 × 3, pour l'écart de couleurs


def _vue(image: Image.Image) -> Vue:
    largeur, hauteur = image.size
    gris = image.convert("L")
    vignette = gris.resize((COTE_VIGNETTE, COTE_VIGNETTE), Image.Resampling.BOX)
    echelle = GRAND_COTE_PREUVE / max(largeur, hauteur)
    taille = (max(8, round(largeur * echelle)), max(8, round(hauteur * echelle)))
    return Vue(
        proportions=largeur / hauteur,
        vignette=_centree_reduite(np.asarray(vignette)),
        vignette_miroir=_centree_reduite(np.asarray(vignette.transpose(Image.Transpose.FLIP_LEFT_RIGHT))),
        gris=np.asarray(gris.resize(taille, Image.Resampling.BOX), dtype=np.float32),
        couleurs=np.asarray(image.convert("RGB").resize((COTE_COULEURS, COTE_COULEURS), Image.Resampling.BOX), dtype=np.float32),
    )


@dataclass(frozen=True)
class Signature:
    """Ce que la recherche des copies garde de chaque photo (quelques dizaines de Ko) : la photo telle
    quelle, et sans ses bords unis quand elle en a (sinon, la même vue)."""

    entiere: Vue
    sans_bords: Vue

    @property
    def bords(self) -> bool:
        return self.sans_bords is not self.entiere

    def vues(self) -> tuple[tuple[Vue, bool], ...]:
        return ((self.entiere, False),) if not self.bords else ((self.entiere, False), (self.sans_bords, True))


def signature(image: Image.Image) -> Signature:
    """La signature d'une photo (RGB, dans le bon sens), pour la recherche des copies."""
    entiere = _vue(image)
    rognee, bords = rogner_bords_unis(image)
    return Signature(entiere, _vue(rognee) if bords else entiere)


def _contours(gris: np.ndarray) -> np.ndarray:
    """Les contours d'une image en gris : ses changements de clarté horizontaux et verticaux, après un
    léger flou (le grain de la compression ne compte pas), centrés réduits."""
    flou = gris.copy()
    flou[1:-1, 1:-1] = (
        gris[:-2, :-2] + gris[:-2, 1:-1] + gris[:-2, 2:]
        + gris[1:-1, :-2] + gris[1:-1, 1:-1] + gris[1:-1, 2:]
        + gris[2:, :-2] + gris[2:, 1:-1] + gris[2:, 2:]
    ) / 9.0
    horizontaux = flou[1:-1, 2:] - flou[1:-1, :-2]
    verticaux = flou[2:, 1:-1] - flou[:-2, 1:-1]
    return _centree_reduite(np.concatenate([horizontaux.ravel(), verticaux.ravel()]))


def _a_la_taille(gris: np.ndarray, taille: tuple[int, int]) -> np.ndarray:
    if (gris.shape[1], gris.shape[0]) == taille:
        return gris
    return np.asarray(Image.fromarray(gris, mode="F").resize(taille, Image.Resampling.BILINEAR), dtype=np.float32)


@dataclass(frozen=True)
class Preuve:
    """La preuve que deux photos sont la même photo entière, et ce qui les distingue."""

    miroir: bool  # l'une est l'autre retournée
    contours: float  # ressemblance des contours superposés (de SEUIL_CONTOURS à 1)
    ecart_de_couleurs: float  # écart moyen des couleurs, sur 255
    bords: bool  # l'une a des bords unis que l'autre n'a pas

    @property
    def autres_couleurs(self) -> bool:
        return self.ecart_de_couleurs >= ECART_DE_COULEURS_SANS_CHANGEMENT

    def proximite(self) -> int:
        """La note, dans la zone « Même photo » : 99 % quand seules la taille, la compression ou le format
        changent ; un point de moins si elle est retournée, un de moins pour des bords ajoutés, et de un
        à trois selon la force du changement de couleurs ; jamais moins de 95 %."""
        note = 99
        if self.miroir:
            note -= 1
        if self.bords:
            note -= 1
        if self.autres_couleurs:
            note -= 1 if self.ecart_de_couleurs < 20 else 2 if self.ecart_de_couleurs < 35 else 3
        return max(95, note)


def _ressemblance(contours_a: np.ndarray, gris_b: np.ndarray) -> tuple[float, bool]:
    droite = float(np.dot(contours_a, _contours(gris_b)))
    retournee = float(np.dot(contours_a, _contours(gris_b[:, ::-1])))
    return (retournee, True) if retournee > droite else (droite, False)


def _rognee(gris: np.ndarray, colonnes: int, lignes: int) -> np.ndarray:
    hauteur, largeur = gris.shape
    return gris[lignes : hauteur - lignes, colonnes : largeur - colonnes]


# Petits décalages essayés quand la superposition est douteuse : un bord uni retiré un peu trop tôt ou
# un peu trop tard laisse quelques pixels de différence (en pixels à 128, retirés de chaque côté de
# l'une des deux vues).
DECALAGES = ((1, 0), (2, 0), (0, 1), (0, 2), (1, 1), (2, 2), (3, 0), (0, 3))
RESSEMBLANCE_DOUTEUSE = 0.30


def _superposer(a: Vue, b: Vue) -> tuple[float, bool] | None:
    """Ressemblance des contours de deux vues superposées (la meilleure, droite ou retournée), ou None si
    leurs formes diffèrent."""
    if abs(np.log(a.proportions / b.proportions)) > ECART_DE_PROPORTIONS_MAX:
        return None
    taille = (min(a.gris.shape[1], b.gris.shape[1]), min(a.gris.shape[0], b.gris.shape[0]))
    if min(taille) < 16:
        return None
    gris_a, gris_b = _a_la_taille(a.gris, taille), _a_la_taille(b.gris, taille)
    meilleure = _ressemblance(_contours(gris_a), gris_b)
    if RESSEMBLANCE_DOUTEUSE <= meilleure[0] < SEUIL_CONTOURS:
        # Douteuse : l'une des deux a peut-être quelques pixels de bord en plus.
        for colonnes, lignes in DECALAGES:
            for rognee, entiere, premiere in ((gris_a, gris_b, True), (gris_b, gris_a, False)):
                plus_petite = _a_la_taille(_rognee(rognee, colonnes, lignes), taille)
                essai = _ressemblance(_contours(plus_petite), entiere) if premiere else _ressemblance(_contours(entiere), plus_petite)
                if essai[0] > meilleure[0]:
                    meilleure = essai
    return meilleure


def prouver(a: Signature, b: Signature, seuil: float = SEUIL_CONTOURS) -> Preuve | None:
    """La preuve que `a` et `b` sont la même photo entière (droite ou retournée, avec ou sans bords
    unis ajoutés), ou None. `seuil` : pour les essais de réglage seulement."""
    meilleure: tuple[float, bool, Vue, Vue, bool] | None = None
    for vue_a, rognee_a in a.vues():
        for vue_b, rognee_b in b.vues():
            trouvee = _superposer(vue_a, vue_b)
            if trouvee is not None and (meilleure is None or trouvee[0] > meilleure[0]):
                meilleure = (trouvee[0], trouvee[1], vue_a, vue_b, rognee_a != rognee_b)
    if meilleure is None or meilleure[0] < seuil:
        return None
    ressemblance, miroir, vue_a, vue_b, bords = meilleure
    couleurs_b = vue_b.couleurs[:, ::-1] if miroir else vue_b.couleurs
    ecart = float(np.abs(vue_a.couleurs - couleurs_b).mean())
    return Preuve(miroir, ressemblance, ecart, bords)


def paires_candidates(signatures: list[Signature], permises: np.ndarray | None = None) -> list[tuple[int, int]]:
    """Les paires (i < j) qui méritent la superposition : des vues de mêmes proportions dont les
    vignettes se ressemblent un peu (droites ou retournées). `permises` : une matrice de booléens
    (n × n) des paires à comparer (« Comparer » : dans chaque dossier, entre les dossiers)."""
    n = len(signatures)
    if n < 2:
        return []
    retenues = np.zeros((n, n), dtype=bool)
    for choix_a in ("entiere", "sans_bords"):
        vues_a = [getattr(s, choix_a) for s in signatures]
        vignettes = np.stack([v.vignette for v in vues_a])
        proportions_a = np.log([v.proportions for v in vues_a])
        for choix_b in ("entiere", "sans_bords"):
            vues_b = [getattr(s, choix_b) for s in signatures]
            proportions_b = np.log([v.proportions for v in vues_b])
            ressemblance = np.maximum(vignettes @ np.stack([v.vignette for v in vues_b]).T, vignettes @ np.stack([v.vignette_miroir for v in vues_b]).T)
            formes = np.abs(proportions_a[:, None] - proportions_b[None, :]) <= ECART_DE_PROPORTIONS_MAX
            retenues |= (ressemblance >= SEUIL_VIGNETTES) & formes
    retenues |= retenues.T
    if permises is not None:
        retenues &= permises
    i, j = np.nonzero(np.triu(retenues, 1))
    return list(zip(i.tolist(), j.tolist()))
