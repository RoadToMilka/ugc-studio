"""Vidéo avec sous-titres (V3, lot 2, §8.3) : ce qui sera exporté (conteneur, codec, débit, son,
couleurs), le résumé avant export, et les commandes données à FFmpeg. Rien ici ne dépend de
l'interface : les tests vérifient chaque choix et chaque option.

Le principe (document V3, §6) : le calque des sous-titres (lot 1) est posé sur la vidéo.
1. Le calque est d'abord écrit dans un fichier provisoire (mov_png.py) : une image PNG à chaque
   changement, au moment exact d'une image de la vidéo (fréquence variable comprise).
2. FFmpeg lit la vidéo et ce calque, pose l'un sur l'autre (filtre « overlay ») et encode le tout :
   en deux passages pour H.264 et H.265 (le premier analyse la vidéo, le second répartit le débit
   là où il sert), en un seul pour le ProRes (format de montage, sans débit à choisir).
3. Le son est copié tel quel quand le conteneur choisi l'accepte ; sinon, il est converti en AAC à
   320 kb/s (signalé en mauve dans le résumé).

Chaque image de la vidéo garde son moment exact : FFmpeg ne change ni n'ajoute aucune image
(« -fps_mode passthrough »), et écrit les moments dans l'unité de temps de la vidéo elle-même
(« -enc_time_base:v demux »). Les couleurs des sous-titres sont converties avec la norme de la vidéo
(BT.709 pour une vidéo HD), et le fichier porte ses étiquettes de couleurs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from .cadence import texte_frequence
from .ffmpeg import PERIODE_DES_NOUVELLES_S, Analyse, CouleursDeLaVideo, ImagesDeLaVideo
from .plan import (
    SUFFIXE_EN_COURS,
    LigneResume,
    Resume,
    Source,
    debit_lisible,
    duree_lisible,
    poids_lisible,
    verifier_la_sortie,
)

MP4, MOV, MKV = "mp4", "mov", "mkv"
H264, H265, PRORES = "h264", "h265", "prores"
CONTENEURS = {MP4: "MP4", MOV: "MOV", MKV: "MKV"}
CODECS = {H264: "H.264", H265: "H.265", PRORES: "ProRes 422 HQ"}
# Combinaisons possibles (§8.3) : le ProRes ne va que dans un MOV (Premiere Pro le lit ainsi).
CODECS_POSSIBLES = {MP4: (H264, H265), MOV: (H264, H265, PRORES), MKV: (H264, H265)}
EXTENSIONS = {MP4: ".mp4", MOV: ".mov", MKV: ".mkv"}
SUFFIXE_VIDEO = "sous-titres"

DEBIT_IDENTIQUE, DEBIT_CONSEILLE, DEBIT_PERSONNALISE = "identique", "conseille", "personnalise"
MARGE_RECOMPRESSION = Fraction(11, 10)  # « identique à la source » : + 10 % (une vidéo réencodée perd toujours un peu)
DEBIT_AAC = 320_000  # son converti quand il ne peut pas être copié
LIMITE_TIKTOK = 500_000_000  # octets (TikTok, In-Feed Ads : 500 Mo au plus)
DEBIT_PERSONNALISE_MIN, DEBIT_PERSONNALISE_MAX = 0.5, 400.0  # Mb/s

# Débits conseillés par YouTube pour la mise en ligne (paramètres d'encodage conseillés, consultés le
# 02/10/2026), en Mb/s, selon le petit côté de l'image : (jusqu'à 30 images par seconde, 48 à 60). Pour
# la 2160p, YouTube donne une fourchette : sa valeur haute. « Conseillé pour la publication » : le
# double (document V3), pour garder de la marge avant la recompression des plateformes.
DEBITS_YOUTUBE_SDR = {2160: (45, 68), 1440: (16, 24), 1080: (8, 12), 720: (5, 7.5), 480: (2.5, 4), 360: (1, 1.5)}
FACTEUR_CONSEILLE = 2
FREQUENCE_HAUTE = 31  # au-delà : la colonne « 48 à 60 images par seconde »

# ProRes 422 HQ : débit visé par Apple en 1920 × 1080 à 29,97 (Apple ProRes White Paper) : 220 Mb/s.
DEBIT_PRORES_422_HQ = 220_000_000
PIXELS_1080P = 1920 * 1080
FREQUENCE_DU_DEBIT_APPLE = Fraction(30000, 1001)

# Formats de montage : à leur débit, un H.264 serait énorme (document V3, §3, point 2) ; le débit
# conseillé est alors proposé.
CODECS_DE_MONTAGE = {"prores", "dnxhd", "cfhd", "rawvideo", "v210", "v410", "ffv1", "qtrle", "utvideo", "huffyuv", "magicyuv", "png"}

# Sons copiables tels quels selon le conteneur (noms de FFmpeg) ; les autres sont convertis en AAC.
SONS_COPIABLES = {
    MP4: {"aac", "mp3", "ac3", "eac3", "alac"},
    MOV: {"aac", "mp3", "ac3", "eac3", "alac", "pcm_s16le", "pcm_s16be", "pcm_s24le", "pcm_s24be", "pcm_s32le", "pcm_s32be", "pcm_f32le", "pcm_f32be"},
    MKV: {"aac", "mp3", "ac3", "eac3", "alac", "opus", "vorbis", "flac", "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le"},
}
SON_COPIE, SON_AAC = "copie", "aac"

# Normes de couleurs que la conversion des sous-titres sait suivre : nom donné par FFmpeg en lisant la
# vidéo → nom attendu par son filtre « scale » (out_color_matrix).
MATRICES_DU_FILTRE = {"bt709": "bt709", "smpte170m": "smpte170m", "bt470bg": "bt470", "fcc": "fcc", "smpte240m": "smpte240m", "bt2020nc": "bt2020", "bt2020c": "bt2020"}
# Étiquettes reprises de la vidéo (setparams accepte ces noms) ; sinon, celles d'une vidéo HD.
PRIMAIRES_CONNUES = {"bt709", "bt470m", "bt470bg", "smpte170m", "smpte240m", "film", "bt2020", "smpte428", "smpte431", "smpte432", "jedec-p22"}
COURBES_CONNUES = {"bt709", "bt470m", "bt470bg", "smpte170m", "smpte240m", "linear", "iec61966-2-4", "bt1361e", "iec61966-2-1", "bt2020-10", "bt2020-12"}


def debit_conseille(largeur: int, hauteur: int, frequence: Fraction | None) -> int:
    """« Conseillé pour la publication » : le double du débit conseillé par YouTube, en bits par
    seconde (1080 × 1920 à 30 images par seconde : 16 Mb/s)."""
    cote = min(largeur, hauteur) if largeur and hauteur else 1080
    rangee = next((r for r in sorted(DEBITS_YOUTUBE_SDR, reverse=True) if cote >= r * 0.9), 360)
    normal, haut = DEBITS_YOUTUBE_SDR[rangee]
    debit = haut if frequence is not None and frequence > FREQUENCE_HAUTE else normal
    return round(debit * FACTEUR_CONSEILLE * 1_000_000)


def debit_prores(largeur: int, hauteur: int, frequence: Fraction | None) -> int:
    """Débit du ProRes 422 HQ visé par Apple, ramené à la taille et à la fréquence (estimation du poids)."""
    rapport = float((frequence or FREQUENCE_DU_DEBIT_APPLE) / FREQUENCE_DU_DEBIT_APPLE)
    return round(DEBIT_PRORES_422_HQ * (largeur * hauteur / PIXELS_1080P) * rapport)


def debit_par_defaut(source: Source) -> str:
    """Identique à la source (+ 10 %), sauf pour une vidéo en format de montage ou de débit inconnu."""
    images = source.analyse.images if source.analyse is not None else None
    if images is None or not images.debit or images.codec in CODECS_DE_MONTAGE:
        return DEBIT_CONSEILLE
    return DEBIT_IDENTIQUE


def son_de_l_export(conteneur: str, codec_ffmpeg: str | None) -> str | None:
    """Le son : copié tel quel si le conteneur l'accepte, sinon converti en AAC ; None : pas de son."""
    if not codec_ffmpeg:
        return None
    return SON_COPIE if codec_ffmpeg in SONS_COPIABLES[conteneur] else SON_AAC


