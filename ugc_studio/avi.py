"""Fichier vidéo AVI « Motion JPEG » (V2, lot 3) : chaque image du film est une image JPEG.

Écrit ici en quelques lignes (sans outil extérieur) pour la vidéo de test de l'autotest
(rendu/video_test.py) ; FFmpeg, fourni avec Qt Multimedia, sait le lire. Structure « RIFF » : un
en-tête (taille et cadence des images), les images, puis un index qui dit où commence chacune.
"""

from __future__ import annotations

import struct

AVIF_HASINDEX = 0x10  # le fichier a un index des images (« idx1 »)
AVIIF_KEYFRAME = 0x10  # chaque image JPEG se lit seule


def _morceau(code: bytes, donnees: bytes) -> bytes:
    """Un « morceau » RIFF : son code, sa taille, ses données (complétées à un nombre pair d'octets)."""
    return code + struct.pack("<I", len(donnees)) + donnees + (b"\0" if len(donnees) % 2 else b"")


def _liste(sorte: bytes, contenu: bytes) -> bytes:
    return b"LIST" + struct.pack("<I", len(contenu) + 4) + sorte + contenu


def avi_mjpeg(images_jpeg: list[bytes], largeur: int, hauteur: int, images_par_seconde: int) -> bytes:
    """Fichier AVI dont chaque image est une image JPEG (en-tête, images, index)."""
    nombre = len(images_jpeg)
    plus_grande = max((len(image) for image in images_jpeg), default=0)
    entete_avi = struct.pack(
        "<14I",
        1_000_000 // images_par_seconde,  # durée d'une image, en microsecondes
        plus_grande * images_par_seconde,
        0,
        AVIF_HASINDEX,
        nombre,
        0,
        1,  # un seul flux : la vidéo
        plus_grande,
        largeur,
        hauteur,
        0, 0, 0, 0,
    )
    entete_flux = struct.pack(
        "<4s4sIHHIIIIIIiI4h",
        b"vids", b"MJPG", 0, 0, 0, 0,
        1, images_par_seconde,  # cadence : images_par_seconde / 1
        0, nombre, plus_grande, -1, 0,
        0, 0, largeur, hauteur,
    )
    format_images = struct.pack("<IiiHH4sIiiII", 40, largeur, hauteur, 1, 24, b"MJPG", largeur * hauteur * 3, 0, 0, 0, 0)
    entetes = _liste(b"hdrl", _morceau(b"avih", entete_avi) + _liste(b"strl", _morceau(b"strh", entete_flux) + _morceau(b"strf", format_images)))
    morceaux, index, position = [], [], 4  # position : depuis le code « movi »
    for image in images_jpeg:
        morceau = _morceau(b"00dc", image)
        index.append(struct.pack("<4sIII", b"00dc", AVIIF_KEYFRAME, position, len(image)))
        morceaux.append(morceau)
        position += len(morceau)
    contenu = entetes + _liste(b"movi", b"".join(morceaux)) + _morceau(b"idx1", b"".join(index))
    return b"RIFF" + struct.pack("<I", len(contenu) + 4) + b"AVI " + contenu
