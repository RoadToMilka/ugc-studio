"""FFmpeg (V3, §2) : le programme qui écrit les fichiers vidéo des exports.

- Où le trouver : la fabrication automatique prépare FFmpeg (outils/preparer_ffmpeg.py : version
  9.0.2 « essentials » de gyan.dev, empreinte SHA-256 vérifiée). Dans le .exe, il voyage compressé
  dans une « ressource » Windows : des données rangées dans le fichier du programme, que Windows ne
  lit que si on les demande. Au premier export (une fois par version de l'app), il est recopié dans
  %LOCALAPPDATA%\\UGC Studio\\ffmpeg\\<version>\\, puis repris de là.
  Pourquoi pas avec les autres ressources ? Le .exe recopie ses ressources dans un dossier
  temporaire à chaque démarrage : avec FFmpeg (100 Mo), l'app démarrait 2,4 s plus lentement.
  Hors du .exe (tests, développement), FFmpeg est dans ressources/ffmpeg ; la variable
  UGC_STUDIO_FFMPEG peut en désigner un autre ; hors Windows, celui de l'ordinateur sert.
- Comment l'app s'en sert : comme un programme à part, lancé sans fenêtre noire. Il reçoit les
  images des sous-titres par un « tuyau » (son entrée standard) et dit où il en est par un autre
  (option -progress). L'app peut l'arrêter à tout moment.
- Les commandes (listes d'arguments) sont fabriquées ici, par des fonctions sans interface : les
  tests vérifient chaque option, et chaque option suit la documentation officielle de FFmpeg 9.0.2
  (fournie dans l'archive de gyan.dev).
"""

from __future__ import annotations

import functools
import hashlib
import logging
import lzma
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from collections import deque
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path

from ..chemins import dossier_programmes, dossier_ressources
from .cadence import texte_ffmpeg

journal = logging.getLogger(__name__)

VARIABLE_FFMPEG = "UGC_STUDIO_FFMPEG"  # tests : un autre FFmpeg que celui de l'app
DOSSIER_FFMPEG = "ffmpeg"  # dans les ressources de l'app, et dans %LOCALAPPDATA%\UGC Studio
VERSION_INTEGREE = "9.0.2"  # celle que la fabrication automatique place dans le .exe
# ffmpeg.exe de cette version (archive de gyan.dev) : taille et empreinte SHA-256, vérifiées par la
# fabrication et à chaque recopie depuis le .exe. Changer de version de FFmpeg : ces trois valeurs,
# et l'empreinte de l'archive dans outils/preparer_ffmpeg.py.
TAILLE_DU_PROGRAMME = 105_423_872
EMPREINTE_DU_PROGRAMME = "3256173f3f8bffd7df12227c68adf68025edb1832273a9530688a7bb1ed8edec"
# La ressource Windows du .exe qui contient FFmpeg, compressé au format xz.
TYPE_DE_RESSOURCE = 10  # RT_RCDATA : des données brutes
NOM_DE_RESSOURCE = "FFMPEG"
MORCEAU_RECOPIE = 1024 * 1024  # FFmpeg est décompressé et écrit par morceaux (peu de mémoire)
LIGNES_D_ERREUR_GARDEES = 40
IMAGES_EN_ATTENTE_MAX = 4  # images prêtes mais pas encore lues par FFmpeg (mémoire : ≈ 66 Mo en 1080 × 1920)
PERIODE_DES_NOUVELLES_S = "0.25"  # FFmpeg dit où il en est 4 fois par seconde

# Calque transparent (§8.2) : images RGBA de 16 bits par couleur, transparence « droite » (non
# prémultipliée), en octets de poids faible d'abord (l'ordre des processeurs Intel et AMD).
FORMAT_DES_IMAGES = "rgba64le"
OCTETS_PAR_PIXEL = 8


def nom_du_programme() -> str:
    return "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


def programme_integre() -> Path:
    """Emplacement de FFmpeg à côté du code (tests et développement, après outils/preparer_ffmpeg.py)."""
    return dossier_ressources() / DOSSIER_FFMPEG / nom_du_programme()


def copie_de_ffmpeg() -> Path:
    """Où FFmpeg est recopié depuis le .exe : un dossier par version, à côté des données de l'app."""
    return dossier_programmes() / DOSSIER_FFMPEG / VERSION_INTEGREE / nom_du_programme()


