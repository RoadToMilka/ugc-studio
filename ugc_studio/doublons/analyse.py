"""L'analyse d'un lot de photos (V4.3) : lire chaque photo une fois, trouver les copies (sans IA) et,
avec la méthode « avec IA », décrire chaque photo par le modèle. Sans interface : la page Doublons la
lance en arrière-plan, et le résultat lui permet de montrer les paires de n'importe quel mode
(« Comparer ») et de n'importe quel seuil sans rien refaire.

Ce qui est lu reste en mémoire le temps de la séance (Memoire) : relancer l'analyse après avoir ajouté
un dossier ne relit que les nouvelles photos (et celles modifiées entre-temps). Rien n'est écrit sur le
disque, et les photos ne sont jamais modifiées.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageOps

from .choix import COMPARAISON, IA, LECTURE, MODELE
from .copies import Preuve, Signature, paires_candidates, prouver, signature
from .paires import IDENTIQUES, MEME_PHOTO, Paire, Selection, ToutesLesPaires, paires_permises
from .photos import Photo, PhotoLue, lire_la_photo

LECTEURS = 3  # photos lues en même temps (Pillow décode en parallèle)
EN_AVANCE = 6  # photos lues d'avance, au plus (mémoire)



class AnalyseArretee(Exception):
    """L'utilisateur a arrêté l'analyse."""


@dataclass(frozen=True)
class Avancement:
    """Où en est l'analyse : LECTURE (sans IA) ou IA (avec), photos faites sur le total ; MODELE : le
    modèle d'IA se prépare ; COMPARAISON : les paires se comparent."""

    etape: str
    faites: int = 0
    total: int = 0


@dataclass(frozen=True)
class Infos:
    """Ce qu'on sait d'une photo lue : l'empreinte exacte de son fichier, sa taille en pixels (dans le bon
    sens) et son format (« JPEG », « PNG »…)."""

    empreinte: str
    largeur: int
    hauteur: int
    format: str


@dataclass
class _Lue:
    infos: Infos
    signature: Signature
    ia: np.ndarray | None = None


class Memoire:
    """Les photos déjà lues pendant la séance, retrouvées par leur clé (chemin, taille, date)."""

    def __init__(self):
        self._lues: dict[tuple, _Lue] = {}
        self._verrou = threading.Lock()

    def trouver(self, photo: Photo) -> _Lue | None:
        with self._verrou:
            return self._lues.get(photo.cle)

    def garder(self, photo: Photo, lue: _Lue) -> None:
        with self._verrou:
            self._lues[photo.cle] = lue

    def __len__(self) -> int:
        with self._verrou:
            return len(self._lues)