@dataclass(frozen=True)
class CouleursDeLExport:
    """Norme des couleurs de la vidéo exportée : celle de la source quand elle est connue, sinon celle
    d'une vidéo HD (BT.709) ; toujours en plage limitée (celle des vidéos)."""

    matrice: str  # nom de FFmpeg (étiquette)
    primaires: str
    transfert: str
    plage_source: str  # « pc » : la vidéo est convertie en plage limitée
    rgb_source: bool = False  # vidéo en RGB (images PNG, certains enregistrements d'écran) : convertie elle aussi

    @property
    def matrice_du_filtre(self) -> str:
        return MATRICES_DU_FILTRE.get(self.matrice, "bt709")


def couleurs_de_l_export(couleurs: CouleursDeLaVideo | None) -> CouleursDeLExport:
    couleurs = couleurs or CouleursDeLaVideo()
    matrice = couleurs.matrice if couleurs.matrice in MATRICES_DU_FILTRE else "bt709"
    primaires = couleurs.primaires if couleurs.primaires in PRIMAIRES_CONNUES else "bt709"
    transfert = couleurs.transfert if couleurs.transfert in COURBES_CONNUES else "bt709"
    format_ = couleurs.format_pixels
    rgb = "rgb" in format_ or "bgr" in format_ or format_.startswith(("gbr", "pal8"))
    return CouleursDeLExport(matrice, primaires, transfert, couleurs.plage, rgb)


