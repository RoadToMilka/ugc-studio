"""Redimensionner toutes les images d'un dossier à la même taille (V4, lot 1 ; cahier des charges §8 bis).

Le parcours : on lit les images du dossier (leur taille et leur format, sans les décoder : rapide),
on prépare le « plan » (la taille finale de chaque image, selon la taille visée), puis on fabrique les
nouvelles images dans le dossier de sortie, plusieurs à la fois (une par cœur du processeur, jusqu'à
quatre). Les originaux ne sont jamais modifiés.

Les choix, et pourquoi :
- **Toutes à la taille visée** (décision de l'utilisateur du 04/10/2026) : avec « 600 px de haut »,
  une image plus grande est réduite, une plus petite agrandie. Une image déjà à la bonne taille est
  copiée telle quelle : aucun calcul inutile, aucune perte.
- **Proportions gardées** : l'autre côté suit, arrondi au pixel le plus proche (1080 × 1920 → 338 × 600).
- **Filtre Lanczos par défaut** : le plus fidèle, en réduction comme en agrandissement (tableau de
  comparaison de Pillow ; mesuré aussi sur de vraies photos, document V4 §4.1). Bicubique et
  bilinéaire restent au choix.
- **Photos de téléphone** : beaucoup sont enregistrées couchées, avec une note « à tourner »
  (l'orientation EXIF). L'image est d'abord tournée ; sinon, sa « hauteur » serait mesurée sur le
  mauvais côté.
- **Couleurs** : le profil de couleurs de l'original (ex. Display P3) est recopié, sinon les couleurs
  deviendraient plus ternes ; les informations de la photo (EXIF : date, appareil) aussi.
- **Qualité** : un JPG garde la qualité de l'original (on reprend ses « tables de compression », les
  réglages qui fixent sa qualité : ni plus lourd, ni plus dégradé) ; ou une qualité choisie. PNG, TIFF
  et BMP sont sans perte ; un WebP sans perte le reste ; WebP et AVIF avec perte : qualité 90.
- **Image en palette** (PNG de 256 couleurs) : passée en couleurs complètes avant le calcul. Pillow
  ne sait la redimensionner qu'au « plus proche voisin » (des escaliers sur les bords), quel que soit
  le filtre demandé.
- **Écriture sûre** : chaque image s'écrit sous un nom provisoire (« ….en-cours »), renommé à la fin ;
  un problème en cours de route ne laisse jamais une image à moitié écrite.
"""

from __future__ import annotations

import math
import os
import shutil
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps, JpegImagePlugin

from ..dossiers import images_du_dossier

# Côté qui reçoit la taille visée.
HAUTEUR, LARGEUR, PLUS_GRAND_COTE = "hauteur", "largeur", "plus_grand_cote"
COTES = {HAUTEUR: "Hauteur", LARGEUR: "Largeur", PLUS_GRAND_COTE: "Plus grand côté"}

# Filtres de calcul (voir en haut du fichier).
LANCZOS, BICUBIQUE, BILINEAIRE = "lanczos", "bicubique", "bilineaire"
FILTRES = {LANCZOS: "Lanczos", BICUBIQUE: "Bicubique", BILINEAIRE: "Bilinéaire"}
_FILTRES_PILLOW = {
    LANCZOS: Image.Resampling.LANCZOS,
    BICUBIQUE: Image.Resampling.BICUBIC,
    BILINEAIRE: Image.Resampling.BILINEAR,
}

# Qualité des JPG (et des WebP et AVIF avec perte). Pillow conseille de ne pas dépasser 95 : au-delà,
# le fichier grossit beaucoup sans différence visible.
COMME_L_ORIGINAL = 0
QUALITES = {
    COMME_L_ORIGINAL: "Comme l'original",
    95: "Très haute (95)",
    90: "Haute (90)",
    85: "Bonne (85)",
    80: "Web (80)",
}
QUALITE_WEBP_AVIF = 90  # « Comme l'original » pour un WebP ou un AVIF avec perte (Pillow ne lit pas leur qualité)

