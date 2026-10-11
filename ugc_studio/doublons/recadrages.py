"""La même photo recadrée, zoomée ou légèrement tournée, prouvée (V4.4, lot 2 de Doublons).

Pour les deux méthodes avec IA (« Toutes les copies », « Copies et photos proches »). La recherche des
copies entières (copies.py) superpose deux photos entières ; ici, l'une peut n'être qu'une partie de
l'autre, agrandie ou réduite, un peu tournée, retournée, avec d'autres couleurs.

1. Repérer, avec l'IA. Le modèle découpe chaque photo (sans ses bords unis) en carreaux de 14 pixels et
   décrit chacun : 384 nombres par carreau, droite et retournée (vision.py). Entre une photo et sa
   version recadrée, beaucoup de carreaux se retrouvent deux à deux (chacun est le plus proche de
   l'autre), et ils sont tous déplacés de la même façon : une « similitude » (un agrandissement, une
   rotation et un décalage). Elle est retrouvée en essayant des centaines de paires de correspondances
   tirées au hasard, et en gardant celles que suivent le plus de carreaux (RANSAC) : les trois
   meilleures par sens, sur toutes les correspondances puis sur les nettes seulement (test du rapport).
   Entre deux photos différentes, les carreaux qui se ressemblent sont peu nombreux et ne vont pas
   ensemble.
2. Prouver, sans IA. Les deux photos (en gris) sont superposées par cette similitude, affinée au pixel
   près (méthode de Lucas et Kanade), puis leurs contours sont comparés sur la partie commune : partout
   (ressemblance globale), et carreau par carreau, sur une grille de 4 × 4 (chacun doit se ressembler).
   Deux photos différentes qui montrent le même objet plat, l'écran d'une même montre par exemple, se
   superposent sur cet objet et pas ailleurs : la grille les écarte. Une vraie copie se superpose
   partout.

Réglé le 11/10/2026 sur le lot de l'utilisateur (document « UGC Studio - V4.3 Doublons », §9.2) : 40 de
ses photos déclinées 10 fois (recadrées à 75 %, 50 % et 35 % de leur surface, zoomées à 40 % et
agrandies, tournées de 6° et de 12°, recadrées et retournées avec d'autres couleurs, réduites, recadrées
et tournées, en perspective) : 359 des 360 déclinaisons sans perspective prouvées, ressemblance des
contours de 0,98 au moins, grille entièrement concordante (la seule manquée, recadrée à 35 %, montre un
fond de carreaux répétés) ; aucune des 780 paires de ses photos différentes. Une photo déformée en
perspective n'est presque jamais prouvée (4 sur 40 : la similitude ne sait pas la redresser) : avec
« Copies et photos proches », elle ressort comme photo proche.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image

# --- Ce qui est gardé de chaque photo (méthodes avec IA) --------------------------------------------
COTE_DETAIL = 384  # la photo sans ses bords unis, en gris, grand côté (environ 150 Ko)
COTE_COULEURS = 64  # et en couleurs, pour l'écart de couleurs
COTE_MIN = 8  # une image réduite garde au moins 8 pixels de côté

# --- Repérer ----------------------------------------------------------------------------------------
# Les paires examinées : pour chaque photo, ses VOISINS photos les plus proches pour l'IA, si leur
# proximité (cosinus des empreintes) atteint au moins COSINUS_MIN. Sur le banc d'essai, une photo
# recadrée à 50 % ou zoomée à 40 % reste au-dessus de 0,59 de son original, presque toujours en tête.
VOISINS = 8
COSINUS_MIN = 0.55
ESSAIS = 256  # paires de correspondances tirées au hasard (RANSAC)
HYPOTHESES = 3  # similitudes essayées par sens (droite, retournée), la plus suivie d'abord
TOLERANCE = 1.5  # écart permis à la similitude, en carreaux (14 pixels de l'image vue par le modèle)
CORRESPONDANCES_MIN = 35  # carreaux qui vont ensemble, au moins (banc : 47 au moins pour une vraie copie)
RAPPORT = 0.95  # correspondance nette : distance au plus proche < 95 % de la distance au deuxième
CORRESPONDANCES_NETTES_MIN = 20  # parmi les nettes seulement (banc : 43 au moins pour une vraie copie)
ECHELLE_MAX = 5.0  # l'une au plus 5 fois plus grande que l'autre (dans l'image vue par le modèle)
ANGLE_MAX = 20.0  # « légèrement tournée » : 20° au plus

# --- Prouver ----------------------------------------------------------------------------------------
COTE_VERIFICATION = 160  # grand côté de l'extrait (la plus petite des deux parties), au plus
COTE_VERIFICATION_MIN = 48
COUVERTURE_MIN = 0.85  # l'extrait est dans l'autre photo, pour 85 % de sa surface au moins
ITERATIONS = 16  # affinage (Lucas-Kanade) sur les petites images ; moitié moins sur les entières
RESSEMBLANCE_DES_PETITES_MIN = 0.60  # en dessous, sur les petites images, la paire est écartée
GRILLE = 4  # carreaux de la vérification : 4 × 4
CONCORDANCE_CARREAU = 0.70  # ressemblance des contours d'un carreau, pour qu'il concorde
ENERGIE_CARREAU = 0.15  # un carreau plus uni que 15 % des contours les plus marqués n'est pas jugé
CARREAUX_JUGES_MIN = 3  # en dessous, la grille ne juge pas (voir SEUIL_CONTOURS_SANS_GRILLE)
SEUIL_CONTOURS_SANS_GRILLE = 0.97
SEUIL_CONTOURS = 0.90  # ressemblance des contours sur toute la partie commune, au moins
SEUIL_CARREAUX = 0.85  # part des carreaux de la grille qui concordent, au moins
# Écart des couleurs (sur 255, voir _ecart_de_couleurs) en dessous duquel les couleurs n'ont pas changé
# (banc : 4,1 au plus sans changement de couleurs, 13,5 au moins avec).
ECART_DE_COULEURS_SANS_CHANGEMENT = 8.0
BLOC_COULEURS = 4  # les couleurs comparées par blocs de 4 × 4 pixels (de l'image de COTE_COULEURS)


@dataclass(frozen=True)
class Carreaux:
    """Ce que le modèle voit dans chaque carreau de la photo sans ses bords unis : une ligne de 384
    nombres (de longueur 1) par carreau, pour la photo droite et pour la photo retournée (float16 :
    environ 0,5 Mo par photo pour les deux), et le centre de chaque carreau, en pixels de l'image vue
    par le modèle (`taille` : sa largeur et sa hauteur). Les carreaux de la photo retournée ont leurs
    centres aux mêmes places, dans la photo retournée."""

    droits: np.ndarray
    retournes: np.ndarray
    centres: np.ndarray  # n × 2 (x, y), float32
    taille: tuple[int, int]


@dataclass(frozen=True)
class Detail:
    """Ce qui sert à prouver un recadrage : les carreaux, et la photo sans ses bords unis, réduite, en gris
    (COTE_DETAIL de grand côté) et en couleurs (COTE_COULEURS)."""

    carreaux: Carreaux
    gris: np.ndarray  # hauteur × largeur, uint8
    couleurs: np.ndarray  # hauteur × largeur × 3, uint8


def detail(rognee: Image.Image, carreaux: Carreaux) -> Detail:
    """Le détail d'une photo (RGB, dans le bon sens, sans ses bords unis)."""

    def reduite(mode: str, cote: int) -> np.ndarray:
        image = rognee.convert(mode)
        echelle = cote / max(image.size)
        if echelle < 1:
            taille = (max(COTE_MIN, round(image.width * echelle)), max(COTE_MIN, round(image.height * echelle)))
            image = image.resize(taille, Image.Resampling.BOX)
        return np.asarray(image, dtype=np.uint8)

    return Detail(carreaux, reduite("L", COTE_DETAIL), reduite("RGB", COTE_COULEURS))