@dataclass(frozen=True)
class PlanVideo:
    """La vidéo qui sera fabriquée."""

    source: Path
    largeur: int  # images redressées (vidéo de téléphone « couchée »)
    hauteur: int
    images: ImagesDeLaVideo
    conteneur: str
    codec: str
    debit: int | None  # bits par seconde ; None : ProRes (débit fixé par son profil)
    son: str | None  # SON_COPIE, SON_AAC ou None (vidéo muette)
    debit_son: int | None
    couleurs: CouleursDeLExport
    bits: int  # 8 ou 10
    sortie: Path

    @property
    def en_cours(self) -> Path:
        return self.sortie.with_name(self.sortie.name + SUFFIXE_EN_COURS)

    @property
    def passages(self) -> int:
        return 1 if self.codec == PRORES else 2

    @property
    def nombre_images(self) -> int:
        return self.images.nombre

    @property
    def duree_s(self) -> float:
        return float(self.images.duree)

    @property
    def debit_estime(self) -> int:
        return self.debit if self.debit is not None else debit_prores(self.largeur, self.hauteur, self.images.frequence)

    @property
    def poids_estime(self) -> int:
        """Débit × durée, son compris, et 1 % pour le conteneur."""
        return round((self.debit_estime + (self.debit_son or 0)) / 8 * self.duree_s * 1.01)

    @property
    def format_des_pixels(self) -> str:
        if self.codec == PRORES:
            return "yuv422p10le"
        return "yuv420p10le" if self.bits == 10 else "yuv420p"

    @property
    def format_du_calque(self) -> str:
        """Format du calque une fois converti (le même découpage des couleurs, plus la transparence)."""
        return {"yuv420p": "yuva420p", "yuv420p10le": "yuva420p10le", "yuv422p10le": "yuva422p10le"}[self.format_des_pixels]

    @property
    def calque_16_bits(self) -> bool:
        """Les images du calque en 16 bits par couleur pour une vidéo en 10 bits (sinon 8 suffisent)."""
        return self.bits == 10 or self.codec == PRORES