@functools.cache
def _ressource() -> tuple[int, int] | None:
    """Adresse et taille de FFmpeg compressé dans la ressource du .exe (None : pas dans un .exe, ou
    ressource absente). FindResource, LoadResource et LockResource (fonctions de Windows) donnent
    l'adresse des données dans le programme déjà ouvert : rien n'est lu du disque avant qu'on y
    touche, et rien ne change pendant que l'app tourne (d'où la mémoire de la réponse)."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return None
    import ctypes
    from ctypes import wintypes

    noyau = ctypes.WinDLL("kernel32", use_last_error=True)
    noyau.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    noyau.GetModuleHandleW.restype = wintypes.HMODULE
    noyau.FindResourceW.argtypes = [wintypes.HMODULE, wintypes.LPCWSTR, wintypes.LPCWSTR]
    noyau.FindResourceW.restype = wintypes.HANDLE
    noyau.SizeofResource.argtypes = [wintypes.HMODULE, wintypes.HANDLE]
    noyau.SizeofResource.restype = wintypes.DWORD
    noyau.LoadResource.argtypes = [wintypes.HMODULE, wintypes.HANDLE]
    noyau.LoadResource.restype = wintypes.HGLOBAL
    noyau.LockResource.argtypes = [wintypes.HGLOBAL]
    noyau.LockResource.restype = ctypes.c_void_p
    module = noyau.GetModuleHandleW(None)  # le .exe lui-même
    # Un type de ressource numéroté se donne comme une « adresse » égale à son numéro (MAKEINTRESOURCE).
    trouvee = noyau.FindResourceW(module, NOM_DE_RESSOURCE, wintypes.LPCWSTR(TYPE_DE_RESSOURCE))
    if not trouvee:
        return None
    taille = noyau.SizeofResource(module, trouvee)
    chargee = noyau.LoadResource(module, trouvee)
    adresse = noyau.LockResource(chargee) if chargee else None
    if not taille or not adresse:
        return None
    return adresse, taille


def _lire_la_ressource() -> bytes | None:
    """FFmpeg compressé (format xz), copié depuis la ressource du .exe."""
    trouvee = _ressource()
    if trouvee is None:
        return None
    import ctypes

    adresse, taille = trouvee
    return ctypes.string_at(adresse, taille)


def ffmpeg_dans_le_exe() -> bool:
    """Vrai dans le .exe fabriqué avec FFmpeg dans sa ressource."""
    return _ressource() is not None


def _copie_prete(chemin: Path) -> bool:
    try:
        return chemin.is_file() and chemin.stat().st_size == TAILLE_DU_PROGRAMME
    except OSError:
        return False


def ffmpeg_a_preparer() -> bool:
    """Vrai au premier export d'une version de l'app : FFmpeg est à recopier depuis le .exe."""
    return not os.environ.get(VARIABLE_FFMPEG) and ffmpeg_dans_le_exe() and not _copie_prete(copie_de_ffmpeg())


class ErreurFFmpeg(Exception):
    """FFmpeg n'a pas pu être préparé (message clair, montré dans la fenêtre d'export)."""


def ecrire_le_programme(compresse: bytes, destination: Path, taille: int, empreinte: str) -> None:
    """Décompresse FFmpeg (format xz) dans `destination`, en vérifiant sa taille et son empreinte.

    Il s'écrit d'abord sous un nom provisoire, propre à ce lancement de l'app (deux fenêtres de l'app
    ne se gênent pas), et ne prend son vrai nom qu'une fois vérifié : un FFmpeg incomplet ou abîmé
    n'est jamais lancé."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    provisoire = destination.with_name(f"{destination.name}.{os.getpid()}.en-cours")
    calcul, ecrits = hashlib.sha256(), 0
    decompresseur = lzma.LZMADecompressor()
    try:
        with provisoire.open("wb") as fichier:
            vue = memoryview(compresse)
            for debut in range(0, len(vue), MORCEAU_RECOPIE):
                if decompresseur.eof:
                    break  # le programme est entier : ce qui suivrait ne sert pas (vérifié plus bas)
                morceau = decompresseur.decompress(vue[debut : debut + MORCEAU_RECOPIE])
                calcul.update(morceau)
                fichier.write(morceau)
                ecrits += len(morceau)
        if not decompresseur.eof or ecrits != taille or calcul.hexdigest() != empreinte:
            raise ErreurFFmpeg("la copie de FFmpeg contenue dans l'app est abîmée (empreinte inattendue)")
        os.replace(provisoire, destination)
    except lzma.LZMAError as erreur:
        raise ErreurFFmpeg(f"la copie de FFmpeg contenue dans l'app est illisible ({erreur})") from erreur
    except OSError:
        if _copie_prete(destination):
            return  # une autre fenêtre de l'app vient de le recopier (et s'en sert peut-être déjà)
        raise
    finally:
        provisoire.unlink(missing_ok=True)


def _ranger_les_anciennes_versions() -> None:
    """Les copies de FFmpeg des versions précédentes de l'app (100 Mo chacune) sont effacées."""
    dossier = dossier_programmes() / DOSSIER_FFMPEG
    for ancienne in dossier.iterdir() if dossier.is_dir() else ():
        if ancienne.is_dir() and ancienne.name != VERSION_INTEGREE:
            shutil.rmtree(ancienne, ignore_errors=True)  # encore utilisée par une autre fenêtre : effacée la prochaine fois


