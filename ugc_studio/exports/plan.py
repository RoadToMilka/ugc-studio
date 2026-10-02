"""Ce qui sera exporté (V3, §8) : la source, les réglages de l'export, son nom, son dossier, et le
résumé avant export (source et export côte à côte).

Rien ici ne dépend de l'interface : la fenêtre d'export (ui/dialogues/export.py) affiche ce que ces
fonctions calculent, et les tests les vérifient seules.

- Source : la vidéo (ou l'audio) importée dans le module Transcription, ou la prise de voix des
  sous-titres. Ses informations viennent de Qt (lues à l'import : taille, rotation, codecs, débits,
  HDR) et de FFmpeg (analyse.py : moment exact de chaque image, vrais débits, nom exact des codecs).
- Dossier (décision du 02/10/2026) : celui de la vidéo source, celui du projet, ou un autre.
- Nom proposé : celui de la vidéo (ou du projet), suivi de « (calque) » : « Sérum Glowzy (calque).mov ».
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path

from ..projets import Projet, nom_de_dossier
from ..transcription import resolution_video
from .cadence import (
    FREQUENCE_SANS_VIDEO,
    duree_lisible,
    frequence_exacte,
    nombre_d_images,
    temps_de_l_image,
    texte_frequence,
)
from .ffmpeg import Analyse, CouleursDeLaVideo

SORTE_CALQUE = "calque"

DOSSIER_SOURCE = "source"  # celui de la vidéo (ou de l'audio) importée
DOSSIER_PROJET = "projet"
DOSSIER_AUTRE = "autre"

EXTENSION_CALQUE = ".mov"
SUFFIXE_CALQUE = "calque"
SUFFIXE_EN_COURS = ".en-cours"  # fichier en cours d'écriture, renommé à la fin (rien d'inachevé sous le vrai nom)

# Débit visé par Apple pour le ProRes 4444 en 1920 × 1080 à 29,97 images par seconde (Apple ProRes
# White Paper, avril 2022) : 330 Mb/s. Le calque, presque entièrement transparent, en demande
# beaucoup moins ; ce débit sert de limite haute (place libre du disque).
DEBIT_PRORES_4444 = 330_000_000
PIXELS_1080P = 1920 * 1080
FREQUENCE_DU_DEBIT_APPLE = Fraction(30000, 1001)

# Noms des formats et des codecs, tels que les connaît l'utilisateur.
NOMS_FORMATS = {
    "MPEG4": "MP4", "QuickTime": "MOV", "Matroska": "MKV", "WebM": "WebM", "AVI": "AVI",
    "Wave": "WAV", "MP3": "MP3", "AAC": "AAC", "FLAC": "FLAC", "Ogg": "OGG", "Mpeg4Audio": "M4A",
    "WMA": "WMA", "WMV": "WMV",
}
NOMS_CODECS = {
    # Qt (QMediaFormat) et FFmpeg (codec_id) : les deux noms d'un même codec.
    "H264": "H.264", "h264": "H.264", "H265": "H.265", "hevc": "H.265", "prores": "ProRes",
    "dnxhd": "DNxHR", "MotionJPEG": "Motion JPEG", "mjpeg": "Motion JPEG", "VP8": "VP8", "vp8": "VP8",
    "VP9": "VP9", "vp9": "VP9", "AV1": "AV1", "av1": "AV1", "MPEG4": "MPEG-4", "mpeg4": "MPEG-4",
    "AAC": "AAC", "aac": "AAC", "MP3": "MP3", "mp3": "MP3", "Opus": "Opus", "opus": "Opus",
    "FLAC": "FLAC", "flac": "FLAC", "AC3": "AC-3", "ac3": "AC-3", "EAC3": "E-AC-3", "eac3": "E-AC-3",
    "ALAC": "ALAC", "alac": "ALAC", "Vorbis": "Vorbis", "vorbis": "Vorbis", "Wave": "PCM",
}


def nom_du_codec(code: str) -> str:
    if code.startswith("pcm_"):
        return "PCM (non compressé)"
    return NOMS_CODECS.get(code, code.upper() if code and code != "Unspecified" else "")


# --- Source ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Source:
    """Ce que l'on sait de la source des sous-titres."""

    chemin: Path | None  # fichier importé (vidéo ou audio) ; None : prise de voix (dans le projet)
    video: bool  # la source a une image
    largeur: int | None = None  # telle qu'on la voit (vidéo de téléphone « couchée » remise debout)
    hauteur: int | None = None
    frequence: Fraction | None = None
    frequence_constante: bool = True
    nombre_images: int | None = None  # exact quand FFmpeg a lu la vidéo
    duree_s: float = 0.0
    format: str = ""  # « MP4 », « MOV »…
    codec_video: str = ""  # « H.264 »…
    debit_video: int | None = None  # bits par seconde
    codec_audio: str = ""
    debit_audio: int | None = None
    poids: int | None = None  # octets
    hdr: bool | None = None
    couleurs: CouleursDeLaVideo | None = None  # lues par FFmpeg (format des pixels, norme, HDR)
    prise: bool = False  # sous-titres d'une prise de voix
    video_d_apercu: Path | None = None  # projet sans vidéo : celle choisie pour l'aperçu

    @property
    def dossier(self) -> Path | None:
        """Dossier de la vidéo (ou de l'audio) importée ; sinon celui de la vidéo d'aperçu."""
        if self.chemin is not None:
            return self.chemin.parent
        return self.video_d_apercu.parent if self.video_d_apercu is not None else None