@dataclass
class Resultat:
    """Le résultat d'une analyse. `photos` : celles qui ont pu être lues ; `illisibles` : les autres, avec
    la raison. Les paires se demandent à paires(mode, seuil)."""

    photos: list[Photo]
    infos: list[Infos]
    illisibles: list[tuple[Photo, str]]
    avec_ia: bool
    identiques: set[tuple[int, int]]
    memes_pixels: set[tuple[int, int]]
    preuves: dict[tuple[int, int], Preuve]
    empreintes: np.ndarray | None  # n × 768 (avec IA), sinon None
    duree_s: float
    _par_mode: dict[tuple[str, bool], ToutesLesPaires] = field(default_factory=dict, repr=False)

    @property
    def dossiers(self) -> list[int]:
        return [photo.dossier for photo in self.photos]

    def paires(self, mode: str, seuil: int, avec_ia: bool = True) -> Selection:
        """Les paires de ce mode au-dessus de ce seuil, les plus proches d'abord. `avec_ia=False` : les
        copies seulement (identiques et même photo), même si l'IA a servi."""
        cle = (mode, avec_ia and self.empreintes is not None)
        if cle not in self._par_mode:
            self._par_mode[cle] = self._toutes(*cle)
        return self._par_mode[cle].au_dessus(seuil)

    def details(self, a: int, b: int, preuve: Preuve | None) -> tuple[str, ...]:
        """Ce qui distingue deux photos prouvées être la même : « autre taille », « autre format »,
        « retournée », « autres couleurs », « bords ajoutés » ; sinon « autre compression »."""
        info_a, info_b = self.infos[a], self.infos[b]
        details = []
        if (info_a.largeur, info_a.hauteur) != (info_b.largeur, info_b.hauteur):
            details.append("autre taille")
        if info_a.format != info_b.format:
            details.append("autre format")
        if preuve is not None:
            if preuve.miroir:
                details.append("retournée")
            if preuve.autres_couleurs:
                details.append("autres couleurs")
            if preuve.bords:
                details.append("bords ajoutés")
        if not details:
            details.append("autre compression")
        return tuple(details)

    def cosinus(self, a: int, b: int) -> float | None:
        """La proximité vue par l'IA (de -1 à 1), quand l'IA a servi."""
        if self.empreintes is None:
            return None
        return float(np.dot(self.empreintes[a], self.empreintes[b]))

    def groupes(self, memes_photos: bool = False) -> list[int]:
        """Pour chaque photo, le numéro de son groupe (la première photo du groupe) : ses copies
        identiques ; avec `memes_photos`, aussi ses copies prouvées (même photo, modifiée). Les photos
        d'un groupe ont à peu près les mêmes ressemblances avec toutes les autres."""
        groupe = list(range(len(self.photos)))
        liees = self.identiques | self.memes_pixels | (set(self.preuves) if memes_photos else set())
        for a, b in sorted(liees):
            racine_a, racine_b = groupe[a], groupe[b]
            while groupe[racine_a] != racine_a:
                racine_a = groupe[racine_a]
            while groupe[racine_b] != racine_b:
                racine_b = groupe[racine_b]
            if racine_a != racine_b:
                groupe[max(racine_a, racine_b)] = min(racine_a, racine_b)
        for numero in range(len(groupe)):
            racine = groupe[numero]
            while groupe[racine] != racine:
                racine = groupe[racine]
            groupe[numero] = racine
        return groupe

    def _toutes(self, mode: str, avec_ia: bool) -> ToutesLesPaires:
        """Toutes les paires du mode. Les copies identiques entre elles sont toutes montrées ; les copies
        prouvées, une seule par couple de groupes de copies identiques ; les paires de l'IA, une seule
        par couple de groupes de copies (identiques ou prouvées). Sans cela, une photo présente en
        plusieurs exemplaires ferait apparaître chacune de ses ressemblances plusieurs fois."""
        permises = paires_permises(self.dossiers, mode) if self.photos else np.zeros((0, 0), dtype=bool)
        groupe = self.groupes()
        prouvees: list[Paire] = []
        connues: set[tuple[int, int]] = set()
        for a, b in sorted(self.identiques):
            if permises[a, b]:
                prouvees.append(Paire(a, b, 100, IDENTIQUES, ("même fichier",), self.cosinus(a, b)))
            connues.add((a, b))
        for a, b in sorted(self.memes_pixels - connues):
            if permises[a, b]:
                prouvees.append(Paire(a, b, 100, IDENTIQUES, ("mêmes pixels",), self.cosinus(a, b)))
            connues.add((a, b))
        couples_vus: set[tuple[int, int]] = set()
        meme_photo = [
            Paire(a, b, preuve.proximite(), MEME_PHOTO, self.details(a, b, preuve), self.cosinus(a, b))
            for (a, b), preuve in self.preuves.items()
            if (a, b) not in connues and permises[a, b]
        ]
        for paire in sorted(meme_photo, key=lambda p: p.cle_de_tri):
            couple = (min(groupe[paire.a], groupe[paire.b]), max(groupe[paire.a], groupe[paire.b]))
            if couple not in couples_vus:
                couples_vus.add(couple)
                prouvees.append(paire)
        connues |= set(self.preuves)
        if not avec_ia or self.empreintes is None or len(self.photos) < 2:
            return ToutesLesPaires(prouvees)
        restantes = np.triu(permises, 1)
        for a, b in connues:
            restantes[a, b] = False
        lignes, colonnes = np.nonzero(restantes)
        valeurs = np.einsum("ij,ij->i", self.empreintes[lignes], self.empreintes[colonnes]) if len(lignes) else np.zeros(0, dtype=np.float32)
        # Une seule paire par couple de groupes de copies : la plus proche (à égalité, les premières
        # photos), et aucune à l'intérieur d'un groupe (ses photos sont déjà montrées comme copies).
        groupe = self.groupes(memes_photos=True)
        groupes = np.asarray(groupe)
        g_a, g_b = groupes[lignes], groupes[colonnes]
        couples = np.minimum(g_a, g_b) * len(groupe) + np.maximum(g_a, g_b)
        ordre = np.lexsort((colonnes, lignes, -valeurs))
        _, premieres = np.unique(couples[ordre], return_index=True)
        gardees = np.array([k for k in sorted(ordre[premieres].tolist()) if g_a[k] != g_b[k]], dtype=np.int64)
        if len(gardees) == 0:
            return ToutesLesPaires(prouvees)
        return ToutesLesPaires(prouvees, lignes[gardees], colonnes[gardees], valeurs[gardees])


def memes_pixels(chemin_a: Path, chemin_b: Path) -> bool:
    """Vrai si les deux images, lues en entier et dans le bon sens, ont exactement les mêmes pixels."""
    try:
        with Image.open(chemin_a) as image_a, Image.open(chemin_b) as image_b:
            pixels_a = ImageOps.exif_transpose(image_a).convert("RGBA")
            pixels_b = ImageOps.exif_transpose(image_b).convert("RGBA")
            return pixels_a.size == pixels_b.size and ImageChops.difference(pixels_a, pixels_b).getbbox() is None
    except Exception:  # noqa: BLE001 : illisible : pas de preuve
        return False


