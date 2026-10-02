"""Vidéo avec sous-titres (V3, lots 2 et 3, §8.3) : ce qui sera exporté (conteneur, codec, débit,
son, couleurs, HDR), le résumé avant export, et les commandes données à FFmpeg. Rien ici ne dépend
de l'interface : les tests vérifient chaque choix et chaque option.

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

HDR (lot 3 ; vidéos d'iPhone) : le HDR suit la vidéo source (décision du 02/10/2026). Une vidéo HDR
(courbe HLG ou PQ) reste en HDR : H.265 en 10 bits (ou ProRes), mêmes couleurs, et les sous-titres
posés au « blanc de référence » de la norme ITU-R BT.2408 (203 cd/m²) : posés tels quels, ils
monteraient au maximum de l'écran et éblouiraient. Dolby Vision (profil 8.4 des iPhone) est gardé en
MP4 et en MKV. « Convertir en SDR » ramène la vidéo en BT.709, ses reflets les plus forts adoucis ;
les sous-titres y sont posés comme dans une vidéo SDR.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from .cadence import texte_frequence
from .ffmpeg import (
    BLANC_DE_REFERENCE,
    COURBES_HDR,
    HLG,
    PERIODE_DES_NOUVELLES_S,
    Analyse,
    CouleursDeLaVideo,
    ImagesDeLaVideo,
    NormeHDR,
    conversion_des_sous_titres,
    conversion_vers_le_hdr,
    etiquetage,
    norme_hdr,
)
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

# --- HDR (lot 3, §8.3 ; courbes, normes et blanc de référence : voir ffmpeg.py) ---
# Débits conseillés par YouTube en HDR (même page, consultée le 02/10/2026) ; sous la 720p, YouTube
# n'en donne pas : ceux du SDR.
DEBITS_YOUTUBE_HDR = {2160: (56, 85), 1440: (20, 30), 1080: (10, 15), 720: (6.5, 9.5)}
# « Convertir en SDR » : la vidéo est ramenée en BT.709 avec le même blanc de référence (203 cd/m²
# deviennent le blanc du SDR), puis ses reflets plus lumineux (jusqu'à 1 000 cd/m², la crête d'un écran
# HLG et de la plupart des vidéos PQ) sont adoucis par une courbe « mobius » (filtre tonemap) : en
# dessous de la moitié du blanc de référence, rien ne change ; au-dessus, la courbe s'infléchit
# doucement. Le blanc de référence de la vidéo arrive ainsi vers 90 % du SDR, comme le conseille l'EBU
# (« Best practices in live HDR production », 2019 : 80 à 90 %, pour garder de la place aux reflets).
CRETE_HDR = 1000  # cd/m²
GENOU_DU_SDR = 0.5  # en part du blanc de référence
# Dolby Vision : x265 sait le reprendre (FFmpeg 9.0.2, option « -dolbyvision ») pour le profil 8.4 des
# iPhone (image HLG, lue en HDR partout, et informations Dolby Vision en plus). FFmpeg n'écrit sa
# description que dans un MP4 ou un MKV (pas dans un MOV) ; x265 demande alors une limite de débit
# (« VBV ») : jusqu'à 2 fois le débit visé, avec une réserve de 4 fois ce débit.
DOLBY_VISION_GARDE = "8.4"
CONTENEURS_DOLBY_VISION = (MP4, MKV)
DEBIT_MAX_DOLBY_VISION, RESERVE_DOLBY_VISION = 2, 4


def rangee_youtube(largeur: int, hauteur: int) -> int:
    """La rangée des tableaux de YouTube (2160, 1440, 1080, 720, 480, 360) d'après le petit côté."""
    cote = min(largeur, hauteur) if largeur and hauteur else 1080
    return next((r for r in sorted(DEBITS_YOUTUBE_SDR, reverse=True) if cote >= r * 0.9), 360)


def debit_hdr_de_youtube(largeur: int, hauteur: int) -> bool:
    """YouTube donne un débit HDR pour cette taille (de la 720p à la 2160p)."""
    return rangee_youtube(largeur, hauteur) in DEBITS_YOUTUBE_HDR


def debit_conseille(largeur: int, hauteur: int, frequence: Fraction | None, hdr: bool = False) -> int:
    """« Conseillé pour la publication » : le double du débit conseillé par YouTube, en bits par
    seconde (1080 × 1920 à 30 images par seconde : 16 Mb/s ; en HDR : 20 Mb/s)."""
    rangee = rangee_youtube(largeur, hauteur)
    table = DEBITS_YOUTUBE_HDR if hdr and rangee in DEBITS_YOUTUBE_HDR else DEBITS_YOUTUBE_SDR
    normal, haut = table[rangee]
    debit = haut if frequence is not None and frequence > FREQUENCE_HAUTE else normal
    return round(debit * FACTEUR_CONSEILLE * 1_000_000)