PIXELS_MIN, PIXELS_MAX = 1, 20_000
PIXELS_PAR_DEFAUT = 600
# Au-delà de ×2, une image agrandie paraît nettement plus douce : le résumé la signale en orange.
AGRANDISSEMENT_FORT = 2.0
TRAVAILLEURS_MAX = 4  # images préparées en même temps (une par cœur du processeur, jusqu'à quatre)

FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
    ".avif": "AVIF",
    ".tif": "TIFF",
    ".tiff": "TIFF",
    ".bmp": "BMP",
}
# Formats qui savent garder les informations de la photo (EXIF).
_FORMATS_AVEC_EXIF = {"JPEG", "PNG", "WEBP", "AVIF", "TIFF"}
# Compressions TIFF reprises telles quelles (les autres, propres aux images en noir et blanc pur, non).
_COMPRESSIONS_TIFF = {"tiff_lzw", "tiff_adobe_deflate", "tiff_deflate", "packbits", "jpeg"}
ORIENTATION = 0x0112  # étiquette EXIF de l'orientation
_ORIENTATIONS_COUCHEES = {5, 6, 7, 8}  # largeur et hauteur échangées à l'affichage

REDUITE, AGRANDIE, INCHANGEE = "reduite", "agrandie", "inchangee"
EXTENSION_PROVISOIRE = ".en-cours"


# --- Taille visée ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cible:
    """La taille visée : un côté (hauteur, largeur ou plus grand côté) et son nombre de pixels."""

    cote: str = HAUTEUR
    pixels: int = PIXELS_PAR_DEFAUT

    def nom_du_dossier(self) -> str:
        """Nom du sous-dossier de sortie : « 600 px de haut »."""
        return {
            HAUTEUR: f"{self.pixels} px de haut",
            LARGEUR: f"{self.pixels} px de large",
            PLUS_GRAND_COTE: f"{self.pixels} px (plus grand côté)",
        }[self.cote]

    def description(self) -> str:
        """« à 600 px de haut »."""
        return {
            HAUTEUR: f"à {self.pixels} px de haut",
            LARGEUR: f"à {self.pixels} px de large",
            PLUS_GRAND_COTE: f"à {self.pixels} px sur le plus grand côté",
        }[self.cote]


def _arrondi(valeur: float) -> int:
    """Au pixel le plus proche, la moitié vers le haut (337,5 → 338), comme on l'attend."""
    return math.floor(valeur + 0.5)


def cote_vise(largeur: int, hauteur: int, cible: Cible) -> str:
    """Le côté qui reçoit la taille visée (HAUTEUR ou LARGEUR) pour une image de cette taille."""
    if cible.cote == PLUS_GRAND_COTE:
        return HAUTEUR if hauteur >= largeur else LARGEUR
    return cible.cote


def taille_visee(largeur: int, hauteur: int, cible: Cible) -> tuple[int, int]:
    """Taille finale d'une image de `largeur` × `hauteur` : le côté visé à la taille demandée, l'autre
    en proportion, arrondi au pixel le plus proche (jamais moins d'un pixel)."""
    if cote_vise(largeur, hauteur, cible) == HAUTEUR:
        return max(1, _arrondi(largeur * cible.pixels / hauteur)), cible.pixels
    return cible.pixels, max(1, _arrondi(hauteur * cible.pixels / largeur))


# --- Lecture du dossier --------------------------------------------------------------------------


@dataclass(frozen=True)
class InfosImage:
    """Une image du dossier : sa taille telle qu'on la voit (orientation appliquée) et son format."""

    chemin: Path
    largeur: int
    hauteur: int
    format: str  # « JPEG », « PNG »…


@dataclass(frozen=True)
class Illisible:
    """Un fichier qui n'a pas pu être lu ou écrit, et pourquoi."""

    chemin: Path
    raison: str


def lire_une_image(chemin: Path) -> InfosImage:
    """Taille et format, sans décoder l'image (Pillow ne lit que son en-tête)."""
    with Image.open(chemin) as image:
        largeur, hauteur = image.size
        if image.getexif().get(ORIENTATION, 1) in _ORIENTATIONS_COUCHEES:
            largeur, hauteur = hauteur, largeur
        return InfosImage(chemin, largeur, hauteur, image.format or FORMATS.get(chemin.suffix.lower(), ""))