_preparation = threading.Lock()


def preparer_ffmpeg() -> Path:
    """FFmpeg prêt à servir : recopié depuis le .exe s'il ne l'est pas encore (une seconde ou deux,
    une fois par version de l'app). Hors du .exe : celui que trouve programme_ffmpeg().
    Lance ErreurFFmpeg (ou OSError : disque plein…) s'il n'a pas pu être préparé."""
    with _preparation:
        if not ffmpeg_a_preparer():
            chemin = programme_ffmpeg()
            if chemin is None:
                raise ErreurFFmpeg("FFmpeg est introuvable (il devrait être intégré à l'app)")
            return chemin
        compresse = _lire_la_ressource()
        if compresse is None:
            raise ErreurFFmpeg("FFmpeg est introuvable dans l'app")
        destination = copie_de_ffmpeg()
        journal.info("Recopie de FFmpeg %s depuis l'app : %s", VERSION_INTEGREE, destination)
        ecrire_le_programme(compresse, destination, TAILLE_DU_PROGRAMME, EMPREINTE_DU_PROGRAMME)
        _ranger_les_anciennes_versions()
        return destination


def programme_ffmpeg() -> Path | None:
    """FFmpeg à utiliser, ou None s'il est introuvable, ou pas encore recopié depuis le .exe (voir
    ffmpeg_a_preparer et preparer_ffmpeg)."""
    force = os.environ.get(VARIABLE_FFMPEG)
    if force:
        return Path(force) if Path(force).is_file() else None
    if ffmpeg_dans_le_exe():
        copie = copie_de_ffmpeg()
        return copie if _copie_prete(copie) else None
    integre = programme_integre()
    if integre.is_file():
        return integre
    if not getattr(sys, "frozen", False):
        trouve = shutil.which("ffmpeg")  # développement : FFmpeg de l'ordinateur
        if trouve:
            return Path(trouve)
    return None