def _entier(valeur) -> int | None:
    try:
        nombre = int(float(valeur))
    except (TypeError, ValueError):
        return None
    return nombre if nombre > 0 else None


def source_du_projet(projet: Projet, analyse: Analyse | None = None) -> Source:
    """La source des sous-titres du projet : la vidéo ou l'audio importés (infos lues par Qt à
    l'import, complétées par l'analyse de FFmpeg), ou la prise de voix."""
    transcription = projet.transcription
    apercu = projet.sous_titres.apercu
    video_d_apercu = Path(apercu.chemin) if apercu.chemin else None
    if transcription is None or transcription.prise or not transcription.source:
        duree = transcription.duree_s if transcription is not None else 0.0
        return Source(None, False, duree_s=duree or 0.0, format="WAV", codec_audio="PCM (non compressé)",
                      prise=transcription is not None and bool(transcription.prise), video_d_apercu=video_d_apercu)
    infos = transcription.infos or {}
    chemin = Path(transcription.source)
    resolution = resolution_video(infos)
    video = bool(infos.get("video")) or resolution is not None
    format_ = NOMS_FORMATS.get(str(infos.get("format", "")), "") or chemin.suffix.lstrip(".").upper()
    source = Source(
        chemin=chemin,
        video=video,
        largeur=resolution[0] if resolution else None,
        hauteur=resolution[1] if resolution else None,
        frequence=frequence_exacte(infos.get("images_par_seconde")) if video else None,
        duree_s=float(infos.get("duree_s") or transcription.duree_s or 0.0),
        format=format_,
        codec_video=nom_du_codec(str(infos.get("codec_video", ""))) if video else "",
        debit_video=_entier(infos.get("debit_video")) if video else None,
        codec_audio=nom_du_codec(str(infos.get("codec_audio", ""))),
        debit_audio=_entier(infos.get("debit_audio")),
        poids=chemin.stat().st_size if chemin.is_file() else None,
        hdr=bool(infos["hdr"]) if "hdr" in infos else None,
    )
    if analyse is None:
        return source
    # FFmpeg a lu la vidéo : ses chiffres sont exacts (Qt ne connaît pas tous les codecs, ni le
    # moment exact de chaque image).
    images, son = analyse.images, analyse.son
    if images is not None and video:
        source = replace(
            source,
            frequence=images.frequence,
            frequence_constante=images.constante,
            nombre_images=images.nombre,
            codec_video=nom_du_codec(images.codec) or source.codec_video,
            debit_video=images.debit or source.debit_video,
            duree_s=float(images.duree) or source.duree_s,
        )
    if son is not None:
        source = replace(source, codec_audio=nom_du_codec(son.codec) or source.codec_audio, debit_audio=son.debit or source.debit_audio)
    elif analyse.images is not None:
        source = replace(source, codec_audio="")  # vidéo sans son
    if analyse.couleurs is not None and video:
        source = replace(source, couleurs=analyse.couleurs, hdr=analyse.couleurs.hdr)
    return source


# --- Textes ------------------------------------------------------------------------------------


def poids_lisible(octets: float | None) -> str:
    """Poids d'un fichier, comme l'Explorateur de Windows le compte (1 Mo = 1 024 Ko) :
    « 850 Ko », « 52 Mo », « 1,2 Go »."""
    if octets is None:
        return "inconnu"
    ko, mo, go = 1024, 1024**2, 1024**3
    if octets < mo:
        return f"{max(1, round(octets / ko))} Ko"
    if octets < go:
        valeur = octets / mo
        return f"{valeur:.1f} Mo".replace(".", ",") if valeur < 10 else f"{round(valeur)} Mo"
    return f"{octets / go:.1f} Go".replace(".", ",")