def lire_les_images(dossier: Path) -> tuple[list[InfosImage], list[Illisible]]:
    """Les images du dossier (pas celles de ses sous-dossiers), dans l'ordre de l'Explorateur, et les
    fichiers d'image illisibles (abîmés, ou d'un format que Pillow ne connaît pas)."""
    lues, illisibles = [], []
    for chemin in images_du_dossier(dossier):
        try:
            lues.append(lire_une_image(chemin))
        except Exception as erreur:  # noqa: BLE001 : un fichier abîmé ne doit pas arrêter la lecture du dossier
            illisibles.append(Illisible(chemin, _raison(erreur)))
    return lues, illisibles


def _raison(erreur: Exception) -> str:
    if isinstance(erreur, Image.UnidentifiedImageError):
        return "format illisible"
    if isinstance(erreur, PermissionError):
        return "accès refusé"
    if isinstance(erreur, Image.DecompressionBombError):
        return "image trop grande"
    return str(erreur) or type(erreur).__name__


# --- Plan ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ImageAPreparer:
    """Une image du plan : sa taille finale, l'agrandissement (ou la réduction) et sa destination."""

    infos: InfosImage
    finale: tuple[int, int]
    facteur: float  # 0,5 : deux fois plus petite ; 2 : deux fois plus grande
    destination: Path
    existe_deja: bool  # une image de ce nom est déjà dans le dossier de sortie (elle sera remplacée)

    @property
    def changement(self) -> str:
        if self.finale == (self.infos.largeur, self.infos.hauteur):
            return INCHANGEE
        return REDUITE if self.facteur < 1 else AGRANDIE

    @property
    def fortement_agrandie(self) -> bool:
        return self.changement == AGRANDIE and self.facteur > AGRANDISSEMENT_FORT


@dataclass
class Plan:
    """Ce qui va être fait : chaque image et sa taille finale, dans le dossier de sortie."""

    cible: Cible
    dossier_sortie: Path
    images: list[ImageAPreparer] = field(default_factory=list)
    illisibles: list[Illisible] = field(default_factory=list)

    def compter(self, changement: str) -> int:
        return sum(1 for image in self.images if image.changement == changement)

    @property
    def fortement_agrandies(self) -> list[ImageAPreparer]:
        return [image for image in self.images if image.fortement_agrandie]

    @property
    def existantes(self) -> list[ImageAPreparer]:
        return [image for image in self.images if image.existe_deja]

    def resume(self) -> str:
        """« 50 images à 600 px de haut : 46 réduites, 4 agrandies. »"""
        if not self.images:
            return "Aucune image à redimensionner."
        parties = [
            quantite(nombre, mot)
            for nombre, mot in (
                (self.compter(REDUITE), "réduite"),
                (self.compter(AGRANDIE), "agrandie"),
            )
            if nombre
        ]
        inchangees = self.compter(INCHANGEE)
        if inchangees:
            parties.append(f"{inchangees} déjà à la bonne taille")
        return f"{quantite(len(self.images), 'image')} {self.cible.description()} : {', '.join(parties)}."


def quantite(nombre: int, mot: str) -> str:
    """« 1 image », « 2 images » (pluriel en « s »)."""
    return f"{nombre} {mot}{'s' if nombre > 1 else ''}"


def meme_dossier(a: Path, b: Path) -> bool:
    """Vrai si les deux chemins désignent le même dossier (majuscules, liens et « .. » compris)."""
    try:
        if a.exists() and b.exists():
            return os.path.samefile(a, b)
    except OSError:
        pass
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def planifier(images: list[InfosImage], cible: Cible, dossier_sortie: Path, illisibles: list[Illisible] | None = None) -> Plan:
    """Le plan : la taille finale de chaque image, et sa destination dans `dossier_sortie` (même nom
    que l'original). Le dossier de sortie ne peut pas être celui des originaux : ils seraient remplacés."""
    plan = Plan(cible, dossier_sortie, illisibles=list(illisibles or []))
    sources = {image.chemin.parent for image in images}
    if any(meme_dossier(source, dossier_sortie) for source in sources):
        raise ValueError("Le dossier de sortie ne peut pas être celui des originaux.")
    for infos in images:
        finale = taille_visee(infos.largeur, infos.hauteur, cible)
        cote = cote_vise(infos.largeur, infos.hauteur, cible)
        facteur = finale[1] / infos.hauteur if cote == HAUTEUR else finale[0] / infos.largeur
        destination = dossier_sortie / infos.chemin.name
        plan.images.append(ImageAPreparer(infos, finale, facteur, destination, destination.exists()))
    return plan


