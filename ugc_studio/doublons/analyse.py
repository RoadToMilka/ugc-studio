"""L'analyse d'un lot de photos (V4.3) : lire chaque photo une fois, trouver les copies entières (sans
IA) et, avec une méthode avec IA, décrire chaque photo par le modèle, puis prouver les copies
recadrées, zoomées ou tournées (V4.4, recadrages.py). Sans interface : la page Doublons la lance en
arrière-plan, et le résultat lui permet de montrer les paires de n'importe quelle méthode, de
n'importe quel mode (« Comparer ») et de n'importe quel seuil sans rien refaire.

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
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageOps

from . import recadrages
from .choix import AVEC_IA, COMPARAISON, COPIES_IA, IA, LECTURE, MODELE, RECADRAGES
from .copies import Preuve, Signature, paires_candidates, prouver, rogner_bords_unis, signature
from .paires import IDENTIQUES, MEME_PHOTO, Paire, Selection, ToutesLesPaires, paires_permises
from .photos import Photo, PhotoLue, lire_la_photo
from .recadrages import Detail, PreuveRecadrage
from .suggestion import Suggestion, suggerer

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
    detail: Detail | None = None  # ses carreaux et sa photo réduite, pour les recadrages (avec IA)


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
    la raison. Les paires se demandent à paires(mode, seuil).

    V4.5 : les décisions de la séance, pour cette analyse seulement (rien n'est retenu d'une analyse à
    l'autre) : `retirees`, les photos mises à la corbeille (leurs paires disparaissent) ; `ignorees`, les
    paires ignorées."""

    photos: list[Photo]
    infos: list[Infos]
    illisibles: list[tuple[Photo, str]]
    avec_ia: bool
    identiques: set[tuple[int, int]]
    memes_pixels: set[tuple[int, int]]
    preuves: dict[tuple[int, int], Preuve]
    empreintes: np.ndarray | None  # n × 768 (avec IA), sinon None
    duree_s: float
    recadrages: dict[tuple[int, int], PreuveRecadrage] = field(default_factory=dict)  # V4.4 (avec IA)
    retirees: set[int] = field(default_factory=set)  # V4.5
    ignorees: set[tuple[int, int]] = field(default_factory=set)  # V4.5
    _par_mode: dict[tuple[str, str], ToutesLesPaires] = field(default_factory=dict, repr=False)
    _etendus: dict[tuple[int, int], PreuveRecadrage] | None = field(default=None, repr=False)

    @property
    def dossiers(self) -> list[int]:
        return [photo.dossier for photo in self.photos]

    # --- Décisions de la séance (V4.5) -------------------------------------------------------------

    def retirer(self, numero: int) -> None:
        """La photo a été mise à la corbeille : ses paires disparaissent. Si elle représentait d'autres
        copies (la première d'un groupe), une de ses copies prend sa place dans les paires montrées."""
        self.retirees.add(numero)
        self._par_mode.clear()

    def remettre(self, numero: int) -> None:
        """« Annuler » : la photo est revenue, ses paires aussi."""
        self.retirees.discard(numero)
        self._par_mode.clear()

    def ignorer(self, a: int, b: int) -> None:
        """La paire est masquée pour cette analyse ; aussi les autres paires des mêmes groupes de copies
        (ce sont les mêmes photos : elles ne la remplacent pas)."""
        self.ignorees.add((min(a, b), max(a, b)))
        self._par_mode.clear()

    def ne_plus_ignorer(self, a: int, b: int) -> None:
        self.ignorees.discard((min(a, b), max(a, b)))
        self._par_mode.clear()

    def paires(self, mode: str, seuil: int, methode: str = AVEC_IA) -> Selection:
        """Les paires de ce mode au-dessus de ce seuil, les plus proches d'abord, selon la méthode :
        SANS_IA, les copies entières (identiques et même photo entière, même si l'IA a servi) ;
        COPIES_IA, aussi les copies recadrées, zoomées ou tournées ; AVEC_IA, aussi les photos que l'IA
        juge proches. Sans l'IA à l'analyse, les deux dernières ne montrent que les copies entières."""
        cle = (mode, methode)
        if cle not in self._par_mode:
            self._par_mode[cle] = self._toutes(mode, methode)
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

    def details_du_recadrage(self, a: int, b: int, preuve: PreuveRecadrage) -> tuple[str, ...]:
        """Ce qui distingue deux photos dont l'une est l'autre recadrée, zoomée ou tournée : « recadrée
        (55 % gardée) », « tournée de 6° », « retournée », « autres couleurs », et « autre format »."""
        details = list(preuve.details())
        if self.infos[a].format != self.infos[b].format:
            details.append("autre format")
        return tuple(details) or ("autre taille",)

    def suggestion(self, paire: Paire) -> Suggestion | None:
        """Celle des deux photos à garder (V4.5, suggestion.py), ou None (deux photos seulement
        ressemblantes : une question de goût)."""
        a, b = paire.a, paire.b
        info_a, info_b = self.infos[a], self.infos[b]
        preuve = self.preuves.get((a, b))
        return suggerer(
            paire.genre,
            pixels=(info_a.largeur * info_a.hauteur, info_b.largeur * info_b.hauteur),
            formats=(info_a.format, info_b.format),
            octets=(self.photos[a].octets, self.photos[b].octets),
            noms=(self.photos[a].chemin.name, self.photos[b].chemin.name),
            recadrage=paire.recadrage,
            bords_sur=preuve.bords_sur if preuve is not None else -1,
            autres_couleurs="autres couleurs" in paire.details,
        )

    def cosinus(self, a: int, b: int) -> float | None:
        """La proximité vue par l'IA (de -1 à 1), quand l'IA a servi."""
        if self.empreintes is None:
            return None
        return float(np.dot(self.empreintes[a], self.empreintes[b]))

    def groupes(self, memes_photos: bool = False) -> list[int]:
        """Pour chaque photo, le numéro de son groupe (la première photo du groupe) : ses copies
        identiques ; avec `memes_photos`, aussi ses copies prouvées (même photo, modifiée). Les photos
        d'un groupe ont à peu près les mêmes ressemblances avec toutes les autres. Les photos mises à la
        corbeille ne relient plus rien (chacune seule dans son groupe)."""
        liens = self.identiques | self.memes_pixels
        if memes_photos:
            liens = liens | set(self.preuves) | set(self.recadrages)
        return self._groupes(liens)

    def _groupes(self, liens: set[tuple[int, int]], sans: set[int] | None = None) -> list[int]:
        """Les groupes formés par ces liens (deux photos liées sont dans le même groupe), sans les photos
        de `sans` (les photos mises à la corbeille, au départ). Le numéro d'un groupe : sa première photo."""
        sans = self.retirees if sans is None else sans
        groupe = list(range(len(self.photos)))

        def racine(numero: int) -> int:
            while groupe[numero] != numero:
                groupe[numero] = groupe[groupe[numero]]
                numero = groupe[numero]
            return numero

        for a, b in sorted(liens):
            if a in sans or b in sans:
                continue
            racine_a, racine_b = racine(a), racine(b)
            if racine_a != racine_b:
                groupe[max(racine_a, racine_b)] = min(racine_a, racine_b)
        return [racine(numero) for numero in range(len(groupe))]

    def recadrages_etendus(self) -> dict[tuple[int, int], PreuveRecadrage]:
        """Les copies recadrées prouvées, et les mêmes pour les copies identiques (mêmes pixels) de leurs
        photos : la preuve est la même. L'analyse ne cherche les recadrages que pour une photo par groupe
        de copies identiques ; si celle-là est mise à la corbeille, sa copie garde ses recadrages."""
        if self._etendus is None:
            identiques = self._groupes(self.identiques | self.memes_pixels, sans=set())
            membres: dict[int, list[int]] = {}
            for numero, groupe in enumerate(identiques):
                membres.setdefault(groupe, []).append(numero)
            etendus = dict(self.recadrages)
            for (a, b), preuve in self.recadrages.items():
                for x in membres[identiques[a]]:
                    for y in membres[identiques[b]]:
                        if x < y:
                            etendus.setdefault((x, y), preuve)
                        elif y < x:  # dans l'autre ordre : l'extrait change de côté
                            etendus.setdefault((y, x), replace(preuve, extrait=1 - preuve.extrait))
            self._etendus = etendus
        return self._etendus

    def _ignorees_par_couple(self, liens: set[tuple[int, int]]) -> tuple[list[int], set[tuple[int, int]]]:
        """Les groupes formés par ces liens, photos mises à la corbeille comprises, et les couples de
        groupes dont une paire est ignorée. Avec les photos mises à la corbeille : une paire ignorée, puis
        l'une de ses photos mise à la corbeille, ne revient pas par une copie de cette photo (relecture
        indépendante de la 4.5.0)."""
        complets = self._groupes(liens, sans=set())
        return complets, {(min(complets[a], complets[b]), max(complets[a], complets[b])) for a, b in self.ignorees}

    def _une_par_couple(self, paires: list[Paire], liens: set[tuple[int, int]]) -> list[Paire]:
        """Une seule paire par couple de groupes (formés par ces liens, sans les photos mises à la
        corbeille) : la plus proche (à égalité, les premières photos). Aucune pour un couple dont une paire
        est ignorée : ce sont les mêmes photos."""
        groupe = self._groupes(liens)
        complets, ignores = self._ignorees_par_couple(liens)
        vus: set[tuple[int, int]] = set()
        gardees = []
        for paire in sorted(paires, key=lambda p: p.cle_de_tri):
            a, b = paire.a, paire.b
            if (min(complets[a], complets[b]), max(complets[a], complets[b])) in ignores:
                continue
            couple = (min(groupe[a], groupe[b]), max(groupe[a], groupe[b]))
            if couple not in vus:
                vus.add(couple)
                gardees.append(paire)
        return gardees

    def _toutes(self, mode: str, methode: str) -> ToutesLesPaires:
        """Toutes les paires du mode et de la méthode, sans les photos mises à la corbeille ni les paires
        ignorées. Les copies identiques entre elles sont toutes montrées ; les copies entières, une seule
        par couple de groupes de copies identiques ; les copies recadrées, une seule par couple de
        familles (une photo, ses copies identiques et ses copies entières) ; les paires de l'IA, une seule
        par couple de groupes de copies (identiques ou prouvées). Sans cela, une photo présente en
        plusieurs exemplaires ferait apparaître chacune de ses ressemblances plusieurs fois. Les groupes
        sont faits sans les photos mises à la corbeille : une copie qui reste prend leur place."""
        permises = paires_permises(self.dossiers, mode) if self.photos else np.zeros((0, 0), dtype=bool)
        if self.retirees:
            retirees = sorted(self.retirees)
            permises[retirees, :] = False
            permises[:, retirees] = False
        identiques = self.identiques | self.memes_pixels
        prouvees: list[Paire] = []
        connues: set[tuple[int, int]] = set()
        for a, b in sorted(self.identiques):
            if permises[a, b] and (a, b) not in self.ignorees:
                prouvees.append(Paire(a, b, 100, IDENTIQUES, ("même fichier",), self.cosinus(a, b)))
            connues.add((a, b))
        for a, b in sorted(self.memes_pixels - connues):
            if permises[a, b] and (a, b) not in self.ignorees:
                prouvees.append(Paire(a, b, 100, IDENTIQUES, ("mêmes pixels",), self.cosinus(a, b)))
            connues.add((a, b))
        entieres = [
            Paire(a, b, preuve.proximite(), MEME_PHOTO, self.details(a, b, preuve), self.cosinus(a, b))
            for (a, b), preuve in self.preuves.items()
            if (a, b) not in connues and permises[a, b]
        ]
        prouvees += self._une_par_couple(entieres, identiques)
        connues |= set(self.preuves)
        etendus = self.recadrages_etendus() if methode in (COPIES_IA, AVEC_IA) else {}
        recadrees = [
            Paire(a, b, preuve.proximite(), MEME_PHOTO, self.details_du_recadrage(a, b, preuve), self.cosinus(a, b), preuve)
            for (a, b), preuve in etendus.items()
            if (a, b) not in connues and permises[a, b]
        ]
        prouvees += self._une_par_couple(recadrees, identiques | set(self.preuves))
        if methode != AVEC_IA or self.empreintes is None or len(self.photos) < 2:
            return ToutesLesPaires(prouvees)
        connues |= set(etendus)
        restantes = np.triu(permises, 1)
        for a, b in connues:
            restantes[a, b] = False
        lignes, colonnes = np.nonzero(restantes)
        valeurs = np.einsum("ij,ij->i", self.empreintes[lignes], self.empreintes[colonnes]) if len(lignes) else np.zeros(0, dtype=np.float32)
        # Une seule paire par couple de groupes de copies : la plus proche (à égalité, les premières
        # photos), et aucune à l'intérieur d'un groupe (ses photos sont déjà montrées comme copies), ni
        # pour un couple dont une paire est ignorée.
        liens = identiques | set(self.preuves) | set(etendus)
        groupe = self._groupes(liens)
        groupes = np.asarray(groupe)
        g_a, g_b = groupes[lignes], groupes[colonnes]
        n = len(groupe)
        couples = np.minimum(g_a, g_b) * n + np.maximum(g_a, g_b)
        # Les couples ignorés, d'après les groupes qui gardent les photos mises à la corbeille.
        complets, ignores = self._ignorees_par_couple(liens)
        if ignores:
            complets_a, complets_b = np.asarray(complets)[lignes], np.asarray(complets)[colonnes]
            codes = np.minimum(complets_a, complets_b) * n + np.maximum(complets_a, complets_b)
            ignorees = np.isin(codes, [x * n + y for x, y in ignores])
        else:
            ignorees = np.zeros(len(lignes), dtype=bool)
        # La plus proche de chaque couple est choisie parmi les paires qui ne sont pas ignorées.
        garder = ~ignorees
        lignes, colonnes, valeurs, g_a, g_b, couples = (x[garder] for x in (lignes, colonnes, valeurs, g_a, g_b, couples))
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
                            _decrire(modele, lue, lue_brute.image)
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
    resultat = Resultat(photos_lues, infos, illisibles, avec_ia, identiques, pixels, preuves, empreintes, 0.0)
    if empreintes is not None:
        details = [lue.detail for _photo, lue in lues]
        resultat.recadrages = _recadrages(resultat, details, dire, arret)
    resultat.duree_s = time.perf_counter() - debut
    return resultat