def codecs_possibles(conteneur: str, hdr: bool) -> tuple[str, ...]:
    """Codecs possibles dans ce conteneur : le ProRes ne va que dans un MOV ; une vidéo qui reste en
    HDR demande H.265 en 10 bits (ou ProRes) : H.264 n'est proposé qu'en SDR."""
    codecs = CODECS_POSSIBLES[conteneur]
    return tuple(codec for codec in codecs if codec != H264) if hdr else codecs


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
    """Norme des couleurs de la vidéo exportée, toujours en plage limitée (celle des vidéos).
    - SDR : celle de la source quand elle est connue, sinon celle d'une vidéo HD (BT.709).
    - HDR gardé : celle de la source (BT.2020, et la courbe HLG ou PQ), dans laquelle les sous-titres
      sont convertis au blanc de référence.
    - « Convertir en SDR » : BT.709 ; `hdr_converti` garde la norme de la source HDR, dont part la
      conversion."""

    matrice: str  # nom de FFmpeg (étiquette)
    primaires: str
    transfert: str
    plage_source: str  # « pc » : la vidéo est convertie en plage limitée
    rgb_source: bool = False  # vidéo en RGB (images PNG, certains enregistrements d'écran) : convertie elle aussi
    hdr_converti: NormeHDR | None = None

    @property
    def hdr(self) -> bool:
        """La vidéo exportée est en HDR (courbe HLG ou PQ)."""
        return self.transfert in COURBES_HDR

    @property
    def matrice_du_filtre(self) -> str:
        return MATRICES_DU_FILTRE.get(self.matrice, "bt709")


def couleurs_de_l_export(couleurs: CouleursDeLaVideo | None, convertir_en_sdr: bool = False) -> CouleursDeLExport:
    couleurs = couleurs or CouleursDeLaVideo()
    hdr = norme_hdr(couleurs)
    if hdr is not None and convertir_en_sdr:
        return CouleursDeLExport("bt709", "bt709", "bt709", couleurs.plage, hdr_converti=hdr)
    if hdr is not None:
        return CouleursDeLExport(hdr.matrice, hdr.primaires, hdr.courbe, couleurs.plage)
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
    dolby_vision: bool = False  # informations Dolby Vision de la source reprises (profil 8.4)

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
    source: Source, conteneur: str, codec: str, mode_debit: str, debit_personnalise_mbps: float, sortie: Path,
    convertir_en_sdr: bool = False,
) -> PlanVideo | None:
    """None : la vidéo n'a pas été lue par FFmpeg (rien à exporter). `convertir_en_sdr` : une vidéo HDR
    est ramenée en SDR (sinon, elle reste en HDR)."""
    analyse: Analyse | None = source.analyse
    if analyse is None or analyse.images is None or not analyse.images.nombre:
        return None
    couleurs = couleurs_de_l_export(analyse.couleurs, convertir_en_sdr)
    possibles = codecs_possibles(conteneur, couleurs.hdr)
    if codec not in possibles:
        codec = possibles[0]
    largeur, hauteur = analyse.taille_affichee
    images = analyse.images
    if codec == PRORES:
        debit = None
    elif mode_debit == DEBIT_IDENTIQUE and images.debit:
        debit = round(images.debit * MARGE_RECOMPRESSION)
    elif mode_debit == DEBIT_PERSONNALISE:
        debit = round(max(0.0, debit_personnalise_mbps) * 1_000_000)
    else:
        debit = debit_conseille(largeur, hauteur, images.frequence, couleurs.hdr)
    son = son_de_l_export(conteneur, analyse.son.codec if analyse.son is not None else None)
    if son == SON_COPIE:
        debit_son = analyse.son.debit
    elif son == SON_AAC:
        debit_son = DEBIT_AAC
    else:
        debit_son = None
    bits_source = analyse.couleurs.bits if analyse.couleurs is not None else 8
    # 10 bits : le ProRes, le HDR, et une vidéo en 10 bits gardée en H.265 ; « Convertir en SDR » : 8 bits.
    dix_bits = codec == H265 and bits_source >= 10 and couleurs.hdr_converti is None
    bits = 10 if codec == PRORES or couleurs.hdr or dix_bits else 8
    dolby_vision = (
        couleurs.transfert == HLG and analyse.dolby_vision == DOLBY_VISION_GARDE
        and codec == H265 and conteneur in CONTENEURS_DOLBY_VISION
    )
    return PlanVideo(
        source.chemin, largeur, hauteur, images, conteneur, codec, debit, son, debit_son,
        couleurs, bits, sortie, dolby_vision,
    )


