"""FFmpeg (V3, §2) : le programme qui écrit les fichiers vidéo des exports.

- Où le trouver : dans le .exe, FFmpeg est rangé avec les ressources de l'app (ressources/ffmpeg),
  placé là par la fabrication automatique (outils/preparer_ffmpeg.py : version 9.0.2 « essentials »
  de gyan.dev, empreinte SHA-256 vérifiée). Pour les tests, la variable UGC_STUDIO_FFMPEG peut
  désigner un autre FFmpeg ; en développement hors Windows, celui de l'ordinateur sert.
- Comment l'app s'en sert : comme un programme à part, lancé sans fenêtre noire. Il reçoit les
  images des sous-titres par un « tuyau » (son entrée standard) et dit où il en est par un autre
  (option -progress). L'app peut l'arrêter à tout moment.
- Les commandes (listes d'arguments) sont fabriquées ici, par des fonctions sans interface : les
  tests vérifient chaque option, et chaque option suit la documentation officielle de FFmpeg 9.0.2
  (fournie dans l'archive de gyan.dev).
"""

from __future__ import annotations

import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from collections import deque
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from ..chemins import dossier_ressources
from .cadence import texte_ffmpeg

journal = logging.getLogger(__name__)

VARIABLE_FFMPEG = "UGC_STUDIO_FFMPEG"  # tests : un autre FFmpeg que celui de l'app
DOSSIER_FFMPEG = "ffmpeg"  # dans les ressources de l'app
VERSION_INTEGREE = "9.0.2"  # celle que la fabrication automatique place dans le .exe
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
    """Emplacement de FFmpeg dans l'app (le .exe, ou le code source après outils/preparer_ffmpeg.py)."""
    return dossier_ressources() / DOSSIER_FFMPEG / nom_du_programme()


def programme_ffmpeg() -> Path | None:
    """FFmpeg à utiliser, ou None s'il est introuvable (ne devrait pas arriver dans le .exe)."""
    force = os.environ.get(VARIABLE_FFMPEG)
    if force:
        return Path(force) if Path(force).is_file() else None
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

    @property
    def nombre(self) -> int:
        return len(self.temps)

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
class Analyse:
    """Ce que FFmpeg lit d'une source : son image (None : un audio) et son son (None : muette)."""

    images: ImagesDeLaVideo | None
    son: SonDeLaVideo | None


def commande_analyse(ffmpeg: Path, source: Path) -> list[str]:
    """Liste des paquets de la source, sans les décoder : « -c copy » recopie chaque paquet tel quel,
    et le format « framecrc » écrit une ligne par paquet (moment, durée, poids). « 0:V:0? » : la
    première image (pas une pochette d'album), si elle existe ; « 0:a:0? » : le premier son."""
    return [
        str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error",
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
        int(hauteur) if hauteur.isdigit() else 0,
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
    return analyse


# --- Commandes des exports --------------------------------------------------------------------


# Couleurs des vidéos HD (§8.2) : les sous-titres, dessinés en RGB, sont convertis avec la norme
# BT.709, en « plage limitée » (16 à 235 sur 255, celle des vidéos), et le fichier le dit (étiquettes
# de couleurs) : Premiere Pro et les lecteurs les reconvertissent donc avec la même norme. Sans ces
# précisions, FFmpeg prendrait une autre norme et les couleurs changeraient un peu.
CONVERSION_BT709 = "scale=out_color_matrix=bt709:out_range=tv"
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
    - « -vendor apl0 » : le fichier se présente comme un ProRes d'Apple (certains logiciels le
      demandent), comme le recommande le guide ProRes de l'Academy Software Foundation.
    - « -frames:v » : exactement le nombre d'images prévu ; « -an » : pas de son.
    - « -progress pipe:1 » : FFmpeg dit où il en est (images écrites), 4 fois par seconde."""
    return [
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
        "-progress", "pipe:1", "-stats_period", PERIODE_DES_NOUVELLES_S,
        "-f", "rawvideo", "-pixel_format", FORMAT_DES_IMAGES, "-video_size", f"{largeur}x{hauteur}",
        "-framerate", texte_ffmpeg(frequence), "-i", "pipe:0",
        "-vf", f"{CONVERSION_BT709},format=yuva444p10le",
        "-c:v", "prores_ks", "-profile:v", "4444", "-alpha_bits", "16", "-vendor", "apl0",
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