# --- Fabrication -----------------------------------------------------------------------------------


def webp_sans_perte(chemin: Path) -> bool:
    """Vrai si ce WebP est enregistré sans perte. Pillow ne le dit pas : on lit les « morceaux » du
    fichier (format RIFF) jusqu'à celui de l'image, « VP8L » (sans perte) ou « VP8 » (avec perte)."""
    try:
        with open(chemin, "rb") as fichier:
            entete = fichier.read(12)
            if entete[:4] != b"RIFF" or entete[8:12] != b"WEBP":
                return False
            while True:
                morceau = fichier.read(8)
                if len(morceau) < 8:
                    return False
                nom, taille = morceau[:4], int.from_bytes(morceau[4:], "little")
                if nom == b"VP8L":
                    return True
                if nom == b"VP8 ":
                    return False
                fichier.seek(taille + (taille & 1), os.SEEK_CUR)  # un morceau de taille impaire a un octet de bourrage
    except OSError:
        return False


def _redimensionner(original: Image.Image, taille: tuple[int, int], filtre: str) -> tuple[Image.Image, bytes | None]:
    """L'image tournée selon son orientation EXIF, puis mise à `taille` ; et ses informations EXIF,
    sans l'orientation (déjà appliquée), à recopier dans la nouvelle image."""
    image = ImageOps.exif_transpose(original)
    exif = image.getexif()
    octets_exif = exif.tobytes() if len(exif) else None
    if image.mode in ("P", "PA"):
        transparente = image.mode == "PA" or "transparency" in image.info
        image = image.convert("RGBA" if transparente else "RGB")
    elif image.mode == "1":
        image = image.convert("L")
    return image.resize(taille, _FILTRES_PILLOW[filtre]), octets_exif


def _options_d_enregistrement(original: Image.Image, image: Image.Image, format_: str, qualite: int, exif: bytes | None) -> dict:
    """Réglages de Pillow pour enregistrer la nouvelle image comme l'original (voir en haut du fichier)."""
    options: dict = {}
    profil = original.info.get("icc_profile")
    if profil and format_ != "BMP":
        options["icc_profile"] = profil
    if exif and format_ in _FORMATS_AVEC_EXIF:
        options["exif"] = exif
    if format_ == "JPEG":
        tables = getattr(original, "quantization", None)
        if qualite == COMME_L_ORIGINAL and tables:
            options["qtables"] = tables
            sous_echantillonnage = JpegImagePlugin.get_sampling(original)
            if sous_echantillonnage >= 0:
                options["subsampling"] = sous_echantillonnage
        else:
            options["quality"] = qualite or max(QUALITES)
        if original.info.get("progressive") or original.info.get("progression"):
            options["progressive"] = True
    elif format_ == "WEBP":
        if original.filename and webp_sans_perte(Path(original.filename)):
            options["lossless"] = True
        else:
            options["quality"] = qualite or QUALITE_WEBP_AVIF
    elif format_ == "AVIF":
        options["quality"] = qualite or QUALITE_WEBP_AVIF
    elif format_ == "TIFF":
        compression = original.info.get("compression")
        if compression in _COMPRESSIONS_TIFF:
            options["compression"] = compression
    return options


def chemin_provisoire(destination: Path) -> Path:
    """« photo.jpg » → « photo.en-cours.jpg » : le nom pendant l'écriture."""
    return destination.with_name(f"{destination.stem}{EXTENSION_PROVISOIRE}{destination.suffix}")


