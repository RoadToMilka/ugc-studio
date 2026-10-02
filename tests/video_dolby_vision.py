"""Une petite vidéo Dolby Vision (profil 8.4, celui des iPhone) fabriquée pour les tests (V3, lot 3).

Une vidéo d'iPhone en HDR contient trois choses :
1. une image HLG ordinaire (H.265, 10 bits, BT.2020) : tout lecteur la montre en HDR ;
2. des informations Dolby Vision pour chaque image (« RPU », dans une unité du flux H.265 de type 62),
   qui aident un écran Dolby Vision à l'afficher au mieux ;
3. dans le MP4, une boîte « dvvC » qui annonce le profil (8), la compatibilité (4 : HLG) et le niveau.

Ici : FFmpeg fabrique l'image HLG (1), avec un délimiteur au début de chaque image (option « aud » de
x265) et sans images B ; une même RPU est ajoutée à la fin de chacune (2) ; FFmpeg range le tout dans un MP4 ; puis la
boîte « dvvC » est ajoutée dans la description de la vidéo (3). Rien ne dépend de l'export testé.

La RPU vient d'une vidéo d'iPhone : fichier assets/tests/profile84.bin du projet dovi_tool
(https://github.com/quietvoid/dovi_tool, licence MIT, © quietvoid), sans son code de début
(00 00 00 01). Elle contient déjà ses octets « anti-émulation » (00 00 03).
"""

from __future__ import annotations

import re
import struct
from fractions import Fraction
from pathlib import Path

RPU_PROFIL_8_4 = bytes.fromhex(
    "19080908406136506e203f114e6401000941002007801ffc00fffa7e6fec17f26373ca9a60a7f8bbc14f242c2bba6cfa"
    "941a97d175a07c6219aa8164ae7e11628bae32be73af0b4a33191830b8a18d335503ac32640202590a2834ef60c01ee8"
    "1340041528c0281c1db70003e92fde00225cfdc0522319cec0aa9d96f85fd0b139b8841f3a802b21f1404a7200c0660f"
    "0383fd4b02ec670d991bb4e3ddf8942cbebba065c127c024c202e0fe5adad8e2ff96d8c43c712d311ae6680e9bf49809"
    "ef955828b7e7400402f250d1ed28149bd470be8dec022a930d1afa5154b4c2b44e74c7c69c97946f800b052395203027"
    "a643ad79e04996d66418cbe6b118448a39681823ba4088f61b470a876844d8714d12b300001af512b37cfe758e12b322"
    "6500000300800000040000030004000003000e1b112180c3052f1847028a00000300d31f2d7fff800000030000030000"
    "030030103ee700a8c030080169b99980c028218008008005b6854100020200000300080500000300000300000300120c"
    "1f400064000003000041e68e9c80"
)
CODE_DE_DEBUT = b"\x00\x00\x00\x01"
UNITE_RPU = CODE_DE_DEBUT + b"\x7c\x01" + RPU_PROFIL_8_4  # en-tête d'une unité H.265 de type 62
DELIMITEUR = CODE_DE_DEBUT + b"\x46\x01"  # unité H.265 de type 35 : début d'une image


def _boites(donnees: bytes, debut: int, fin: int):
    """Les boîtes MP4 entre `debut` et `fin` : (nom, position, taille, taille de l'en-tête)."""
    position = debut
    while position + 8 <= fin:
        taille, nom = struct.unpack_from(">I4s", donnees, position)
        entete = 8
        if taille == 1:
            taille, entete = struct.unpack_from(">Q", donnees, position + 8)[0], 16
        elif taille == 0:
            taille = fin - position
        yield nom, position, taille, entete
        position += taille


def ajouter_dvvc(mp4: Path, profil: int = 8, niveau: int = 1, compatibilite: int = 4) -> None:
    """Ajoute la boîte « dvvC » (DOVIDecoderConfigurationRecord, 24 octets) dans la description de la
    vidéo (moov > trak > mdia > minf > stbl > stsd > hvc1). Les boîtes qui la contiennent grandissent
    d'autant ; le MP4 a son index (moov) après les images (mdat) : l'emplacement des images ne change pas."""
    donnees = bytearray(mp4.read_bytes())
    debut, fin, parents = 0, len(donnees), []
    for voulue in (b"moov", b"trak", b"mdia", b"minf", b"stbl", b"stsd"):
        _nom, position, taille, entete = next(b for b in _boites(donnees, debut, fin) if b[0] == voulue)
        parents.append(position)
        debut, fin = position + entete + (8 if voulue == b"stsd" else 0), position + taille  # stsd : version, nombre
    _nom, position, taille, _entete = next(b for b in _boites(donnees, debut, fin) if b[0] in (b"hvc1", b"hev1"))
    parents.append(position)
    drapeaux = (profil << 9) | (niveau << 3) | 0b101  # RPU présente, pas de couche d'amélioration, image de base présente
    config = bytes([1, 0]) + struct.pack(">H", drapeaux) + bytes([compatibilite << 4]) + bytes(19)
    boite = struct.pack(">I4s", 8 + len(config), b"dvvC") + config
    donnees[position + taille : position + taille] = boite
    for parent in parents:
        struct.pack_into(">I", donnees, parent, struct.unpack_from(">I", donnees, parent)[0] + len(boite))
    mp4.write_bytes(bytes(donnees))


def fabriquer_video_dolby_vision(executer, ffmpeg: Path, chemin: Path, taille: str = "128x96", frequence: Fraction = Fraction(30), duree_s: float = 0.5) -> None:
    """Une vidéo HLG avec Dolby Vision (profil 8.4) : `chemin` (un .mp4)."""
    base, flux = chemin.with_suffix(".base.hevc"), chemin.with_suffix(".dv.hevc")
    commun = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y"]
    resultat = executer([
        *commun, "-f", "lavfi", "-i", f"testsrc2=size={taille}:rate={frequence.numerator}/{frequence.denominator}", "-t", str(duree_s),
        "-vf", "zscale=rin=limited:pin=bt709:tin=bt709:min=bt709:p=bt2020:t=arib-std-b67:m=bt2020nc:r=limited:npl=203,"
               "format=yuv420p10le,setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc:range=tv",
        # Sans images B (« bframes=0 ») : un flux H.265 brut ne dit pas l'ordre d'affichage des images ;
        # sans elles, il est celui du flux, et le MP4 a les bons moments.
        "-c:v", "libx265", "-x265-params", "log-level=error:aud=1:bframes=0", "-f", "hevc", str(base),
    ], 120)
    assert resultat.returncode == 0, resultat.stderr
    donnees = base.read_bytes()
    debuts = [m.start() for m in re.finditer(re.escape(DELIMITEUR), donnees)]
    assert debuts and debuts[0] == 0, "x265 n'a pas écrit de délimiteur au début de chaque image"
    images = [donnees[a:b] for a, b in zip(debuts, [*debuts[1:], len(donnees)], strict=True)]
    flux.write_bytes(b"".join(image + UNITE_RPU for image in images))
    resultat = executer([
        *commun, "-f", "hevc", "-framerate", f"{frequence.numerator}/{frequence.denominator}", "-i", str(flux),
        "-c", "copy", "-tag:v", "hvc1", "-f", "mp4", str(chemin),
    ], 120)
    assert resultat.returncode == 0, resultat.stderr
    ajouter_dvvc(chemin)
    base.unlink()
    flux.unlink()