def plan_video(
    source: Source, conteneur: str, codec: str, mode_debit: str, debit_personnalise_mbps: float, sortie: Path
) -> PlanVideo | None:
    """None : la vidéo n'a pas été lue par FFmpeg (rien à exporter)."""
    analyse: Analyse | None = source.analyse
    if analyse is None or analyse.images is None or not analyse.images.nombre:
        return None
    if codec not in CODECS_POSSIBLES[conteneur]:
        codec = CODECS_POSSIBLES[conteneur][0]
    largeur, hauteur = analyse.taille_affichee
    images = analyse.images
    if codec == PRORES:
        debit = None
    elif mode_debit == DEBIT_IDENTIQUE and images.debit:
        debit = round(images.debit * MARGE_RECOMPRESSION)
    elif mode_debit == DEBIT_PERSONNALISE:
        debit = round(max(0.0, debit_personnalise_mbps) * 1_000_000)
    else:
        debit = debit_conseille(largeur, hauteur, images.frequence)
    son = son_de_l_export(conteneur, analyse.son.codec if analyse.son is not None else None)
    if son == SON_COPIE:
        debit_son = analyse.son.debit
    elif son == SON_AAC:
        debit_son = DEBIT_AAC
    else:
        debit_son = None
    bits_source = analyse.couleurs.bits if analyse.couleurs is not None else 8
    bits = 10 if codec == PRORES or (codec == H265 and bits_source >= 10) else 8
    return PlanVideo(
        source.chemin, largeur, hauteur, images, conteneur, codec, debit, son, debit_son,
        couleurs_de_l_export(analyse.couleurs), bits, sortie,
    )


# --- Commandes ---------------------------------------------------------------------------------


def graphe_de_filtres(plan: PlanVideo) -> str:
    """La vidéo (entrée 0) et le calque (entrée 1), posés l'un sur l'autre.

    - Vidéo : convertie en plage limitée si elle était en plage complète (ou avec la norme de l'export
      si elle est en RGB), puis dans le format de l'export (8 ou 10 bits, 4:2:0 ou 4:2:2). FFmpeg la
      redresse lui-même si elle est « couchée ».
    - Calque : ses couleurs (RGB) converties avec la norme de la vidéo, en plage limitée.
    - overlay : le calque par-dessus, chaque image du calque sur les images de la vidéo de son moment
      jusqu'au suivant ; après la dernière, il reste en place (eof_action=repeat).
    - setparams : les étiquettes de couleurs posées sur les images (FFmpeg 9 les reprend des images)."""
    couleurs = plan.couleurs
    principal = f"format={plan.format_des_pixels}"
    if couleurs.rgb_source:  # comme le calque : convertie avec la norme de l'export
        principal = f"scale=out_color_matrix={couleurs.matrice_du_filtre}:out_range=tv,{principal}"
    elif couleurs.plage_source == "pc":
        principal = f"scale=in_range=pc:out_range=tv,{principal}"
    calque = f"scale=out_color_matrix={couleurs.matrice_du_filtre}:out_range=tv,format={plan.format_du_calque}"
    etiquettes = f"setparams=color_primaries={couleurs.primaires}:color_trc={couleurs.transfert}:colorspace={couleurs.matrice}:range=tv"
    format_de_l_overlay = {"yuv420p": "yuv420", "yuv420p10le": "yuv420p10", "yuv422p10le": "yuv422p10"}[plan.format_des_pixels]
    return (
        f"[0:v]{principal}[video];[1:v]{calque}[calque];"
        f"[video][calque]overlay=format={format_de_l_overlay}:eof_action=repeat,{etiquettes}[sortie]"
    )