def debit_lisible(bits_par_seconde: float | None) -> str:
    """12 400 000 → « 12,4 Mb/s » ; 256 000 → « 256 kb/s »."""
    if not bits_par_seconde:
        return "inconnu"
    if bits_par_seconde >= 1_000_000:
        return f"{bits_par_seconde / 1_000_000:.1f} Mb/s".replace(".", ",")
    return f"{round(bits_par_seconde / 1000)} kb/s"


def nom_propre(nom: str) -> str:
    """Nom de fichier valide sous Windows (caractères interdits retirés, espaces superflus aussi)."""
    return nom_de_dossier(nom)


def nom_propose(source: Source, projet: Projet, suffixe: str = SUFFIXE_CALQUE) -> str:
    """Nom de la vidéo (ou du projet), suivi de « (calque) » : « Sérum Glowzy (calque) »."""
    base = source.chemin.stem if source.chemin is not None else projet.nom
    return f"{nom_propre(base) or nom_propre(projet.nom) or 'Export'} ({suffixe})"


# --- Calque transparent (§8.2) -----------------------------------------------------------------


@dataclass(frozen=True)
class PlanCalque:
    """Le calque qui sera fabriqué : taille, fréquence et nombre d'images, fichier."""

    largeur: int
    hauteur: int
    frequence: Fraction
    nombre_images: int
    sortie: Path

    @property
    def duree_s(self) -> float:
        return float(self.nombre_images / self.frequence)

    def temps(self, numero: int) -> float:
        """Moment exact de l'image `numero` (calculé depuis son numéro : aucun décalage qui s'accumule)."""
        return float(temps_de_l_image(numero, self.frequence))

    @property
    def en_cours(self) -> Path:
        """Fichier pendant l'écriture ; il prend son vrai nom à la fin."""
        return self.sortie.with_name(self.sortie.name + SUFFIXE_EN_COURS)

    @property
    def poids_max(self) -> int:
        """Limite haute du poids du fichier (débit visé par Apple, ramené à la taille et à la fréquence)."""
        debit = DEBIT_PRORES_4444 * (self.largeur * self.hauteur / PIXELS_1080P) * float(self.frequence / FREQUENCE_DU_DEBIT_APPLE)
        return round(debit / 8 * self.duree_s)


def frequence_du_calque(source: Source, choisie: Fraction | None) -> Fraction:
    """Avec une vidéo, sa fréquence exacte (sinon le calque se décalerait peu à peu) ; sans vidéo,
    celle choisie (30 au départ, §8.4)."""
    if source.video and source.frequence is not None:
        return source.frequence
    return choisie or FREQUENCE_SANS_VIDEO


def nombre_d_images_du_calque(source: Source, frequence: Fraction) -> int:
    """Autant d'images que la vidéo (FFmpeg les a comptées) ; sinon de quoi couvrir sa durée."""
    if source.video and source.nombre_images and source.frequence == frequence:
        return source.nombre_images
    return nombre_d_images(source.duree_s, frequence)


def plan_du_calque(source: Source, largeur: int, hauteur: int, frequence: Fraction | None, sortie: Path) -> PlanCalque:
    frequence = frequence_du_calque(source, frequence)
    return PlanCalque(largeur, hauteur, frequence, nombre_d_images_du_calque(source, frequence), sortie)


# --- Résumé avant export (§8.5) ----------------------------------------------------------------


@dataclass(frozen=True)
class LigneResume:
    titre: str
    source: str
    export: str
    differente: bool  # en mauve dans la fenêtre


@dataclass
class Resume:
    lignes: list[LigneResume] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)  # en orange
    erreurs: list[str] = field(default_factory=list)  # en rouge : l'export ne peut pas partir

    @property
    def possible(self) -> bool:
        return not self.erreurs


def _ligne(titre: str, source: str, export: str, comparer: bool = True) -> LigneResume:
    return LigneResume(titre, source, export, comparer and bool(source) and source != export)


def _format_source(source: Source) -> str:
    morceaux = [m for m in (source.format, source.codec_video) if m]
    return ", ".join(morceaux)


def _son_source(source: Source) -> str:
    if not source.codec_audio:
        return "aucun"
    if source.debit_audio:
        return f"{source.codec_audio}, {debit_lisible(source.debit_audio)}"
    return source.codec_audio


def place_libre(dossier: Path) -> int | None:
    """Place libre sur le disque de ce dossier, en octets (None : inconnue)."""
    try:
        return shutil.disk_usage(dossier).free
    except OSError:
        return None


