"""Les paires à montrer et leur note : une seule échelle, de 0 à 100 % (document V4.3, §4).

  100 %         Identiques     prouvé sans IA : le même fichier, ou les mêmes pixels
  95 à 99 %     Même photo     prouvé sans IA (copies.py) : plus elle a été modifiée, plus on descend
  94 % au plus  Ressemblantes  estimé par l'IA, réglé sur le lot de l'utilisateur

Seule une preuve fait entrer dans les deux zones du haut : deux photos que l'IA voit presque identiques,
mais que rien ne prouve être la même photo, restent à 94 % au plus. Le seuil garde donc toujours le même
sens : à 95 %, seulement des copies prouvées.
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .choix import (  # noqa: F401 : les noms des cas et des choix, sans calcul (choix.py)
    DANS_CHAQUE_DOSSIER,
    ENTRE_LES_DOSSIERS,
    IDENTIQUES,
    LES_DEUX,
    MAX_PAIRES,
    MEME_PHOTO,
    RESSEMBLANTES,
    SEUIL_DE_DEPART,
    SEUIL_MAX,
    SEUIL_MIN,
)

# La note de l'IA (zone estimée) : le cosinus des deux empreintes converti par cette table (points
# reliés par des droites), réglée le 11/10/2026 sur le lot de l'utilisateur (121 photos différentes de
# montres connectées, souvent au poignet) : la paire de photos différentes la plus proche est à 0,867,
# 99,9 % d'entre elles sont sous 0,851, la moitié sous 0,49 ; ses photos déclinées (autre taille, autres
# couleurs, recadrées…) sont presque toutes au-dessus de 0,87. Avec le seuil de départ (85 %), aucune paire
# de photos différentes de ce lot ne ressort.
TABLE_IA = ((0.0, 0.0), (0.50, 50.0), (0.75, 70.0), (0.87, 84.0), (0.95, 94.0))
PLAFOND_ESTIME = 94


def note_de_l_ia(cosinus: float) -> int:
    """La note (en %) d'une paire que seule l'IA a vue, de 0 à 94."""
    abscisses, notes = zip(*TABLE_IA)
    return int(min(PLAFOND_ESTIME, max(0, round(float(np.interp(cosinus, abscisses, notes))))))


def paires_permises(dossiers: Sequence[int], mode: str) -> np.ndarray:
    """Matrice (n × n) des paires à comparer selon « Comparer » : dans chaque dossier, entre les dossiers,
    ou les deux. Avec un seul dossier, toutes les paires."""
    numeros = np.asarray(dossiers)
    meme = numeros[:, None] == numeros[None, :]
    if mode == DANS_CHAQUE_DOSSIER:
        permises = meme
    elif mode == ENTRE_LES_DOSSIERS:
        permises = ~meme
    else:
        permises = np.ones_like(meme)
    permises = permises.copy()
    np.fill_diagonal(permises, False)
    return permises


@dataclass(frozen=True)
class Paire:
    """Deux photos (leurs numéros dans la liste), leur note, ce qu'elles sont (IDENTIQUES, MEME_PHOTO,
    RESSEMBLANTES), ce qui les distingue (« autre taille », « retournée »…), et leur proximité vue par
    l'IA (le cosinus, quand l'IA a servi)."""

    a: int
    b: int
    proximite: int
    genre: str
    details: tuple[str, ...] = ()
    ia: float | None = None
    recadrage: object | None = None  # V4.4 : la preuve, quand l'une est l'autre recadrée (recadrages.PreuveRecadrage)

    @property
    def cle_de_tri(self) -> tuple:
        return (-self.proximite, -(self.ia if self.ia is not None else 2.0), self.a, self.b)


@dataclass(frozen=True)
class Selection:
    """Les paires au-dessus du seuil (les MAX_PAIRES plus proches au plus), et leur nombre réel."""

    paires: list[Paire]
    total: int

    @property
    def tronquee(self) -> bool:
        return self.total > len(self.paires)

    def compte(self, genre: str) -> int:
        return sum(1 for paire in self.paires if paire.genre == genre)


class ToutesLesPaires:
    """Toutes les paires notées au moins SEUIL_MIN, triées de la plus proche à la moins proche : changer
    le seuil ne fait que prendre le début de la liste (instantané, même pour des milliers de photos).

    `prouvees` : les paires identiques ou prouvées (notées 95 % ou plus : toujours avant celles de l'IA) ;
    les paires vues par l'IA sont gardées en tableaux (numéros des deux photos, cosinus) et ne deviennent
    des objets Paire qu'au moment d'être montrées."""

    def __init__(self, prouvees: list[Paire], ia_a=None, ia_b=None, ia_cosinus=None):
        self._prouvees = sorted(prouvees, key=lambda p: p.cle_de_tri)
        self._notes_prouvees = [-p.proximite for p in self._prouvees]
        if ia_cosinus is None or len(ia_cosinus) == 0:
            ia_a = ia_b = np.zeros(0, dtype=np.int64)
            ia_cosinus = np.zeros(0, dtype=np.float32)
        abscisses, notes = zip(*TABLE_IA)
        ia_notes = np.minimum(PLAFOND_ESTIME, np.clip(np.rint(np.interp(ia_cosinus, abscisses, notes)), 0, None)).astype(np.int64)
        gardees = ia_notes >= SEUIL_MIN
        ia_a, ia_b, ia_cosinus, ia_notes = (np.asarray(x)[gardees] for x in (ia_a, ia_b, ia_cosinus, ia_notes))
        ordre = np.lexsort((ia_b, ia_a, -ia_cosinus, -ia_notes))
        self._ia_a, self._ia_b = ia_a[ordre], ia_b[ordre]
        self._ia_cosinus, self._ia_notes = ia_cosinus[ordre], ia_notes[ordre]

    def __len__(self) -> int:
        return len(self._prouvees) + len(self._ia_notes)

    def au_dessus(self, seuil: int, maximum: int = MAX_PAIRES) -> Selection:
        prouvees = bisect.bisect_right(self._notes_prouvees, -seuil)
        estimees = int(np.searchsorted(-self._ia_notes, -seuil, side="right"))
        total = prouvees + estimees
        paires = self._prouvees[: min(prouvees, maximum)]
        for k in range(max(0, min(estimees, maximum - len(paires)))):
            paires.append(Paire(int(self._ia_a[k]), int(self._ia_b[k]), int(self._ia_notes[k]), RESSEMBLANTES, (), float(self._ia_cosinus[k])))
        return Selection(paires, total)