# --- Repérer : les carreaux qui vont ensemble ------------------------------------------------------------


def _correspondances(premiers: np.ndarray, seconds: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Les carreaux (i, j) qui sont chacun le plus proche de l'autre, et lesquels le sont nettement : le
    plus proche l'est plus que le deuxième (test du rapport, RAPPORT). Dans une partie unie de la photo
    (un fond, un mur), le modèle décrit surtout la place du carreau, et beaucoup de carreaux de l'autre
    photo se valent : ces correspondances-là ne disent presque rien."""
    ressemblances = premiers.astype(np.float32) @ seconds.astype(np.float32).T
    vers_seconds = ressemblances.argmax(axis=1)
    vers_premiers = ressemblances.argmax(axis=0)
    i = np.arange(len(premiers))
    gardes = vers_premiers[vers_seconds] == i
    nettes = np.ones(len(premiers), dtype=bool)
    if ressemblances.shape[1] >= 2:
        deux = np.partition(ressemblances, -2, axis=1)[:, -2:]  # le deuxième, puis le premier
        premier, deuxieme = np.sqrt(np.maximum(2 - 2 * deux[:, 1], 0)), np.sqrt(np.maximum(2 - 2 * deux[:, 0], 0))
        nettes = premier < RAPPORT * deuxieme
    return i[gardes], vers_seconds[gardes], nettes[gardes]


@dataclass(frozen=True)
class Similitude:
    """w = m · z + t, en nombres complexes (z = x + i·y) : m porte l'agrandissement (|m|) et la rotation
    (son angle), t le décalage."""

    m: complex
    t: complex

    @property
    def echelle(self) -> float:
        return abs(self.m)

    @property
    def angle(self) -> float:
        """En degrés."""
        return math.degrees(math.atan2(self.m.imag, self.m.real))

    def appliquer(self, z: np.ndarray) -> np.ndarray:
        return self.m * z + self.t

    def inverse(self) -> Similitude:
        return Similitude(1 / self.m, -self.t / self.m)


def _moindres_carres(z: np.ndarray, w: np.ndarray) -> Similitude:
    """La similitude qui envoie au mieux les points z sur les points w."""
    zc, wc = z - z.mean(), w - w.mean()
    m = complex((wc * np.conj(zc)).sum() / max(float((np.abs(zc) ** 2).sum()), 1e-9))
    return Similitude(m, complex(w.mean() - m * z.mean()))


def _hypotheses(z: np.ndarray, w: np.ndarray, tolerance: float, graine: int, nombre: int, sans_identite: bool = False) -> list[tuple[Similitude, np.ndarray]]:
    """Les similitudes que suivent le plus de correspondances (z → w), et lesquelles les suivent : au
    plus `nombre`, la meilleure d'abord, chacune suivie par d'autres correspondances que les précédentes.
    Les hypothèses (deux correspondances tirées au hasard suffisent pour une similitude) sont calculées
    toutes ensemble.

    Pourquoi plusieurs : dans les parties unies d'une photo (un fond en dégradé, un mur), le modèle décrit
    surtout la place du carreau dans l'image, et deux photos différentes s'y « correspondent » carreau
    pour carreau, sans déplacement. Cette fausse similitude peut être la plus suivie ; la vraie vient
    alors juste après, et la superposition tranche. `sans_identite` : écarte la similitude « rien ne
    bouge » (deux images vues par le modèle à la même taille, carreau pour carreau) : c'est celle de ces
    fausses correspondances, et celle d'une copie entière, déjà cherchée sans IA (copies.py)."""
    n = len(z)
    if n < 4:
        return []
    hasard = np.random.default_rng(graine)
    premiers, seconds = hasard.integers(0, n, ESSAIS), hasard.integers(0, n, ESSAIS)
    dz = z[seconds] - z[premiers]
    utiles = np.abs(dz) > 1e-6
    premiers, seconds, dz = premiers[utiles], seconds[utiles], dz[utiles]
    if len(dz) == 0:
        return []
    m = (w[seconds] - w[premiers]) / dz
    t = w[premiers] - m * z[premiers]
    possibles = (np.abs(m) <= ECHELLE_MAX) & (np.abs(m) >= 1 / ECHELLE_MAX) & (np.abs(np.angle(m, deg=True)) <= ANGLE_MAX + 5)
    if not possibles.any():
        return []
    if sans_identite:
        possibles &= ~((np.abs(m - 1) < 0.05) & (np.abs(t) < tolerance))
    if not possibles.any():
        return []
    m, t = m[possibles], t[possibles]
    ecarts = np.abs(m[:, None] * z[None, :] + t[:, None] - w[None, :])
    # Chaque hypothèse est jugée sur ses écarts (MSAC) plutôt que sur le seul nombre de correspondances
    # qui la suivent : à nombre égal, la plus précise l'emporte (une échelle un peu fausse peut garder
    # beaucoup de correspondances dans la tolérance).
    couts = (np.minimum(ecarts, tolerance) ** 2).sum(axis=1)
    trouvees: list[tuple[Similitude, np.ndarray]] = []
    deja = np.zeros(n, dtype=bool)
    for rang in np.argsort(couts):
        gardes = ecarts[rang] < tolerance
        if gardes.sum() < 4 or (gardes & deja).sum() > 0.5 * gardes.sum():
            continue  # trop peu suivie, ou la même qu'une hypothèse déjà gardée
        similitude = Similitude(complex(m[rang]), complex(t[rang]))
        # Affinée sur les correspondances qui la suivent, avec une tolérance de plus en plus étroite
        # (les mauvaises correspondances restées dans la tolérance pèsent de moins en moins).
        for facteur in (1.0, 0.75, 0.5):
            proches = np.abs(similitude.appliquer(z) - w) < tolerance * facteur
            if proches.sum() < 8:
                break
            similitude = _moindres_carres(z[proches], w[proches])
        gardes = np.abs(similitude.appliquer(z) - w) < tolerance
        if gardes.sum() < 4:
            continue
        trouvees.append((similitude, gardes))
        deja |= gardes
        if len(trouvees) == nombre:
            break
    return trouvees


def _ransac(z: np.ndarray, w: np.ndarray, tolerance: float, graine: int) -> tuple[Similitude | None, np.ndarray]:
    """La similitude que suivent le plus de correspondances (z → w), et lesquelles la suivent."""
    trouvees = _hypotheses(z, w, tolerance, graine, 1)
    return trouvees[0] if trouvees else (None, np.zeros(len(z), dtype=bool))


@dataclass(frozen=True)
class Reperage:
    """Le résultat du repérage d'une paire (a, b) : la similitude qui envoie les pixels de l'image vue
    par le modèle de b (retournée si `miroir`) sur ceux de a, et combien de carreaux la suivent."""

    similitude: Similitude
    correspondances: int
    miroir: bool


def reperer(a: Carreaux, b: Carreaux, graine: int = 0) -> list[Reperage]:
    """Les carreaux de b, droits puis retournés, qui vont avec ceux de a, et les similitudes qu'ils
    suivent (au plus HYPOTHESES par sens) : celles que suivent au moins CORRESPONDANCES_MIN carreaux, la
    plus suivie d'abord. Les deux sens sont gardés : une photo retournée d'un objet presque symétrique
    (une montre de face) peut trouver beaucoup de correspondances sans être retournée ; seule la
    superposition tranche."""
    trouves: list[Reperage] = []
    centres_a = a.centres[:, 0] + 1j * a.centres[:, 1]
    centres_b = b.centres[:, 0] + 1j * b.centres[:, 1]
    tolerance = TOLERANCE * 14
    for miroir in (False, True):
        i, j, nettes = _correspondances(b.retournes if miroir else b.droits, a.droits)
        # Toutes les correspondances, puis seulement les nettes : dans une photo aux grandes parties unies,
        # les correspondances qui ne disent rien peuvent cacher la vraie similitude (voir _hypotheses).
        for choix, minimum in ((np.ones(len(i), dtype=bool), CORRESPONDANCES_MIN), (nettes, CORRESPONDANCES_NETTES_MIN)):
            hypotheses = _hypotheses(centres_b[i[choix]], centres_a[j[choix]], tolerance, graine, HYPOTHESES, sans_identite=a.taille == b.taille)
            for similitude, gardes in hypotheses:
                nombre = int(gardes.sum())
                if nombre >= minimum and abs(similitude.angle) <= ANGLE_MAX and not _deja_trouvee(similitude, miroir, trouves):
                    trouves.append(Reperage(similitude, nombre, miroir))
    return sorted(trouves, key=lambda reperage: -reperage.correspondances)


def _deja_trouvee(similitude: Similitude, miroir: bool, trouves: list[Reperage]) -> bool:
    """Une similitude presque égale à une autre déjà trouvée (même sens) : inutile de l'essayer deux fois."""
    return any(
        r.miroir == miroir and abs(r.similitude.m - similitude.m) < 0.03 * abs(similitude.m) and abs(r.similitude.t - similitude.t) < TOLERANCE * 14
        for r in trouves
    )


# --- Prouver : superposer au pixel près --------------------------------------------------------------------


def _echantillonner(image: np.ndarray, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Les valeurs de l'image aux positions (x, y) (interpolation bilinéaire), et celles qui tombent dans
    l'image."""
    hauteur, largeur = image.shape
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = (x - x0).astype(np.float32), (y - y0).astype(np.float32)
    dedans = (x0 >= 0) & (y0 >= 0) & (x0 < largeur - 1) & (y0 < hauteur - 1)
    x0, y0 = np.clip(x0, 0, largeur - 2), np.clip(y0, 0, hauteur - 2)
    valeurs = (
        image[y0, x0] * (1 - fx) * (1 - fy)
        + image[y0, x0 + 1] * fx * (1 - fy)
        + image[y0 + 1, x0] * (1 - fx) * fy
        + image[y0 + 1, x0 + 1] * fx * fy
    )
    return valeurs, dedans


def _echantillonner_ensemble(images: np.ndarray, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Comme _echantillonner, pour plusieurs images de même taille empilées (hauteur × largeur × n) : les
    positions ne sont calculées qu'une fois. Renvoie (nombre de positions × n, dedans)."""
    hauteur, largeur, _n = images.shape
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = (x - x0).astype(np.float32)[:, None], (y - y0).astype(np.float32)[:, None]
    dedans = (x0 >= 0) & (y0 >= 0) & (x0 < largeur - 1) & (y0 < hauteur - 1)
    rangs = np.clip(y0, 0, hauteur - 2) * largeur + np.clip(x0, 0, largeur - 2)
    plates = images.reshape(hauteur * largeur, -1)
    valeurs = (
        plates[rangs] * ((1 - fx) * (1 - fy))
        + plates[rangs + 1] * (fx * (1 - fy))
        + plates[rangs + largeur] * ((1 - fx) * fy)
        + plates[rangs + largeur + 1] * (fx * fy)
    )
    return valeurs, dedans


def _moitie(image: np.ndarray) -> np.ndarray:
    """L'image deux fois plus petite (moyenne de chaque carré de 2 × 2 pixels) : le pixel k de la moitié
    a son centre au point 2k + 0,5 de l'image entière."""
    hauteur, largeur = image.shape[0] // 2 * 2, image.shape[1] // 2 * 2
    return image[:hauteur, :largeur].reshape(hauteur // 2, 2, largeur // 2, 2).mean(axis=(1, 3))


def _flou(image: np.ndarray) -> np.ndarray:
    """Un léger flou (moyenne 3 × 3) : le grain de la compression ne compte pas."""
    flou = image.copy()
    flou[1:-1, 1:-1] = sum(image[1 + dy : image.shape[0] - 1 + dy, 1 + dx : image.shape[1] - 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9.0
    return flou


def _gradients(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    gx, gy = np.zeros_like(image), np.zeros_like(image)
    gx[:, 1:-1] = (image[:, 2:] - image[:, :-2]) / 2
    gy[1:-1] = (image[2:] - image[:-2]) / 2
    return gx, gy


def _normee(valeurs: np.ndarray) -> np.ndarray:
    valeurs = valeurs - valeurs.mean()
    norme = float(np.linalg.norm(valeurs))
    return valeurs / norme if norme > 1e-6 else valeurs


def _positions(similitude: Similitude, largeur: int, hauteur: int) -> tuple[np.ndarray, np.ndarray]:
    ys, xs = np.mgrid[0:hauteur, 0:largeur].astype(np.float32)
    w = similitude.appliquer(xs.ravel() + 1j * ys.ravel())
    return w.real.astype(np.float32), w.imag.astype(np.float32)


def _lucas_kanade(conteneur: np.ndarray, extrait: np.ndarray, depart: Similitude, iterations: int) -> tuple[Similitude, float] | None:
    """Lucas-Kanade : la similitude (pixels de l'extrait → pixels du conteneur) qui superpose au mieux
    l'extrait sur le conteneur (images floutées), en partant de `depart`, et la ressemblance obtenue (de
    -1 à 1). Un changement de clarté ou de contraste entre les deux ne gêne pas (il est retiré à chaque
    pas). None si l'extrait sort du conteneur."""
    hauteur, largeur = extrait.shape
    ys, xs = np.mgrid[0:hauteur, 0:largeur].astype(np.float32)
    xs, ys = xs.ravel(), ys.ravel()
    gx, gy = _gradients(conteneur)
    pile = np.stack([conteneur, gx, gy], axis=2).astype(np.float32)
    modele = extrait.ravel()
    a, b, tx, ty = depart.m.real, depart.m.imag, depart.t.real, depart.t.imag
    ressemblance = -1.0
    for _ in range(iterations):
        x, y = a * xs - b * ys + tx, b * xs + a * ys + ty
        valeurs, dedans = _echantillonner_ensemble(pile, x, y)
        if dedans.mean() < 0.5:
            return None
        vu, vx, vy = valeurs[dedans, 0], valeurs[dedans, 1], valeurs[dedans, 2]
        xd, yd, mo = xs[dedans], ys[dedans], modele[dedans]
        vu, mo = vu - vu.mean(), mo - mo.mean()
        produit, carre_mo, carre_vu = float(mo @ vu), float(mo @ mo), float(vu @ vu)
        ressemblance = produit / max(math.sqrt(carre_mo * carre_vu), 1e-9)
        residu = vu - (produit / max(carre_mo, 1e-6)) * mo
        jacobienne = np.stack([vx * xd + vy * yd, vy * xd - vx * yd, vx, vy], axis=1)
        jacobienne -= jacobienne.mean(axis=0)
        try:
            pas = np.linalg.solve(jacobienne.T @ jacobienne + 1e-6 * np.eye(4), -(jacobienne.T @ residu))
        except np.linalg.LinAlgError:
            return None
        a, b, tx, ty = a + pas[0], b + pas[1], tx + pas[2], ty + pas[3]
        if abs(pas[2]) < 0.01 and abs(pas[3]) < 0.01 and abs(pas[0]) < 1e-4 and abs(pas[1]) < 1e-4:
            break
    return Similitude(complex(a, b), complex(tx, ty)), ressemblance


def _affiner(conteneur: np.ndarray, extrait: np.ndarray, depart: Similitude) -> Similitude | None:
    """La superposition affinée, d'abord sur les images deux fois plus petites (rapide, et elle rattrape
    un départ décalé de quelques pixels), puis sur les images entières. Une paire qui ne se superpose
    pas du tout sur les petites images est écartée là : la plupart des paires de photos différentes."""
    h = 0.5 * (1 + 1j)  # pixel k de la moitié : centre au point 2k + 0,5 de l'image entière
    petite = Similitude(depart.m, (depart.t + (depart.m - 1) * h) / 2)
    trouvee = _lucas_kanade(_moitie(conteneur), _moitie(extrait), petite, ITERATIONS)
    if trouvee is None or trouvee[1] < RESSEMBLANCE_DES_PETITES_MIN:
        return None
    petite = trouvee[0]
    entiere = Similitude(petite.m, 2 * petite.t - (petite.m - 1) * h)
    trouvee = _lucas_kanade(conteneur, extrait, entiere, ITERATIONS // 2)
    return None if trouvee is None else trouvee[0]


def _contours(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    flou = _flou(image)
    gx, gy = np.zeros_like(flou), np.zeros_like(flou)
    gx[1:-1, 1:-1] = flou[1:-1, 2:] - flou[1:-1, :-2]
    gy[1:-1, 1:-1] = flou[2:, 1:-1] - flou[:-2, 1:-1]
    return gx, gy


def _comparer(conteneur: np.ndarray, extrait: np.ndarray, similitude: Similitude) -> tuple[float, float]:
    """Les contours de l'extrait et du conteneur superposés : leur ressemblance sur toute la partie
    commune, et la part des carreaux de la grille (ceux qui ont assez de détails) qui concordent."""
    hauteur, largeur = extrait.shape
    x, y = _positions(similitude, largeur, hauteur)
    valeurs, dedans = _echantillonner(conteneur, x, y)
    valeurs, dedans = valeurs.reshape(hauteur, largeur), dedans.reshape(hauteur, largeur)
    masque = dedans.copy()
    masque[:2], masque[-2:], masque[:, :2], masque[:, -2:] = False, False, False, False
    for decalage in (1, 2):  # les contours ont besoin des pixels voisins
        for axe in (0, 1):
            masque &= np.roll(dedans, decalage, axe) & np.roll(dedans, -decalage, axe)
    if masque.mean() < 0.5:
        return -1.0, 0.0
    cx, cy = _contours(valeurs)
    ex, ey = _contours(extrait)
    globale = float(_normee(np.concatenate([cx[masque], cy[masque]])) @ _normee(np.concatenate([ex[masque], ey[masque]])))
    energie = np.hypot(ex, ey)
    reference = float(np.percentile(energie[masque], 90)) or 1.0
    concordants, juges = 0, 0
    for rang in range(GRILLE):
        for colonne in range(GRILLE):
            zone = (slice(rang * hauteur // GRILLE, (rang + 1) * hauteur // GRILLE), slice(colonne * largeur // GRILLE, (colonne + 1) * largeur // GRILLE))
            dans_la_zone = masque[zone]
            if dans_la_zone.mean() < 0.6 or energie[zone][dans_la_zone].mean() < ENERGIE_CARREAU * reference:
                continue  # hors de la partie commune, ou trop uni pour juger (un ciel, un mur)
            juges += 1
            u = _normee(np.concatenate([cx[zone][dans_la_zone], cy[zone][dans_la_zone]]))
            v = _normee(np.concatenate([ex[zone][dans_la_zone], ey[zone][dans_la_zone]]))
            concordants += float(u @ v) >= CONCORDANCE_CARREAU
    if juges >= CARREAUX_JUGES_MIN:
        return globale, concordants / juges
    # Presque tout est uni (un objet sur un fond lisse) : la grille ne peut pas juger ; il faut alors
    # que les contours se superposent presque parfaitement.
    return globale, (1.0 if globale >= SEUIL_CONTOURS_SANS_GRILLE else 0.0)


def _reduite(image: np.ndarray, cote: int) -> tuple[np.ndarray, float]:
    """L'image (float32) réduite à `cote` de grand côté au plus, et le facteur appliqué."""
    hauteur, largeur = image.shape[:2]
    echelle = min(1.0, cote / max(hauteur, largeur))
    if echelle >= 1.0:
        return image.astype(np.float32), 1.0
    taille = (max(COTE_MIN, round(largeur * echelle)), max(COTE_MIN, round(hauteur * echelle)))
    reduite = Image.fromarray(image).resize(taille, Image.Resampling.BOX)
    return np.asarray(reduite, dtype=np.float32), taille[0] / largeur


def _aire_dans(coins: np.ndarray, largeur: float, hauteur: float) -> float:
    """L'aire de la partie du quadrilatère `coins` (4 points complexes, dans l'ordre) qui tombe dans le
    rectangle [0, largeur] × [0, hauteur] (découpe de Sutherland-Hodgman, puis formule du lacet)."""
    points = [complex(c) for c in coins]
    for garder in (lambda p: p.real >= 0, lambda p: p.real <= largeur, lambda p: p.imag >= 0, lambda p: p.imag <= hauteur):
        if not points:
            return 0.0
        entree, points = points, []
        for k, courant in enumerate(entree):
            precedent = entree[k - 1]
            if garder(courant):
                if not garder(precedent):
                    points.append(_croisement(precedent, courant, garder))
                points.append(courant)
            elif garder(precedent):
                points.append(_croisement(precedent, courant, garder))
    if len(points) < 3:
        return 0.0
    return abs(sum((p.conjugate() * q).imag for p, q in zip(points, points[1:] + points[:1]))) / 2


def _croisement(p: complex, q: complex, garder) -> complex:
    """Le point du segment [p, q] où l'on passe d'un côté de la limite à l'autre (par dichotomie)."""
    dedans, dehors = (p, q) if garder(p) else (q, p)
    for _ in range(30):
        milieu = (dedans + dehors) / 2
        if garder(milieu):
            dedans = milieu
        else:
            dehors = milieu
    return dedans


@dataclass(frozen=True)
class PreuveRecadrage:
    """La preuve que deux photos sont la même photo, l'une recadrée, zoomée ou tournée par rapport à
    l'autre. `extrait` : 0 si c'est la première de la paire qui est (presque) entièrement dans l'autre,
    1 si c'est la seconde. `gardee` : la part de l'autre photo que l'extrait garde (de 0 à 1)."""

    extrait: int
    gardee: float
    angle: float  # en degrés
    miroir: bool
    agrandie: bool  # l'extrait a plus de pixels que la même partie dans l'autre photo
    contours: float
    carreaux: float
    ecart_de_couleurs: float
    correspondances: int

    @property
    def recadree(self) -> bool:
        return self.gardee < 0.97

    @property
    def tournee(self) -> bool:
        return abs(self.angle) >= 1.0

    @property
    def autres_couleurs(self) -> bool:
        return self.ecart_de_couleurs >= ECART_DE_COULEURS_SANS_CHANGEMENT

    def proximite(self) -> int:
        """Dans la zone « Même photo » : 99 %, moins un point si elle est recadrée en gardant au moins
        60 % de la photo, deux en dessous ; un de moins si elle est tournée, un si elle est retournée,
        et de un à trois selon la force du changement de couleurs ; jamais moins de 95 %."""
        note = 99
        if self.recadree:
            note -= 1 if self.gardee >= 0.6 else 2
        if self.tournee:
            note -= 1
        if self.miroir:
            note -= 1
        if self.autres_couleurs:
            note -= 1 if self.ecart_de_couleurs < 20 else 2 if self.ecart_de_couleurs < 35 else 3
        return max(95, note)

    def details(self) -> tuple[str, ...]:
        """« recadrée (55 % gardée) », « agrandie », « tournée de 6° », « retournée », « autres couleurs »."""
        details = []
        if self.recadree:
            details.append(f"recadrée ({round(self.gardee * 100)} % gardée)")
        if self.agrandie:
            details.append("agrandie")
        if self.tournee:
            details.append(f"tournée de {round(abs(self.angle))}°")
        if self.miroir:
            details.append("retournée")
        if self.autres_couleurs:
            details.append("autres couleurs")
        return tuple(details)


def prouver(a: Detail, b: Detail, taille_a: tuple[int, int], taille_b: tuple[int, int], graine: int = 0) -> PreuveRecadrage | None:
    """La preuve que a et b (leurs détails) sont la même photo, l'une recadrée, zoomée ou tournée par
    rapport à l'autre, ou None. `taille_a`, `taille_b` : leurs tailles en pixels (sans les bords unis),
    pour dire si l'extrait a été agrandi."""
    for reperage in reperer(a.carreaux, b.carreaux, graine):
        preuve = _prouver_avec(a, b, taille_a, taille_b, reperage)
        if preuve is not None:
            return preuve
    return None


def _prouver_avec(a: Detail, b: Detail, taille_a: tuple[int, int], taille_b: tuple[int, int], reperage: Reperage) -> PreuveRecadrage | None:
    """La preuve, à partir d'un repérage (une similitude trouvée par les carreaux), ou None."""
    # Qui est dans qui ? Les coins de b (dans l'image vue par le modèle) envoyés dans a, et l'inverse.
    lb, hb = b.carreaux.taille
    la, ha = a.carreaux.taille
    vers_a = reperage.similitude
    coins_b = vers_a.appliquer(np.array([0, lb, lb + 1j * hb, 1j * hb], dtype=complex))
    coins_a = vers_a.inverse().appliquer(np.array([0, la, la + 1j * ha, 1j * ha], dtype=complex))
    couverture_b = _aire_dans(coins_b, la, ha) / max(abs(vers_a.m) ** 2 * lb * hb, 1e-9)
    couverture_a = _aire_dans(coins_a, lb, hb) / max(abs(1 / vers_a.m) ** 2 * la * ha, 1e-9)
    if max(couverture_a, couverture_b) < COUVERTURE_MIN:
        return None  # ni l'une ni l'autre n'est dans l'autre
    extrait = 1 if couverture_b >= couverture_a else 0
    # La superposition se fait dans le sens extrait → conteneur ; la photo retournée est celle de b.
    if extrait == 1:
        detail_extrait, detail_conteneur, vers_conteneur = b, a, vers_a
        gris_extrait = b.gris[:, ::-1] if reperage.miroir else b.gris
        gris_conteneur = a.gris
        couleurs_extrait = b.couleurs[:, ::-1] if reperage.miroir else b.couleurs
        couleurs_conteneur = a.couleurs
    else:
        detail_extrait, detail_conteneur, vers_conteneur = a, b, vers_a.inverse()
        gris_extrait = a.gris
        gris_conteneur = b.gris[:, ::-1] if reperage.miroir else b.gris
        couleurs_extrait = a.couleurs
        couleurs_conteneur = b.couleurs[:, ::-1] if reperage.miroir else b.couleurs
    # Pixels du modèle → pixels des images en gris gardées (et en couleurs).
    def facteur(image: np.ndarray, carreaux: Carreaux) -> float:
        return image.shape[1] / carreaux.taille[0]

    f_extrait, f_conteneur = facteur(gris_extrait, detail_extrait.carreaux), facteur(gris_conteneur, detail_conteneur.carreaux)
    # L'extrait réduit de sorte que ses pixels ne soient pas plus fins que ceux du conteneur.
    largeur_dans_le_conteneur = max(gris_extrait.shape) / f_extrait * vers_conteneur.echelle * f_conteneur
    cote = int(max(COTE_VERIFICATION_MIN, min(COTE_VERIFICATION, largeur_dans_le_conteneur, max(gris_extrait.shape))))
    petit_extrait, r = _reduite(gris_extrait, cote)
    f_petit = f_extrait * r
    # z (pixel de l'extrait réduit, centre au point entier) → pixel du conteneur (même convention).
    m = vers_conteneur.m * f_conteneur / f_petit
    t = f_conteneur * vers_conteneur.t + (m * 0.5 - 0.5) * (1 + 1j)
    depart = Similitude(complex(m), complex(t))
    conteneur = gris_conteneur.astype(np.float32)
    affinee = _affiner(_flou(conteneur), _flou(petit_extrait), depart)
    if affinee is None or abs(affinee.angle) > ANGLE_MAX:
        return None
    contours, concordance = _comparer(conteneur, petit_extrait, affinee)
    if contours < SEUIL_CONTOURS or concordance < SEUIL_CARREAUX:
        return None
    # La part gardée, d'après la superposition affinée (plus exacte que le repérage par carreaux) : les
    # coins de l'extrait (bords des pixels) envoyés dans le conteneur.
    h = 0.5 * (1 + 1j)
    hauteur_e, largeur_e = petit_extrait.shape
    coins = np.array([0, largeur_e, largeur_e + 1j * hauteur_e, 1j * hauteur_e], dtype=complex) - h
    hauteur_c, largeur_c = conteneur.shape
    gardee = _aire_dans(affinee.appliquer(coins) + h, largeur_c, hauteur_c) / (largeur_c * hauteur_c)
    # Couleurs : l'extrait en petites couleurs, et la même partie du conteneur.
    fc_extrait = couleurs_extrait.shape[1] / petit_extrait.shape[1]
    fc_conteneur = couleurs_conteneur.shape[1] / conteneur.shape[1]
    # Mêmes conventions que plus haut (centre d'un pixel au point entier) : h, le demi-pixel.
    m_couleurs = affinee.m * fc_conteneur / fc_extrait
    vers_couleurs = Similitude(m_couleurs, h * m_couleurs + fc_conteneur * (affinee.t + h - h * affinee.m) - h)
    ecart = _ecart_de_couleurs(couleurs_conteneur, couleurs_extrait, vers_couleurs)
    # Agrandie : l'extrait a plus de pixels (dans la photo d'origine) que la même partie dans l'autre.
    taille_extrait, taille_conteneur = (taille_b, taille_a) if extrait == 1 else (taille_a, taille_b)
    pixels_par_modele_extrait = taille_extrait[0] / detail_extrait.carreaux.taille[0]
    pixels_par_modele_conteneur = taille_conteneur[0] / detail_conteneur.carreaux.taille[0]
    agrandie = pixels_par_modele_extrait > 1.15 * vers_conteneur.echelle * pixels_par_modele_conteneur
    return PreuveRecadrage(
        extrait=extrait,
        gardee=float(min(1.0, gardee)),
        angle=affinee.angle,
        miroir=reperage.miroir,
        agrandie=bool(agrandie),
        contours=contours,
        carreaux=concordance,
        ecart_de_couleurs=ecart,
        correspondances=reperage.correspondances,
    )


def _ecart_de_couleurs(conteneur: np.ndarray, extrait: np.ndarray, vers_conteneur: Similitude) -> float:
    """L'écart des couleurs (sur 255) entre l'extrait et la même partie du conteneur, superposés : pour
    chaque couleur (rouge, vert, bleu), l'écart de leurs moyennes et celui de leurs écarts types,
    additionnés, puis la moyenne des trois. Un changement de luminosité, de contraste, de saturation ou
    de teinte change ces chiffres ; une superposition un peu moins nette au bord des objets, non (les
    mêmes pixels sont là, à peine déplacés). Calculé sur des blocs de BLOC_COULEURS × BLOC_COULEURS
    pixels entièrement dans le conteneur."""
    hauteur, largeur = extrait.shape[:2]
    x, y = _positions(vers_conteneur, largeur, hauteur)
    valeurs, dedans = _echantillonner_ensemble(conteneur.astype(np.float32), x, y)
    if dedans.mean() < 0.3:
        return 0.0
    hauteur_b, largeur_b = hauteur // BLOC_COULEURS, largeur // BLOC_COULEURS
    if hauteur_b == 0 or largeur_b == 0:
        return 0.0

    def par_blocs(image: np.ndarray) -> np.ndarray:
        coupee = image[: hauteur_b * BLOC_COULEURS, : largeur_b * BLOC_COULEURS]
        return coupee.reshape(hauteur_b, BLOC_COULEURS, largeur_b, BLOC_COULEURS, -1).mean(axis=(1, 3))

    entiers = par_blocs(dedans.reshape(hauteur, largeur, 1).astype(np.float32))[:, :, 0] == 1.0  # blocs entièrement dans le conteneur
    if entiers.sum() < 4:
        return 0.0
    du_conteneur = par_blocs(valeurs.reshape(hauteur, largeur, 3))[entiers]
    de_l_extrait = par_blocs(extrait.astype(np.float32))[entiers]
    ecarts = np.abs(du_conteneur.mean(axis=0) - de_l_extrait.mean(axis=0)) + np.abs(du_conteneur.std(axis=0) - de_l_extrait.std(axis=0))
    return float(ecarts.mean())


def paires_a_examiner(empreintes: np.ndarray, groupes: list[int], connues: set[tuple[int, int]]) -> list[tuple[int, int]]:
    """Les paires (i < j) à examiner : pour chaque photo, ses VOISINS photos les plus proches pour l'IA
    (au moins COSINUS_MIN), d'un autre groupe de copies, sans les paires déjà prouvées. Une seule photo
    par groupe de copies (la première) : ses copies ont les mêmes voisins."""
    representants = sorted(set(groupes))
    if len(representants) < 2:
        return []
    index = np.array(representants)
    proximites = empreintes[index] @ empreintes[index].T
    np.fill_diagonal(proximites, -2.0)
    paires: set[tuple[int, int]] = set()
    voisins = min(VOISINS, len(index) - 1)
    plus_proches = np.argpartition(-proximites, voisins - 1, axis=1)[:, :voisins]
    for rang, colonnes in enumerate(plus_proches):
        for colonne in colonnes:
            if proximites[rang, colonne] >= COSINUS_MIN:
                a, b = sorted((int(index[rang]), int(index[colonne])))
                if (a, b) not in connues:
                    paires.add((a, b))
    return sorted(paires)