def verifier_la_sortie(sortie: Path, source: Source) -> tuple[list[str], list[str]]:
    """Avertissements et erreurs sur le fichier à écrire."""
    avertissements, erreurs = [], []
    nom = sortie.name.rsplit(".", 1)[0] if "." in sortie.name else sortie.name  # « .mov » seul : pas de nom
    if not nom.strip():
        erreurs.append("Donne un nom au fichier.")
    elif not sortie.parent.is_dir():
        erreurs.append(f"Le dossier « {sortie.parent} » n'existe pas (ou plus) : choisis-en un autre.")
    elif source.chemin is not None and sortie.resolve() == source.chemin.resolve():
        erreurs.append("C'est le nom de ta vidéo : choisis un autre nom, ta vidéo n'est jamais remplacée.")
    elif sortie.exists():
        avertissements.append(f"Un fichier « {sortie.name} » existe déjà dans ce dossier : il sera remplacé.")
    return avertissements, erreurs


def resume_calque(source: Source, plan: PlanCalque, sous_titres: str, libre: int | None = None) -> Resume:
    """Source et calque côte à côte ; une valeur différente de la source est en mauve."""
    resume = Resume()
    taille_source = f"{source.largeur} × {source.hauteur}" if source.video and source.largeur else ""
    images_source = ""
    if source.video and source.frequence is not None:
        images_source = texte_frequence(source.frequence) + ("" if source.frequence_constante else " (variable)")
    if source.video and source.couleurs is not None:
        couleurs_source = source.couleurs.texte()
    else:
        couleurs_source = ("HDR" if source.hdr else "SDR") if source.video and source.hdr is not None else ""
    resume.lignes = [
        _ligne("Taille", taille_source or ("son seul" if not source.video else "inconnue"), f"{plan.largeur} × {plan.hauteur}", bool(taille_source)),
        _ligne(
            "Images par seconde", images_source or ("aucune" if not source.video else "inconnue"),
            texte_frequence(plan.frequence), bool(images_source),
        ),
        _ligne("Format et codec", _format_source(source), "MOV, ProRes 4444 (transparent)"),
        _ligne("Son", _son_source(source), "aucun (le son reste dans ton montage)"),
        _ligne("Couleurs", couleurs_source, "SDR (BT.709), 10 bits + transparence"),
        _ligne("Durée", duree_lisible(source.duree_s) if source.duree_s else "", duree_lisible(plan.duree_s)),
        _ligne("Poids", poids_lisible(source.poids) if source.poids else "", f"≈ {poids_lisible(plan.poids_max)} au plus", False),
        _ligne("Sous-titres", "", sous_titres, False),
    ]
    if source.video and not source.frequence_constante:
        resume.avertissements.append(
            f"Ta vidéo a une fréquence d'images variable : le calque est à {texte_frequence(plan.frequence)} images "
            "par seconde (sa moyenne). Premiere Pro le pose sans décalage."
        )
    if source.video and source.hdr:
        resume.avertissements.append(
            "Ta vidéo est en HDR : le calque est en SDR (BT.709). Le HDR des exports arrive avec la version 3.0.0."
        )
    avertissements, erreurs = verifier_la_sortie(plan.sortie, source)
    resume.avertissements += avertissements
    resume.erreurs += erreurs
    if libre is not None and libre < plan.poids_max:
        resume.avertissements.append(
            f"Place libre : {poids_lisible(libre)} sur ce disque, et le calque peut demander jusqu'à "
            f"{poids_lisible(plan.poids_max)} (souvent bien moins : la transparence prend peu de place)."
        )
    return resume


def texte_des_sous_titres(nombre: int, prereglage: str) -> str:
    """« 14 sous-titres, préréglage « Karaoké » »."""
    texte = f"{nombre} sous-titre{'s' if nombre > 1 else ''}"
    return f"{texte}, préréglage « {prereglage} »" if prereglage else texte


def duree_d_export_lisible(secondes: float) -> str:
    """Durée d'un export, ou temps restant : « 12 s », « 1 min 12 s »."""
    total = max(0, round(secondes))
    if total < 60:
        return f"{total} s"
    return f"{total // 60} min {total % 60:02d} s"


@dataclass(frozen=True)
class SousTitresAExporter:
    """Les sous-titres du projet tels que l'aperçu les montre (réglages, taille de la vidéo, liste,
    mots), et le nom de leur style (« Karaoké », « Karaoké (modifié) », ou vide)."""

    reglages: object  # ReglagesSousTitres
    largeur: int
    hauteur: int
    sous_titres: list
    mots: list
    style: str = ""