# --- Commandes ---------------------------------------------------------------------------------


def conversion_en_sdr(norme: NormeHDR, plage_source: str) -> str:
    """« Convertir en SDR » (voir CRETE_HDR) : la vidéo HDR en lumière linéaire, le blanc de référence
    valant 1 (zscale, « npl=203 ») ; ses couleurs ramenées dans celles du BT.709 ; ses reflets adoucis
    (tonemap, courbe « mobius » : rien ne change sous le genou, la crête de 1 000 cd/m² devient le
    blanc) ; puis la courbe et la norme du SDR (BT.709), en plage limitée. La norme de la source est
    donnée en entier : une étiquette manquante ne bloque pas la conversion."""
    plage = "full" if plage_source == "pc" else "limited"
    return (
        f"zscale=min={norme.matrice}:pin={norme.primaires}:tin={norme.courbe}:rin={plage}:t=linear"
        f":npl={BLANC_DE_REFERENCE},format=gbrpf32le,zscale=pin={norme.primaires}:tin=linear:p=bt709,"
        f"tonemap=tonemap=mobius:param={GENOU_DU_SDR}:peak={CRETE_HDR / BLANC_DE_REFERENCE:.3f}:desat=0,"
        f"zscale=pin=bt709:tin=linear:t=bt709:m=bt709:r=limited"
    )


def graphe_de_filtres(plan: PlanVideo) -> str:
    """La vidéo (entrée 0) et le calque (entrée 1), posés l'un sur l'autre.

    - Vidéo : convertie en plage limitée si elle était en plage complète (ou avec la norme de l'export
      si elle est en RGB ; ou ramenée en SDR, « Convertir en SDR »), puis dans le format de l'export
      (8 ou 10 bits, 4:2:0 ou 4:2:2). FFmpeg la redresse lui-même si elle est « couchée ». En HDR
      gardé, ses images ne changent pas.
    - Calque : ses couleurs (RGB) converties avec la norme de la vidéo, en plage limitée, par zscale
      (conversion_des_sous_titres) ; en HDR, au blanc de référence (conversion_vers_le_hdr).
    - overlay : le calque par-dessus, chaque image du calque sur les images de la vidéo de son moment
      jusqu'au suivant ; après la dernière, il reste en place (eof_action=repeat).
    - setparams : les étiquettes de couleurs posées sur les images (FFmpeg 9 les reprend des images)."""
    couleurs = plan.couleurs
    principal = f"format={plan.format_des_pixels}"
    if couleurs.hdr_converti is not None:
        principal = f"{conversion_en_sdr(couleurs.hdr_converti, couleurs.plage_source)},{principal}"
    elif couleurs.rgb_source:  # comme le calque : convertie avec la norme de l'export
        principal = f"scale=out_color_matrix={couleurs.matrice_du_filtre}:out_range=tv,{principal}"
    elif couleurs.plage_source == "pc":
        principal = f"scale=in_range=pc:out_range=tv,{principal}"
    if couleurs.hdr:
        conversion = conversion_vers_le_hdr(NormeHDR(couleurs.matrice, couleurs.primaires, couleurs.transfert))
    else:
        conversion = conversion_des_sous_titres(couleurs.matrice)
    calque = f"{conversion},format={plan.format_du_calque}"
    etiquettes = etiquetage(couleurs.primaires, couleurs.transfert, couleurs.matrice)
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
    if plan.dolby_vision:
        # Dolby Vision repris de la source : FFmpeg passe à x265 les informations de chaque image
        # (« -dolbyvision 1 »), et x265 demande une limite de débit (VBV, voir DEBIT_MAX_DOLBY_VISION).
        options += [
            "-dolbyvision", "1", "-maxrate", str(plan.debit * DEBIT_MAX_DOLBY_VISION),
            "-bufsize", str(plan.debit * RESERVE_DOLBY_VISION),
        ]
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
    # Dolby Vision dans un MP4 : FFmpeg 9.0.2 n'écrit sa description (boîte « dvvC ») qu'avec
    # « -strict unofficial » (code de FFmpeg, libavformat/movenc.c : la boîte n'est pas dans la norme MP4).
    officieux = ["-strict", "unofficial"] if plan.dolby_vision and plan.conteneur == MP4 else []
    # « fast start » : l'index au début du fichier, la vidéo démarre avant d'être entièrement téléchargée.
    return [*officieux, "-movflags", "+faststart", "-f", "mp4" if plan.conteneur == MP4 else "mov"]


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


