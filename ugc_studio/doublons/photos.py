"""Les photos à comparer : celles des dossiers ajoutés (et de leurs sous-dossiers, sur demande), et leur
lecture, la même pour la recherche des copies et pour l'IA.

- Mêmes règles que les modules Images et Renommer (ugc_studio/dossiers.py) : mêmes formats, ordre de
  l'Explorateur Windows, fichiers et dossiers cachés de Windows ignorés.
- Une photo trouvée deux fois (un dossier ajouté qui est le sous-dossier d'un autre, ou ajouté deux
  fois) ne compte qu'une fois, pour le premier dossier ajouté qui la contient.
- Lecture : une seule lecture du fichier, qui sert à son empreinte exacte (SHA-256) et à l'image. Un JPG
  est décodé directement en plus petit (« draft » de Pillow : 2, 4 ou 8 fois moins de pixels), assez
  grand pour la recherche des copies et pour l'IA. La photo est remise dans le bon sens (informations
  EXIF d'un téléphone), et une image transparente (un produit détouré en PNG) est posée sur du blanc.
"""

from __future__ import annotations

import hashlib
import io
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from ..dossiers import EXTENSIONS_IMAGES, est_cache, images_du_dossier, trier_comme_l_explorateur

# Le plus petit côté de l'image décodée, au moins (avant de retirer ses bords unis) : l'IA la décrit à
# 224 pixels de petit côté, la recherche des copies à 128 pixels de grand côté.
COTE_DE_LECTURE = 448


@dataclass(frozen=True)
class Photo:
    """Une photo à comparer : son chemin, le numéro du dossier ajouté qui la contient (pour « Comparer »
    : dans chaque dossier, entre les dossiers), sa taille en octets et sa date de modification (pour
    savoir, plus tard, si elle a changé depuis l'analyse)."""

    chemin: Path
    dossier: int
    octets: int
    modifiee: float

    @property
    def cle(self) -> tuple[str, int, float]:
        """Ce qui identifie cette version du fichier : son chemin, sa taille et sa date. Une photo
        modifiée depuis la dernière analyse a une autre clé : elle est relue."""
        return os.path.normcase(str(self.chemin)), self.octets, self.modifiee


def a_change(photo: Photo) -> bool:
    """Vrai si la photo a changé depuis l'analyse (V4.5) : déplacée, supprimée ou modifiée ailleurs (une
    autre taille ou une autre date). Une photo changée n'est jamais mise à la corbeille : elle n'est plus
    celle que la comparaison a montrée."""
    try:
        infos = photo.chemin.stat()
    except OSError:
        return True
    return (infos.st_size, infos.st_mtime) != (photo.octets, photo.modifiee)


def _dossiers_visibles(dossier: Path) -> list[Path]:
    """Les sous-dossiers d'un dossier (pas les dossiers cachés de Windows), dans l'ordre de l'Explorateur.
    Les raccourcis vers d'autres dossiers (liens) ne sont pas suivis : pas de boucle sans fin."""
    trouves = []
    try:
        entrees = list(os.scandir(dossier))
    except OSError:
        return []
    for entree in entrees:
        try:
            if not entree.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        chemin = Path(entree.path)
        if not est_cache(chemin):
            trouves.append(chemin)
    return trier_comme_l_explorateur(trouves)


def images_du_dossier_et_sous_dossiers(dossier: Path) -> list[Path]:
    """Les images du dossier, puis celles de chacun de ses sous-dossiers (dans l'ordre de l'Explorateur),
    à toutes les profondeurs."""
    images = list(images_du_dossier(dossier))
    for sous_dossier in _dossiers_visibles(dossier):
        images.extend(images_du_dossier_et_sous_dossiers(sous_dossier))
    return images


def lister_les_photos(dossiers: Sequence[Path], sous_dossiers: bool = False) -> list[Photo]:
    """Les photos des dossiers ajoutés, dans l'ordre des dossiers puis de l'Explorateur. Une photo
    trouvée deux fois ne compte qu'une fois (le premier dossier ajouté qui la contient)."""
    photos: list[Photo] = []
    vues: set[str] = set()
    for numero, dossier in enumerate(dossiers):
        chemins = images_du_dossier_et_sous_dossiers(dossier) if sous_dossiers else images_du_dossier(dossier)
        for chemin in chemins:
            if chemin.suffix.lower() not in EXTENSIONS_IMAGES:
                continue
            try:
                identite = os.path.normcase(os.path.realpath(chemin))
                infos = chemin.stat()
            except OSError:
                continue  # disparue entre-temps : elle ne compte pas
            if identite in vues:
                continue
            vues.add(identite)
            photos.append(Photo(chemin, numero, infos.st_size, infos.st_mtime))
    return photos


@dataclass(frozen=True)
class PhotoLue:
    """Une photo lue : l'empreinte exacte de son fichier, sa taille en pixels (dans le bon sens), son
    format, et l'image décodée (RGB, dans le bon sens, transparence posée sur du blanc)."""

    empreinte: str
    largeur: int
    hauteur: int
    format: str
    image: Image.Image


def lire_la_photo(chemin: Path, cote: int = COTE_DE_LECTURE) -> PhotoLue:
    """Lit la photo une seule fois. Lance une exception (OSError, erreur de Pillow) si elle est illisible."""
    donnees = chemin.read_bytes()
    empreinte = hashlib.sha256(donnees).hexdigest()
    with Image.open(io.BytesIO(donnees)) as ouverte:
        format_lu = (ouverte.format or chemin.suffix.lstrip(".")).upper()
        largeur, hauteur = ouverte.size
        orientation = ouverte.getexif().get(0x0112, 1)  # 5 à 8 : photo couchée (largeur et hauteur échangées)
        if orientation in (5, 6, 7, 8):
            largeur, hauteur = hauteur, largeur
        ouverte.draft("RGB", (cote, cote))  # JPG : décodé directement en plus petit (au moins `cote`)
        image = ImageOps.exif_transpose(ouverte)
        image.load()
    image = sur_fond_blanc(image)
    # Les autres formats (PNG, WebP…) sont décodés en entier : réduits aussitôt, pour la mémoire.
    reduction = min(image.size) // cote
    if reduction >= 2:
        image = image.reduce(reduction)
    return PhotoLue(empreinte, largeur, hauteur, format_lu, image)


def sur_fond_blanc(image: Image.Image) -> Image.Image:
    """L'image en RGB ; une image transparente est d'abord posée sur du blanc."""
    if image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info):
        image = image.convert("RGBA")
        fond = Image.new("RGBA", image.size, (255, 255, 255, 255))
        fond.alpha_composite(image)
        image = fond
    return image.convert("RGB")