def preparer_une_image(image: ImageAPreparer, filtre: str = LANCZOS, qualite: int = COMME_L_ORIGINAL) -> None:
    """Écrit la nouvelle image dans le dossier de sortie (sous un nom provisoire, renommé à la fin)."""
    provisoire = chemin_provisoire(image.destination)
    try:
        if image.changement == INCHANGEE:
            shutil.copy2(image.infos.chemin, provisoire)  # déjà à la bonne taille : copie exacte
        else:
            with Image.open(image.infos.chemin) as original:
                format_ = original.format or image.infos.format
                nouvelle, exif = _redimensionner(original, image.finale, filtre)
                if format_ == "JPEG" and nouvelle.mode not in ("RGB", "L", "CMYK"):
                    nouvelle = nouvelle.convert("RGB")
                options = _options_d_enregistrement(original, nouvelle, format_, qualite, exif)
                nouvelle.save(provisoire, format=format_, **options)
        os.replace(provisoire, image.destination)
    except BaseException:
        provisoire.unlink(missing_ok=True)
        raise


@dataclass
class Bilan:
    """Ce qui a été fait : images enregistrées, erreurs, arrêt demandé, durée."""

    dossier_sortie: Path
    total: int
    faites: int = 0
    erreurs: list[Illisible] = field(default_factory=list)
    arrete: bool = False
    duree_s: float = 0.0

    def message(self) -> str:
        """« 50 images enregistrées en 6 s dans « 600 px de haut ». »"""
        dossier = self.dossier_sortie.name
        if self.arrete:
            enregistrees = f"enregistrée{'s' if self.faites > 1 else ''}"
            return f"Arrêté : {quantite(self.faites, 'image')} sur {self.total} {enregistrees} dans « {dossier} »."
        texte = f"{quantite(self.faites, 'image')} enregistrée{'s' if self.faites > 1 else ''} en {duree_lisible(self.duree_s)} dans « {dossier} »"
        if self.erreurs:
            noms = ", ".join(erreur.chemin.name for erreur in self.erreurs[:3])
            suite = "…" if len(self.erreurs) > 3 else ""
            texte += f" ; {quantite(len(self.erreurs), 'erreur')} ({noms}{suite})"
        return texte + "."


def duree_lisible(secondes: float) -> str:
    """« 6 s », « 1 min 12 s » (au moins 1 s : « en 0 s » ne se dit pas)."""
    total = max(1, round(secondes))
    if total < 60:
        return f"{total} s"
    return f"{total // 60} min {total % 60:02d} s"


def preparer_les_images(
    plan: Plan,
    filtre: str = LANCZOS,
    qualite: int = COMME_L_ORIGINAL,
    progres: Callable[[tuple[int, int]], None] | None = None,
    arret: threading.Event | None = None,
    travailleurs: int | None = None,
) -> Bilan:
    """Fabrique toutes les images du plan, plusieurs à la fois. `progres((faites, total))` donne des
    nouvelles après chaque image ; `arret` : quand il est levé, les images pas encore commencées ne
    le sont plus (celles en cours se terminent : une image prend moins d'une seconde)."""
    debut = time.monotonic()
    arret = arret or threading.Event()
    bilan = Bilan(plan.dossier_sortie, len(plan.images))
    plan.dossier_sortie.mkdir(parents=True, exist_ok=True)
    travailleurs = travailleurs or max(1, min(TRAVAILLEURS_MAX, os.cpu_count() or 1))

    def une(image: ImageAPreparer) -> bool:
        if arret.is_set():
            return False  # pas commencée
        preparer_une_image(image, filtre, qualite)
        return True

    with ThreadPoolExecutor(max_workers=travailleurs) as executeur:
        futurs = {executeur.submit(une, image): image for image in plan.images}
        for futur in as_completed(futurs):
            try:
                if futur.result():
                    bilan.faites += 1
            except Exception as erreur:  # noqa: BLE001 : une image en échec n'arrête pas les autres
                bilan.erreurs.append(Illisible(futurs[futur].infos.chemin, _raison(erreur)))
            if progres is not None:
                progres((bilan.faites + len(bilan.erreurs), bilan.total))
    bilan.arrete = arret.is_set() and bilan.faites + len(bilan.erreurs) < bilan.total
    bilan.duree_s = time.monotonic() - debut
    return bilan