def options_video(plan: PlanVideo, passage: int, journal_des_passages: Path) -> list[str]:
    if plan.codec == PRORES:
        return ["-c:v", "prores_ks", "-profile:v", "hq", "-vendor", "apl0", "-pix_fmt", plan.format_des_pixels]
    deux_passages = ["-pass", str(passage), "-passlogfile", str(journal_des_passages)]
    if plan.codec == H264:
        return ["-c:v", "libx264", "-preset", "medium", "-profile:v", "high", "-pix_fmt", plan.format_des_pixels,
                "-b:v", str(plan.debit), *deux_passages]
    options = ["-c:v", "libx265", "-preset", "medium", "-pix_fmt", plan.format_des_pixels, "-b:v", str(plan.debit),
               "-x265-params", "log-level=error", *deux_passages]
    if plan.conteneur in (MP4, MOV):
        options += ["-tag:v", "hvc1"]  # marqué « hvc1 » : lu par les iPhone et les Mac
    return options


def options_son(plan: PlanVideo) -> list[str]:
    if plan.son == SON_COPIE:
        return ["-map", "0:a:0", "-c:a", "copy"]
    if plan.son == SON_AAC:
        return ["-map", "0:a:0", "-c:a", "aac", "-b:a", str(DEBIT_AAC)]
    return ["-an"]


def options_conteneur(plan: PlanVideo) -> list[str]:
    if plan.conteneur == MKV:
        return ["-f", "matroska"]
    # « fast start » : l'index au début du fichier, la vidéo démarre avant d'être entièrement téléchargée.
    return ["-movflags", "+faststart", "-f", "mp4" if plan.conteneur == MP4 else "mov"]


def decalage_du_calque(images: ImagesDeLaVideo) -> list[str]:
    """Le calque provisoire commence à 0 s, avec la première image de la vidéo. Quand celle-ci n'est pas
    à 0 s, le calque est décalé d'autant (« -itsoffset », au millionième de seconde, arrondi vers le
    bas : FFmpeg le ramène à l'unité de temps du calque, celle de la vidéo, où il tombe juste)."""
    debut = images.debut
    if debut == 0:
        return []
    microsecondes = math.floor(debut * 1_000_000)
    signe = "-" if microsecondes < 0 else ""
    return ["-itsoffset", f"{signe}{abs(microsecondes) // 1_000_000}.{abs(microsecondes) % 1_000_000:06d}"]


def commande_video(ffmpeg: Path, plan: PlanVideo, calque: Path, passage: int, journal_des_passages: Path) -> list[str]:
    """Le passage `passage` (1 ou 2 ; le ProRes n'en a qu'un) : le dernier écrit le fichier, son
    compris ; le premier de H.264 et H.265 n'écrit que son analyse (journal des passages)."""
    dernier = passage == plan.passages
    commande = [
        str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        "-progress", "pipe:1", "-stats_period", PERIODE_DES_NOUVELLES_S,
        "-i", str(plan.source), *decalage_du_calque(plan.images), "-i", str(calque),
        "-filter_complex", graphe_de_filtres(plan), "-map", "[sortie]",
        *(options_son(plan) if dernier else ["-an"]),
        "-fps_mode", "passthrough", "-enc_time_base:v", "demux",
        *options_video(plan, passage, journal_des_passages),
    ]
    if dernier:
        return [*commande, *options_conteneur(plan), str(plan.en_cours)]
    return [*commande, "-f", "null", "-"]


# --- Résumé avant export (§8.5) ----------------------------------------------------------------


def _couleurs_source(source: Source) -> str:
    couleurs = source.analyse.couleurs if source.analyse is not None else None
    if couleurs is None:
        return ""
    texte = couleurs.texte()
    return f"{texte} (plage complète)" if couleurs.plage == "pc" else texte


