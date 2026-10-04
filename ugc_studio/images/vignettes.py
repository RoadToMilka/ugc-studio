"""Vignettes d'images (V4, lot 2 : module Renommer) : une petite copie de chaque image, pour la
reconnaître d'un coup d'œil. Faites en arrière-plan, plusieurs à la fois : l'affichage se remplit au
fur et à mesure, même pour un dossier de plusieurs centaines d'images.

Rapide même pour de grandes photos : un JPG est décodé directement en petit (Pillow demande au
décodeur une image 2, 4 ou 8 fois plus petite, « draft »), au lieu d'être décodé en entier puis réduit.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageOps

TRAVAILLEURS = 4  # vignettes faites en même temps (le décodage de Pillow se fait en parallèle)


def vignette(chemin: Path, cote: int) -> Image.Image:
    """L'image en petit, au plus `cote` × `cote` pixels (proportions gardées), dans le bon sens (une
    photo enregistrée couchée est redressée), en RGBA (transparence gardée)."""
    with Image.open(chemin) as image:
        image.draft("RGB", (cote, cote))  # JPG : décodé directement en petit (au moins `cote`)
        droite = ImageOps.exif_transpose(image)
        droite.thumbnail((cote, cote), Image.Resampling.BICUBIC, reducing_gap=2.0)
        return droite.convert("RGBA")


def faire_les_vignettes(
    chemins: Sequence[Path],
    cote: int,
    convertir: Callable[[Image.Image], object],
    progres: Callable[[tuple[Path, object]], None],
    arret: threading.Event,
) -> int:
    """Fait la vignette de chaque image et la donne aussitôt à `progres((chemin, convertir(vignette)))`
    (None si l'image est illisible). `convertir` la prépare pour l'affichage (en QImage, par exemple),
    dans le fil de travail. S'arrête dès que `arret` est posé (autre dossier, fermeture de l'app).
    Renvoie le nombre de vignettes données."""

    def une(chemin: Path):
        if arret.is_set():
            return chemin, None, False
        try:
            return chemin, convertir(vignette(chemin, cote)), True
        except Exception:  # noqa: BLE001 : une image illisible garde une case vide, sans bloquer les autres
            return chemin, None, True

    donnees = 0
    with ThreadPoolExecutor(max_workers=TRAVAILLEURS) as travailleurs:
        for fait in as_completed([travailleurs.submit(une, chemin) for chemin in chemins]):
            chemin, image, traitee = fait.result()
            if arret.is_set():
                break
            if traitee:
                progres((chemin, image))
                donnees += 1
    return donnees