def _options_de_lancement() -> dict:
    """Sous Windows, FFmpeg est un programme « console » : sans précaution, une fenêtre noire
    s'ouvrirait pendant l'export. CREATE_NO_WINDOW l'en empêche."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def executer(arguments: list[str], delai_s: float | None = 120, binaire: bool = False) -> subprocess.CompletedProcess:
    """Lance FFmpeg et attend la fin (petites commandes : version, analyse d'une vidéo, lecture d'une image)."""
    return subprocess.run(
        arguments,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=delai_s,
        text=not binaire,
        **({"encoding": "utf-8", "errors": "replace"} if not binaire else {}),
        **_options_de_lancement(),
    )


@dataclass(frozen=True)
class InfosFFmpeg:
    """Ce que sait faire le FFmpeg trouvé (pour l'autotest et le journal)."""

    chemin: Path
    version: str  # ex. « 9.0.2-essentials_build-www.gyan.dev »
    encodeurs: frozenset[str]
    formats_x265: tuple[str, ...]  # formats d'image acceptés par x265 (10 bits : « yuv420p10le »)

    @property
    def x265_10_bits(self) -> bool:
        return "yuv420p10le" in self.formats_x265


def lire_version(texte: str) -> str:
    """« ffmpeg version 9.0.2-essentials_build-www.gyan.dev Copyright… » → « 9.0.2-essentials_build-www.gyan.dev »."""
    trouve = re.search(r"ffmpeg version (\S+)", texte)
    return trouve.group(1) if trouve else ""


def lire_encodeurs(texte: str) -> frozenset[str]:
    """Liste de « ffmpeg -encoders » → noms des encodeurs (« prores_ks », « libx264 »…)."""
    noms = set()
    apres_la_legende = False  # la liste commence après la ligne « ------ » (avant : la légende des drapeaux)
    for ligne in texte.splitlines():
        morceaux = ligne.split()
        if morceaux and set(morceaux[0]) == {"-"}:
            apres_la_legende = True
            continue
        # Lignes d'encodeurs : « V....D libx264   libx264 H.264… » (6 drapeaux, puis le nom).
        if apres_la_legende and len(morceaux) >= 2 and re.fullmatch(r"[VAS][F.][S.][X.][B.][D.]", morceaux[0]):
            noms.add(morceaux[1])
    return frozenset(noms)


def lire_formats_d_encodeur(texte: str) -> tuple[str, ...]:
    """« ffmpeg -h encoder=libx265 » → les formats d'image acceptés (« Supported pixel formats: … »)."""
    trouve = re.search(r"Supported pixel formats:([^\n]*)", texte)
    return tuple(trouve.group(1).split()) if trouve else ()


def infos_ffmpeg(chemin: Path | None = None) -> InfosFFmpeg | None:
    """Version et encodeurs du FFmpeg de l'app (None : introuvable ou qui ne démarre pas)."""
    chemin = chemin or programme_ffmpeg()
    if chemin is None:
        return None
    try:
        version = executer([str(chemin), "-hide_banner", "-version"], 30)
        encodeurs = executer([str(chemin), "-hide_banner", "-encoders"], 30)
        x265 = executer([str(chemin), "-hide_banner", "-h", "encoder=libx265"], 30)
    except (OSError, subprocess.SubprocessError):
        journal.warning("FFmpeg ne démarre pas : %s", chemin, exc_info=True)
        return None
    return InfosFFmpeg(
        chemin,
        lire_version(version.stdout),
        lire_encodeurs(encodeurs.stdout),
        lire_formats_d_encodeur(x265.stdout),
    )


# --- Analyse d'une vidéo : moment exact de chaque image, débits, codecs ------------------------


@dataclass(frozen=True)
class ImagesDeLaVideo:
    """L'image d'une vidéo, lue par FFmpeg sans la décoder (rapide) : le moment de chaque image (en
    secondes, depuis la première), la fréquence et si elle est constante, le codec et le poids."""

    temps: tuple[Fraction, ...]
    frequence: Fraction  # exacte si constante ; sinon la moyenne, ramenée à une fréquence courante
    constante: bool
    duree: Fraction  # du début de la première image à la fin de la dernière
    codec: str = ""  # nom donné par FFmpeg : « h264 », « hevc », « prores »…
    octets: int = 0  # poids de l'image dans le fichier (tout le son mis à part)
    largeur: int = 0  # dimensions enregistrées (avant une éventuelle rotation)
    hauteur: int = 0
    # Les moments tels que la vidéo les écrit (V3, lot 2) : en unités de son « unité de temps »
    # (1/30 000 s, 1/600 s…), sans arrondi ; le premier n'est pas toujours 0.
    base_de_temps: Fraction = Fraction(0)
    moments: tuple[int, ...] = ()
    duree_derniere: int = 0  # durée de la dernière image, dans la même unité

    @property
    def nombre(self) -> int:
        return len(self.temps)

    @property
    def debut(self) -> Fraction:
        """Moment de la première image, en secondes (0 le plus souvent)."""
        return self.moments[0] * self.base_de_temps if self.moments else Fraction(0)

    @property
    def debit(self) -> int | None:
        """Débit moyen réel de l'image, en bits par seconde."""
        return round(self.octets * 8 / self.duree) if self.duree > 0 and self.octets else None


@dataclass(frozen=True)
class SonDeLaVideo:
    """Le son d'une vidéo (ou d'un audio), lu par FFmpeg sans le décoder."""

    codec: str  # « aac », « pcm_s16le », « mp3 »…
    octets: int
    duree: Fraction
    frequence: int = 0  # échantillons par seconde (48 000…)
    canaux: str = ""  # « stereo », « mono »…

    @property
    def debit(self) -> int | None:
        return round(self.octets * 8 / self.duree) if self.duree > 0 and self.octets else None


@dataclass(frozen=True)
class CouleursDeLaVideo:
    """Les couleurs d'une vidéo, telles que FFmpeg les décrit (« yuv420p10le(tv, bt2020nc/bt2020/
    arib-std-b67, progressive) ») : format des pixels, plage, matrice, primaires et courbe de
    transfert. Un champ vide : le fichier ne le précise pas."""

    format_pixels: str = ""  # « yuv420p » (8 bits), « yuv420p10le » (10 bits)…
    plage: str = ""  # « tv » : limitée (16 à 235 sur 255), celle des vidéos ; « pc » : complète
    matrice: str = ""  # « bt709 » (vidéos HD), « bt2020nc » (HDR)…
    primaires: str = ""
    transfert: str = ""  # « bt709 » ; « arib-std-b67 » : HLG ; « smpte2084 » : PQ
    bits_declares: int = 0  # « 8 bpc » : moins de bits que le format des pixels n'en a

    @property
    def bits(self) -> int:
        """Bits par couleur (0 : inconnu)."""
        if self.bits_declares:
            return self.bits_declares
        if not self.format_pixels or self.format_pixels == "none":
            return 0
        trouve = re.search(r"p0?(\d{2})(?:le|be)?$", self.format_pixels)
        return int(trouve.group(1)) if trouve else 8

    @property
    def hlg(self) -> bool:
        return self.transfert == "arib-std-b67"

    @property
    def pq(self) -> bool:
        return self.transfert == "smpte2084"

    @property
    def hdr(self) -> bool:
        return self.hlg or self.pq

    def texte(self) -> str:
        """« SDR, 8 bits », « HDR (HLG), 10 bits » (résumé avant export)."""
        gamme = "HDR (HLG)" if self.hlg else "HDR (PQ)" if self.pq else "SDR"
        return f"{gamme}, {self.bits} bits" if self.bits else gamme


ORDRES_DES_LIGNES = {"progressive", "top first", "bottom first", "top coded first (swapped)", "bottom coded first (swapped)"}


def lire_couleurs(texte: str) -> CouleursDeLaVideo | None:
    """Description de la source par FFmpeg (ses messages, rubrique « Input #0 ») → les couleurs de
    la première image (pas une pochette d'album). None : pas d'image."""
    dans_l_entree = False
    for ligne in texte.splitlines():
        if ligne.startswith("Input #"):
            dans_l_entree = True
            continue
        if ligne.startswith(("Output #", "Stream mapping")):
            dans_l_entree = False
        if not dans_l_entree or "(attached pic)" in ligne:
            continue
        trouve = re.match(r"\s*Stream #\d+:\d+.*?: Video: [^,]*?, (?P<format>[a-z0-9_]+)(?:\((?P<details>.*?)\))?(?:, |$)", ligne)
        if trouve is None:
            continue
        valeurs = {"format_pixels": trouve.group("format")}
        for morceau in (m.strip() for m in (trouve.group("details") or "").split(",")):
            if morceau in ("tv", "pc"):
                valeurs["plage"] = morceau
            elif re.fullmatch(r"\d+ bpc", morceau):
                valeurs["bits_declares"] = int(morceau.split()[0])
            elif morceau.count("/") == 2:
                valeurs["matrice"], valeurs["primaires"], valeurs["transfert"] = (
                    "" if v == "unknown" else v for v in morceau.split("/")
                )
            elif morceau and morceau not in ORDRES_DES_LIGNES and "matrice" not in valeurs and not morceau.startswith(("top ", "bottom ")):
                valeurs["matrice"] = valeurs["primaires"] = valeurs["transfert"] = morceau  # les trois pareilles : écrites une fois
        return CouleursDeLaVideo(**valeurs)
    return None


def lire_rotation(texte: str) -> int:
    """Rotation de la première image (vidéo de téléphone filmée debout, enregistrée « couchée ») :
    0, 90, 180 ou 270 degrés, d'après la description de FFmpeg (« rotation of -90.00 degrees »,
    dans les « Side data » de l'image). FFmpeg redresse lui-même les images en les lisant."""
    dans_l_entree = dans_l_image = False
    for ligne in texte.splitlines():
        if ligne.startswith("Input #"):
            dans_l_entree = True
            continue
        if ligne.startswith(("Output #", "Stream mapping")):
            break
        if not dans_l_entree:
            continue
        if re.match(r"\s*Stream #", ligne):
            if dans_l_image:
                break  # le flux suivant : la première image n'a pas de rotation
            dans_l_image = ": Video: " in ligne and "(attached pic)" not in ligne
            continue
        trouve = re.search(r"rotation of (-?\d+(?:\.\d+)?) degrees", ligne) if dans_l_image else None
        if trouve:
            return round(float(trouve.group(1)) / 90) * 90 % 360
    return 0


@dataclass(frozen=True)
class Analyse:
    """Ce que FFmpeg lit d'une source : son image (None : un audio), son son (None : muette), les
    couleurs de son image et sa rotation."""

    images: ImagesDeLaVideo | None
    son: SonDeLaVideo | None
    couleurs: CouleursDeLaVideo | None = None
    rotation: int = 0

    @property
    def taille_affichee(self) -> tuple[int, int]:
        """Largeur et hauteur des images telles qu'on les voit (redressées)."""
        if self.images is None:
            return (0, 0)
        if self.rotation in (90, 270):
            return (self.images.hauteur, self.images.largeur)
        return (self.images.largeur, self.images.hauteur)


def commande_analyse(ffmpeg: Path, source: Path) -> list[str]:
    """Liste des paquets de la source, sans les décoder : « -c copy » recopie chaque paquet tel quel,
    et le format « framecrc » écrit une ligne par paquet (moment, durée, poids). « 0:V:0? » : la
    première image (pas une pochette d'album), si elle existe ; « 0:a:0? » : le premier son.
    « -loglevel info » : FFmpeg décrit aussi la source dans ses messages (couleurs de l'image) ;
    « -nostats » : sans ses nouvelles d'avancement, inutiles ici."""
    return [
        str(ffmpeg), "-hide_banner", "-nostdin", "-nostats", "-loglevel", "info",
        "-i", str(source), "-map", "0:V:0?", "-map", "0:a:0?", "-c", "copy", "-f", "framecrc", "-",
    ]


_PAS_DE_TEMPS = -(2**63)  # « pas de moment » pour FFmpeg (AV_NOPTS_VALUE)


def _fraction(texte: str) -> Fraction | None:
    numerateur, _, denominateur = texte.strip().partition("/")
    try:
        return Fraction(int(numerateur), int(denominateur or 1))
    except (ValueError, ZeroDivisionError):
        return None


def _images(flux: dict) -> ImagesDeLaVideo | None:
    """Fréquence : avec des images toutes espacées pareil, elle est exacte (1 001 / 30 000 s d'écart :
    30 000 / 1 001). Un écart d'une unité de temps près (arrondis de certains logiciels) compte comme
    constant. Sinon (iPhone, enregistrement d'écran : fréquence variable), c'est l'écart le plus
    fréquent qui la donne, la fréquence « nominale » sur laquelle Premiere Pro se cale (30 pour un
    iPhone réglé sur 30), et pas la moyenne (29,98…)."""
    from collections import Counter

    from .cadence import frequence_exacte

    base, paquets = flux.get("tb"), sorted(flux["paquets"])
    if base is None or not paquets:
        return None
    moments = [moment for moment, _duree, _octets in paquets]
    depart = moments[0]
    ecarts = [b - a for a, b in zip(moments, moments[1:], strict=False)]
    courant = Counter(ecarts).most_common(1)[0][0] if ecarts else 0
    derniere = paquets[-1][1] if paquets[-1][1] > 0 else courant
    duree = (moments[-1] - depart + derniere) * base
    constante = all(abs(ecart - courant) <= 1 for ecart in ecarts)
    if ecarts and len(set(ecarts)) == 1:
        frequence = 1 / (courant * base)
    elif ecarts and constante:
        frequence = frequence_exacte((len(moments) - 1) / float((moments[-1] - depart) * base)) or Fraction(30)
    elif courant > 0:
        frequence = frequence_exacte(1 / float(courant * base)) or Fraction(30)
    elif duree > 0:
        frequence = 1 / duree  # une seule image
    else:
        frequence = Fraction(30)
    largeur, _, hauteur = flux.get("dimensions", "").partition("x")
    return ImagesDeLaVideo(
        tuple((m - depart) * base for m in moments), frequence, constante, duree, flux.get("codec", ""),
        sum(octets for _m, _d, octets in paquets), int(largeur) if largeur.isdigit() else 0,
        int(hauteur) if hauteur.isdigit() else 0, base, tuple(moments), derniere,
    )


def _son(flux: dict) -> SonDeLaVideo | None:
    base, paquets = flux.get("tb"), sorted(flux["paquets"])
    if base is None or not paquets:
        return None
    duree = (paquets[-1][0] + max(paquets[-1][1], 0) - paquets[0][0]) * base
    frequence = flux.get("sample_rate", "")
    return SonDeLaVideo(
        flux.get("codec", ""), sum(octets for _m, _d, octets in paquets), duree,
        int(frequence) if frequence.isdigit() else 0, flux.get("canaux", ""),
    )


def lire_analyse(texte: str) -> Analyse:
    """Sortie « framecrc » → l'image et le son de la source (moments exacts, codecs, poids)."""
    flux: dict[int, dict] = {}
    for ligne in texte.splitlines():
        if ligne.startswith("#"):
            cle, _, valeur = ligne[1:].partition(":")
            nom, _, numero = cle.strip().rpartition(" ")
            if not numero.isdigit():
                continue
            infos = flux.setdefault(int(numero), {"paquets": []})
            valeur = valeur.strip()
            if nom == "tb":
                infos["tb"] = _fraction(valeur)
            elif nom == "media_type":
                infos["sorte"] = valeur
            elif nom == "codec_id":
                infos["codec"] = valeur
            elif nom in ("dimensions", "sample_rate"):
                infos[nom] = valeur
            elif nom == "channel_layout_name":
                infos["canaux"] = valeur
            continue
        champs = [c.strip() for c in ligne.split(",")]
        if len(champs) < 5 or not champs[0].isdigit():
            continue
        try:
            numero, moment, duree, octets = int(champs[0]), int(champs[2]), int(champs[3]), int(champs[4])
        except ValueError:
            continue
        if moment != _PAS_DE_TEMPS:
            flux.setdefault(numero, {"paquets": []})["paquets"].append((moment, duree, octets))
    video = next((f for f in flux.values() if f.get("sorte") == "video"), None)
    son = next((f for f in flux.values() if f.get("sorte") == "audio"), None)
    return Analyse(_images(video) if video else None, _son(son) if son else None)


def analyser(source: Path, ffmpeg: Path | None = None) -> Analyse | None:
    """Image et son de la source, lus par FFmpeg (None : FFmpeg absent, ou fichier illisible)."""
    ffmpeg = ffmpeg or programme_ffmpeg()
    if ffmpeg is None:
        return None
    try:
        resultat = executer(commande_analyse(ffmpeg, source), 120)
    except (OSError, subprocess.SubprocessError):
        journal.warning("Source illisible par FFmpeg : %s", source, exc_info=True)
        return None
    analyse = lire_analyse(resultat.stdout)
    if analyse.images is None and analyse.son is None:
        journal.warning("FFmpeg ne trouve ni image ni son dans %s : %s", source, resultat.stderr[-500:])
        return None
    if analyse.images is None:
        return analyse
    return replace(analyse, couleurs=lire_couleurs(resultat.stderr), rotation=lire_rotation(resultat.stderr))


# --- Commandes des exports --------------------------------------------------------------------


# Couleurs des vidéos HD (§8.2) : les sous-titres, dessinés en RGB, sont convertis avec la norme
# BT.709, en « plage limitée » (16 à 235 sur 255, celle des vidéos), et le fichier le dit (étiquettes
# de couleurs) : Premiere Pro et les lecteurs les reconvertissent donc avec la même norme. Sans ces
# précisions, FFmpeg prendrait une autre norme et les couleurs changeraient un peu.
# Depuis FFmpeg 8, l'encodeur reprend les étiquettes portées par les images : les options
# « -color_primaries » et « -color_trc » seules ne suffisent plus (vérifié dans le code de FFmpeg
# 9.0.2, fftools/ffmpeg_enc.c, et par les tests). Le filtre setparams les pose donc sur les images.
CONVERSION_BT709 = "scale=out_color_matrix=bt709:out_range=tv"
ETIQUETAGE_BT709 = "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"
ETIQUETTES_BT709 = ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv"]


def commande_calque(
    ffmpeg: Path, largeur: int, hauteur: int, frequence: Fraction, nombre_images: int, sortie: Path
) -> list[str]:
    """Calque transparent (§8.2) : les images arrivent par l'entrée standard (« pipe:0 »), brutes,
    en RGBA de 16 bits (rgba64le). FFmpeg les écrit en ProRes 4444 avec transparence, dans un MOV.

    - « -f rawvideo » : des images brutes, sans en-tête ; il faut donc donner leur format, leur
      taille et leur fréquence (exacte : « 30000/1001 »).
    - ProRes 4444 (encodeur prores_ks, profil « 4444 ») : le format de montage d'Apple qui garde la
      transparence ; « yuva444p10le » : couleurs en 10 bits sans réduction de leur finesse (4:4:4),
      plus la transparence (le « a ») ; « -alpha_bits 16 » : transparence gardée sur 16 bits.
    - « setparams » : les étiquettes BT.709 posées sur les images (voir ETIQUETAGE_BT709).
    - « -vendor apl0 » : le fichier se présente comme un ProRes d'Apple (certains logiciels le
      demandent), comme le recommande le guide ProRes de l'Academy Software Foundation.
    - « -qscale:v 1 » : la compression la plus fine, partout. Sans lui, prores_ks cherche pour chaque
      bande d'image la compression qui tient dans le débit visé ; pour des sous-titres (aplats,
      bords nets, fond transparent), il choisit de toute façon la plus fine : mêmes images à l'octet
      près dans nos essais, mais 3 fois plus lent. La documentation de FFmpeg 9.0.2 conseille de fixer
      ce réglage pour aller vite (« Speed considerations »).
    - « -frames:v » : exactement le nombre d'images prévu ; « -an » : pas de son.
    - « -progress pipe:1 » : FFmpeg dit où il en est (images écrites), 4 fois par seconde."""
    return [
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
        "-progress", "pipe:1", "-stats_period", PERIODE_DES_NOUVELLES_S,
        "-f", "rawvideo", "-pixel_format", FORMAT_DES_IMAGES, "-video_size", f"{largeur}x{hauteur}",
        "-framerate", texte_ffmpeg(frequence), "-i", "pipe:0",
        "-vf", f"{CONVERSION_BT709},format=yuva444p10le,{ETIQUETAGE_BT709}",
        "-c:v", "prores_ks", "-profile:v", "4444", "-alpha_bits", "16", "-vendor", "apl0", "-qscale:v", "1",
        *ETIQUETTES_BT709,
        "-frames:v", str(nombre_images), "-an",
        "-f", "mov", str(sortie),
    ]


def commande_lire_une_image(ffmpeg: Path, video: Path, numero: int) -> list[str]:
    """Une image d'une vidéo exportée, décodée en RGBA 16 bits (vérifications de l'autotest) : la
    conversion inverse utilise la même norme BT.709 que l'export."""
    return [
        str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(video),
        "-vf", f"select=eq(n\\,{numero}),scale=in_color_matrix=bt709:in_range=tv,format={FORMAT_DES_IMAGES}",
        "-frames:v", "1", "-f", "rawvideo", "-",
    ]


# --- Suivi de FFmpeg pendant un export ---------------------------------------------------------


@dataclass
class Nouvelles:
    """Où en est FFmpeg (option -progress) : images écrites, moment atteint dans la vidéo."""

    images: int = 0
    temps_s: float = 0.0
    fini: bool = False


def lire_nouvelles(lignes: list[str], nouvelles: Nouvelles) -> None:
    """Lignes « clé=valeur » de -progress (« frame=412 », « out_time_us=13746066 », « progress=end »)."""
    for ligne in lignes:
        cle, _, valeur = ligne.strip().partition("=")
        if cle == "frame" and valeur.isdigit():
            nouvelles.images = int(valeur)
        elif cle == "out_time_us" and valeur.lstrip("-").isdigit():
            nouvelles.temps_s = max(0.0, int(valeur) / 1_000_000)
        elif cle == "progress":
            nouvelles.fini = valeur == "end"


class Processus:
    """FFmpeg en train de travailler : les images à lui donner partent par un fil à part (l'écriture
    attend quand FFmpeg est occupé, sans figer la fenêtre) ; ses nouvelles et ses messages d'erreur
    sont lus par deux autres fils.

    Pourquoi des fils ? Un tuyau a une petite réserve : si l'app attendait FFmpeg directement, la
    fenêtre ne répondrait plus pendant l'export ; et si personne ne lisait ses messages, FFmpeg
    finirait par s'arrêter, bloqué sur un tuyau plein."""

    def __init__(self, arguments: list[str], avec_images: bool):
        journal.info("FFmpeg : %s", " ".join(arguments))
        self._processus = subprocess.Popen(
            arguments,
            stdin=subprocess.PIPE if avec_images else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **_options_de_lancement(),
        )
        self.nouvelles = Nouvelles()
        self._erreurs: deque[str] = deque(maxlen=LIGNES_D_ERREUR_GARDEES)
        self._en_attente: queue.Queue[bytes | None] = queue.Queue(maxsize=IMAGES_EN_ATTENTE_MAX)
        self.tuyau_coupe = False  # FFmpeg a cessé de lire ses images (erreur, ou arrêt)
        self._fils = [
            threading.Thread(target=self._lire_nouvelles, daemon=True),
            threading.Thread(target=self._lire_erreurs, daemon=True),
        ]
        if avec_images:
            self._fils.append(threading.Thread(target=self._ecrire_images, daemon=True))
        for fil in self._fils:
            fil.start()

    # --- Images ---

    def peut_recevoir(self) -> bool:
        return not self._en_attente.full() and not self.tuyau_coupe

    def envoyer(self, image: bytes) -> bool:
        """Confie une image à FFmpeg ; False si la réserve est pleine (réessayer un peu plus tard)."""
        try:
            self._en_attente.put_nowait(image)
        except queue.Full:
            return False
        return True

    def fin_des_images(self) -> bool:
        """Toutes les images sont envoyées : FFmpeg peut terminer le fichier. False si la réserve
        est pleine (réessayer un peu plus tard)."""
        try:
            self._en_attente.put_nowait(None)
        except queue.Full:
            return False
        return True

    def _ecrire_images(self) -> None:
        entree = self._processus.stdin
        try:
            while True:
                image = self._en_attente.get()
                if image is None:
                    break
                entree.write(image)
        except (BrokenPipeError, OSError, ValueError):
            self.tuyau_coupe = True
        finally:
            try:
                entree.close()
            except (BrokenPipeError, OSError, ValueError):
                pass
        # Les images restantes (après une erreur) sont jetées : rien ne doit rester bloqué.
        while True:
            try:
                self._en_attente.get_nowait()
            except queue.Empty:
                break

    # --- Nouvelles et erreurs ---

    def _lire_nouvelles(self) -> None:
        for ligne in iter(self._processus.stdout.readline, b""):
            lire_nouvelles([ligne.decode("utf-8", "replace")], self.nouvelles)

    def _lire_erreurs(self) -> None:
        for ligne in iter(self._processus.stderr.readline, b""):
            texte = ligne.decode("utf-8", "replace").rstrip()
            if texte:
                self._erreurs.append(texte)

    def erreur(self) -> str:
        """Dernier message d'erreur de FFmpeg (vide s'il n'en a pas écrit)."""
        return self._erreurs[-1] if self._erreurs else ""

    def erreurs(self) -> list[str]:
        return list(self._erreurs)

    # --- Fin ---

    def termine(self) -> bool:
        return self._processus.poll() is not None

    @property
    def code(self) -> int | None:
        return self._processus.poll()

    def attendre(self, delai_s: float | None = None) -> int | None:
        try:
            return self._processus.wait(delai_s)
        except subprocess.TimeoutExpired:
            return None

    def arreter(self) -> None:
        """Arrête FFmpeg tout de suite (« Arrêter ») ; le fichier inachevé est effacé par l'appelant."""
        if self._processus.poll() is None:
            self._processus.kill()
        self.tuyau_coupe = True
        try:
            self._en_attente.put_nowait(None)  # libère le fil d'écriture s'il attend une image
        except queue.Full:
            pass
        self.attendre(10)
