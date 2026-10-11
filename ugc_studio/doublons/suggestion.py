"""La suggestion (V4.5, lot 3 de Doublons ; document V4.3, §3.5) : pour la même photo en deux versions,
celle à garder. Rien n'est jamais supprimé sans un clic : ce n'est qu'une aide pour décider vite.

Pas de suggestion pour deux photos qui se ressemblent seulement (« Ressemblantes ») : c'est une question
de goût. Pour deux copies identiques : l'une ou l'autre (sauf si le nom de l'une est celui d'une copie).

L'ordre des raisons, pour la même photo en deux versions :
1. une partie de la photo (recadrée, zoomée) : garder la photo entière ;
2. des bords unis ajoutés sur l'une : garder celle sans bords (la photo d'origine) ;
3. la plus grande (plus de pixels) ;
4. à taille égale et dans le même format : la moins compressée (le fichier le plus lourd). Deux formats
   différents ne se comparent pas ainsi : un PNG fait d'après un JPG est plus lourd sans être meilleur
   (relu sur les captures de la fabrication : « format sans perte, PNG » était proposé pour une copie
   retournée en PNG, sans raison de la préférer) ;
5. celle dont le nom n'est pas celui d'une copie (« - Copie », « (1) », « Copie de »…).
Quand leurs couleurs diffèrent, la suggestion le rappelle : on peut préférer les couleurs de l'autre.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePath

from .choix import IDENTIQUES, MEME_PHOTO

ECART_DE_TAILLE = 0.02  # au moins 2 % de pixels en plus : « plus grande »
ECART_DE_POIDS = 0.05  # même taille, même format, au moins 5 % d'octets en plus : « moins compressée »

# Les noms que Windows, les navigateurs ou l'utilisateur donnent à une copie : « photo - Copie »,
# « photo - Copie (2) », « photo - Copy », « Copie de photo », « Copy of photo », « photo (1) »,
# « photo_copie ».
NOM_DE_COPIE = re.compile(
    r"(\s-\s(copie|copy)(\s\(\d+\))?$)|(^(copie|copy)(\sde|\sof)?\s)|(\s\(\d+\)$)|([_\s-](copie|copy)$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Suggestion:
    """`garder` : 0 la première photo de la paire (à gauche), 1 la seconde (à droite), None l'une ou
    l'autre ; `raison` : pourquoi (« plus grande ») ; `couleurs` : leurs couleurs diffèrent."""

    garder: int | None
    raison: str
    couleurs: bool = False

    def texte(self) -> str:
        """« Suggestion : garder celle de gauche (plus grande). »"""
        if self.garder is None:
            return f"Suggestion : garder l'une ou l'autre ({self.raison})."
        cote = "celle de gauche" if self.garder == 0 else "celle de droite"
        suite = ", si ses couleurs te conviennent" if self.couleurs else ""
        return f"Suggestion : garder {cote} ({self.raison}){suite}."


def nom_de_copie(nom: str) -> bool:
    """Vrai si le nom (avec ou sans extension) est celui d'une copie (« photo - Copie.jpg », « photo (1).jpg »)."""
    return bool(NOM_DE_COPIE.search(PurePath(nom).stem))


def _celle_qui_n_est_pas_une_copie(noms: tuple[str, str]) -> int | None:
    copies = (nom_de_copie(noms[0]), nom_de_copie(noms[1]))
    if copies[0] == copies[1]:
        return None
    return 1 if copies[0] else 0


def suggerer(
    genre: str,
    pixels: tuple[int, int],
    formats: tuple[str, str],
    octets: tuple[int, int],
    noms: tuple[str, str],
    recadrage=None,
    bords_sur: int = -1,
    autres_couleurs: bool = False,
) -> Suggestion | None:
    """La suggestion pour une paire (voir en haut du fichier), ou None. `recadrage` : la preuve d'un
    recadrage (recadrages.PreuveRecadrage) ; `bords_sur` : 0 ou 1 si l'une des deux a des bords unis
    ajoutés (copies.Preuve), -1 sinon."""
    if genre == IDENTIQUES:
        originale = _celle_qui_n_est_pas_une_copie(noms)
        if originale is not None:
            return Suggestion(originale, "l'autre a un nom de copie")
        return Suggestion(None, "ce sont les mêmes pixels")
    if genre != MEME_PHOTO:
        return None
    if recadrage is not None and recadrage.recadree:
        return Suggestion(1 - recadrage.extrait, "la photo entière", autres_couleurs)
    if bords_sur in (0, 1):
        return Suggestion(1 - bords_sur, "sans les bords ajoutés", autres_couleurs)
    if max(pixels) > min(pixels) * (1 + ECART_DE_TAILLE):
        return Suggestion(0 if pixels[0] > pixels[1] else 1, "plus grande", autres_couleurs)
    if formats[0] == formats[1] and max(octets) > min(octets) * (1 + ECART_DE_POIDS):
        return Suggestion(0 if octets[0] > octets[1] else 1, "moins compressée", autres_couleurs)
    originale = _celle_qui_n_est_pas_une_copie(noms)
    if originale is not None:
        return Suggestion(originale, "l'autre a un nom de copie", autres_couleurs)
    return None