def _decrire(modele, lue: _Lue, image: Image.Image) -> None:
    """L'empreinte de la photo pour l'IA et, si le modèle les donne, ses carreaux (V4.4) : ce qu'il faut
    pour prouver un recadrage. Un modèle sans carreaux (les faux modèles des tests) donne l'empreinte
    seule : pas de recherche des recadrages pour cette photo."""
    if hasattr(modele, "decrire_rognee"):
        rognee, _bords = rogner_bords_unis(image)
        lue.ia, carreaux = modele.decrire_rognee(rognee)
        lue.detail = recadrages.detail(rognee, carreaux)
    else:
        lue.ia = modele.decrire(image)


def _recadrages(resultat: Resultat, details: list[Detail | None], dire, arret: threading.Event) -> dict[tuple[int, int], PreuveRecadrage]:
    """Les copies recadrées, zoomées ou tournées (V4.4) : les paires que l'IA voit assez proches
    (recadrages.paires_a_examiner), prouvées sans IA (recadrages.prouver)."""
    connues = resultat.identiques | resultat.memes_pixels | set(resultat.preuves)
    # Une photo par groupe de copies identiques (leurs preuves sont les mêmes : Resultat.recadrages_etendus),
    # mais chaque copie entière (autre taille, autres couleurs…) : si l'une est mise à la corbeille
    # (V4.5), l'autre garde ses copies recadrées.
    a_examiner = [
        (a, b)
        for a, b in recadrages.paires_a_examiner(resultat.empreintes, resultat.groupes(), connues, familles=resultat.groupes(memes_photos=True))
        if details[a] is not None and details[b] is not None
    ]
    trouves: dict[tuple[int, int], PreuveRecadrage] = {}
    dire(Avancement(RECADRAGES, 0, len(a_examiner)))
    for rang, (a, b) in enumerate(a_examiner):
        if arret.is_set():
            raise AnalyseArretee()
        taille_a = (resultat.infos[a].largeur, resultat.infos[a].hauteur)
        taille_b = (resultat.infos[b].largeur, resultat.infos[b].hauteur)
        preuve = recadrages.prouver(details[a], details[b], taille_a, taille_b, graine=a * 100_003 + b)
        if preuve is not None:
            trouves[(a, b)] = preuve
        if rang % 16 == 15 or rang == len(a_examiner) - 1:
            dire(Avancement(RECADRAGES, rang + 1, len(a_examiner)))
    return trouves