def resume_video(source: Source, plan: PlanVideo | None, sous_titres: str, libre: int | None = None) -> Resume:
    """Source et vidéo exportée côte à côte ; une valeur différente de la source est en mauve."""
    resume = Resume()
    analyse = source.analyse
    if source.chemin is not None and not source.chemin.is_file():
        resume.erreurs.append(
            f"Ta vidéo « {source.chemin.name} » est introuvable (déplacée ou effacée ?) : remets-la à sa place pour l'exporter."
        )
        return resume
    if plan is None or analyse is None or analyse.images is None:
        resume.erreurs.append("FFmpeg n'a pas pu lire ta vidéo : l'export de la vidéo avec sous-titres est impossible.")
        return resume
    images = analyse.images
    largeur, hauteur = analyse.taille_affichee
    frequence = texte_frequence(images.frequence) + ("" if images.constante else " (variable)")
    debit_source = debit_lisible(images.debit) if images.debit else "inconnu"
    debit_export = f"≈ {debit_lisible(plan.debit_estime)} (ProRes 422 HQ)" if plan.debit is None else debit_lisible(plan.debit)
    format_source = ", ".join(m for m in (source.format, source.codec_video) if m)
    format_export = f"{CONTENEURS[plan.conteneur]}, {CODECS[plan.codec]}"
    son_source = "aucun"
    if analyse.son is not None:
        son_source = source.codec_audio or analyse.son.codec
        if analyse.son.debit:
            son_source += f", {debit_lisible(analyse.son.debit)}"
    son_export = {SON_COPIE: "copié tel quel", SON_AAC: f"converti en AAC, {debit_lisible(DEBIT_AAC)}", None: "aucun"}[plan.son]
    gamme = "SDR (BT.709)" if plan.couleurs.matrice == "bt709" else "SDR"
    couleurs_export = f"{gamme}, {plan.bits} bits"
    couleurs_source = _couleurs_source(source)
    resume.lignes = [
        LigneResume("Taille", f"{largeur} × {hauteur}", f"{plan.largeur} × {plan.hauteur}", False),
        LigneResume("Images par seconde", frequence, frequence if images.constante else f"{frequence}, gardée", False),
        LigneResume("Débit vidéo", debit_source, debit_export, images.debit is not None and plan.debit != images.debit),
        LigneResume("Format et codec", format_source, format_export, format_source != format_export),
        LigneResume("Son", son_source, son_export, plan.son == SON_AAC),
        LigneResume(
            "Couleurs", couleurs_source, couleurs_export,
            bool(couleurs_source) and (couleurs_source != f"SDR, {plan.bits} bits"),
        ),
        LigneResume("Durée", duree_lisible(float(images.duree)), duree_lisible(plan.duree_s), False),
        LigneResume("Poids", poids_lisible(source.poids) if source.poids else "", f"≈ {poids_lisible(plan.poids_estime)}", False),
        LigneResume("Sous-titres", "", sous_titres, False),
    ]
    if analyse.couleurs is not None and analyse.couleurs.hdr:
        resume.erreurs.append(
            "Ta vidéo est en HDR : la vidéo avec sous-titres en HDR arrive avec la version 3.0.0. En attendant, "
            "exporte le calque transparent et pose-le sur ta vidéo dans Premiere Pro."
        )
    if plan.debit is not None and plan.debit <= 0:
        resume.erreurs.append("Donne un débit (en Mb/s).")
    if plan.conteneur == MKV:
        resume.avertissements.append("Premiere Pro ne lit pas le MKV : pour le montage, choisis MP4 ou MOV.")
    if plan.poids_estime > LIMITE_TIKTOK:
        resume.avertissements.append(
            f"Poids estimé : {poids_lisible(plan.poids_estime)}, plus que la limite de TikTok (500 Mo). Choisis un "
            "débit plus bas, comme « Conseillé pour la publication »."
        )
    if images.codec in CODECS_DE_MONTAGE and plan.debit is not None and images.debit and plan.debit > debit_conseille(largeur, hauteur, images.frequence) * 2:
        resume.avertissements.append(
            "Ta vidéo est dans un format de montage : à son débit, le fichier serait énorme. « Conseillé pour la "
            "publication » est plus adapté."
        )
    avertissements, erreurs = verifier_la_sortie(plan.sortie, source)
    resume.avertissements += avertissements
    resume.erreurs += erreurs
    if libre is not None and libre < plan.poids_estime * 1.2:
        resume.avertissements.append(
            f"Place libre : {poids_lisible(libre)} sur ce disque, pour une vidéo d'environ {poids_lisible(plan.poids_estime)}."
        )
    return resume