def texte_hdr(courbe: str, bits: int, dolby_vision: bool = False) -> str:
    """« HDR (HLG), 10 bits », « HDR (HLG, Dolby Vision), 10 bits »."""
    details = COURBES_HDR[courbe] + (", Dolby Vision" if dolby_vision else "")
    return f"HDR ({details}), {bits} bits" if bits else f"HDR ({details})"


def _couleurs_source(source: Source) -> str:
    analyse = source.analyse
    couleurs = analyse.couleurs if analyse is not None else None
    if couleurs is None:
        return ""
    texte = texte_hdr(couleurs.transfert, couleurs.bits, bool(analyse.dolby_vision)) if couleurs.hdr else couleurs.texte()
    return f"{texte} (plage complète)" if couleurs.plage == "pc" else texte


def _couleurs_export(plan: PlanVideo) -> tuple[str, str]:
    """Le texte des couleurs de l'export, et sa forme comparable à celle de la source (sans la norme
    BT.709, que le texte de la source ne donne pas)."""
    if plan.couleurs.hdr:
        texte = texte_hdr(plan.couleurs.transfert, plan.bits, plan.dolby_vision)
        return texte, texte
    gamme = "SDR (BT.709)" if plan.couleurs.matrice == "bt709" else "SDR"
    return f"{gamme}, {plan.bits} bits", f"SDR, {plan.bits} bits"


def _dolby_vision(analyse: Analyse, plan: PlanVideo, resume: Resume) -> None:
    """Dolby Vision : gardé (profil 8.4 des iPhone, en MP4 ou MKV avec H.265), sinon dit en orange ;
    le profil 5 (plateformes de streaming) n'a pas d'image lisible sans Dolby Vision : erreur."""
    profil = analyse.dolby_vision
    if not profil or plan.dolby_vision or plan.couleurs.hdr_converti is not None:
        return
    if profil == "5":
        resume.erreurs.append(
            "Ta vidéo est en Dolby Vision sans image compatible (profil 5, celui des plateformes de streaming) : "
            "ses couleurs ne peuvent pas être lues correctement, l'export est impossible."
        )
    elif profil == DOLBY_VISION_GARDE and plan.couleurs.hdr:
        resume.avertissements.append(
            "Dolby Vision n'est gardé qu'en MP4 ou en MKV, avec H.265 : en MOV, ta vidéo reste en HDR (HLG), "
            "lue partout en HDR."
        )
    else:
        gamme = f"HDR ({COURBES_HDR[plan.couleurs.transfert]})" if plan.couleurs.hdr else "SDR"
        resume.avertissements.append(
            f"Les informations Dolby Vision de ta vidéo (profil {profil}) ne sont pas gardées : elle reste en "
            f"{gamme}, lue partout."
        )


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
    couleurs_export, comparable = _couleurs_export(plan)
    couleurs_source = _couleurs_source(source)
    resume.lignes = [
        LigneResume("Taille", f"{largeur} × {hauteur}", f"{plan.largeur} × {plan.hauteur}", False),
        LigneResume("Images par seconde", frequence, frequence if images.constante else f"{frequence}, gardée", False),
        LigneResume("Débit vidéo", debit_source, debit_export, images.debit is not None and plan.debit != images.debit),
        LigneResume("Format et codec", format_source, format_export, format_source != format_export),
        LigneResume("Son", son_source, son_export, plan.son == SON_AAC),
        LigneResume("Couleurs", couleurs_source, couleurs_export, bool(couleurs_source) and couleurs_source != comparable),
        LigneResume("Durée", duree_lisible(float(images.duree)), duree_lisible(plan.duree_s), False),
        LigneResume("Poids", poids_lisible(source.poids) if source.poids else "", f"≈ {poids_lisible(plan.poids_estime)}", False),
        LigneResume("Sous-titres", "", sous_titres, False),
    ]
    _dolby_vision(analyse, plan, resume)
    if plan.debit is not None and plan.debit <= 0:
        resume.erreurs.append("Donne un débit (en Mb/s).")
    if plan.conteneur == MKV:
        resume.avertissements.append("Premiere Pro ne lit pas le MKV : pour le montage, choisis MP4 ou MOV.")
    if plan.poids_estime > LIMITE_TIKTOK:
        resume.avertissements.append(
            f"Poids estimé : {poids_lisible(plan.poids_estime)}, plus que la limite de TikTok (500 Mo). Choisis un "
            "débit plus bas, comme « Conseillé pour la publication »."
        )
    conseille = debit_conseille(largeur, hauteur, images.frequence, plan.couleurs.hdr)
    if images.codec in CODECS_DE_MONTAGE and plan.debit is not None and images.debit and plan.debit > conseille * 2:
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