def _lire(photo: Photo, signer: bool) -> tuple[PhotoLue, Signature | None]:
    lue = lire_la_photo(photo.chemin)
    return lue, (signature(lue.image) if signer else None)


def analyser(
    photos: Sequence[Photo],
    avec_ia: bool,
    memoire: Memoire,
    progres: Callable[[Avancement], None] | None = None,
    arret: threading.Event | None = None,
    descripteur_ia: Callable[[], object] | None = None,
) -> Resultat:
    """Analyse les photos. `descripteur_ia` : fonction qui donne le modèle (vision.descripteur par défaut ;
    les tests en donnent un faux, avec une méthode decrire(image)). Lance AnalyseArretee si `arret` est
    posé, vision.ErreurModele si le modèle d'IA manque ou est abîmé."""
    debut = time.perf_counter()
    arret = arret or threading.Event()
    dire = progres or (lambda _avancement: None)
    modele = None
    if avec_ia:
        dire(Avancement(MODELE))
        if descripteur_ia is None:
            from .vision import descripteur as descripteur_ia
        modele = descripteur_ia()
    etape = IA if avec_ia else LECTURE
    total = len(photos)
    dire(Avancement(etape, 0, total))

    lues: list[tuple[Photo, _Lue]] = []
    illisibles: list[tuple[Photo, str]] = []
    with ThreadPoolExecutor(max_workers=LECTEURS) as lecteurs:
        restantes = deque(photos)
        en_cours: deque[tuple[Photo, _Lue | None, Future | None]] = deque()

        def remplir() -> None:
            while restantes and len(en_cours) < EN_AVANCE:
                photo = restantes.popleft()
                deja = memoire.trouver(photo)
                if deja is not None and (deja.ia is not None or not avec_ia):
                    en_cours.append((photo, deja, None))  # déjà lue pendant la séance
                else:
                    en_cours.append((photo, deja, lecteurs.submit(_lire, photo, deja is None)))

        try:
            remplir()
            faites = 0
            while en_cours:
                if arret.is_set():
                    raise AnalyseArretee()
                photo, deja, futur = en_cours.popleft()
                remplir()
                if futur is None:
                    lues.append((photo, deja))
                else:
                    try:
                        lue_brute, signee = futur.result()
                    except Exception as erreur:  # noqa: BLE001 : une photo illisible n'arrête pas l'analyse
                        illisibles.append((photo, str(erreur) or type(erreur).__name__))
                    else:
                        lue = deja or _Lue(Infos(lue_brute.empreinte, lue_brute.largeur, lue_brute.hauteur, lue_brute.format), signee)
                        if modele is not None and lue.ia is None:
                            lue.ia = modele.decrire(lue_brute.image)
                        memoire.garder(photo, lue)
                        lues.append((photo, lue))
                faites += 1
                dire(Avancement(etape, faites, total))
        finally:
            for _photo, _deja, futur in en_cours:
                if futur is not None:
                    futur.cancel()

    dire(Avancement(COMPARAISON))
    photos_lues = [photo for photo, _lue in lues]
    infos = [lue.infos for _photo, lue in lues]
    signatures = [lue.signature for _photo, lue in lues]

    identiques: set[tuple[int, int]] = set()
    par_empreinte: dict[str, list[int]] = {}
    for numero, info in enumerate(infos):
        par_empreinte.setdefault(info.empreinte, []).append(numero)
    for groupe in par_empreinte.values():
        for rang, a in enumerate(groupe):
            for b in groupe[rang + 1 :]:
                identiques.add((a, b))

    preuves: dict[tuple[int, int], Preuve] = {}
    pixels: set[tuple[int, int]] = set()
    for a, b in paires_candidates(signatures):
        if arret.is_set():
            raise AnalyseArretee()
        if (a, b) in identiques:
            continue
        preuve = prouver(signatures[a], signatures[b])
        if preuve is None:
            continue
        preuves[(a, b)] = preuve
        memes_dimensions = (infos[a].largeur, infos[a].hauteur) == (infos[b].largeur, infos[b].hauteur)
        if memes_dimensions and not (preuve.miroir or preuve.bords) and preuve.ecart_de_couleurs < 1.0:
            if memes_pixels(photos_lues[a].chemin, photos_lues[b].chemin):
                pixels.add((a, b))

    empreintes = np.stack([lue.ia for _photo, lue in lues]).astype(np.float32) if avec_ia and lues else None
    return Resultat(photos_lues, infos, illisibles, avec_ia, identiques, pixels, preuves, empreintes, time.perf_counter() - debut)
