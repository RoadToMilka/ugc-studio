"""Calque provisoire de la vidéo avec sous-titres (V3, lot 2, §8.3) : un fichier MOV dont chaque
image est un PNG avec transparence, qui dure exactement le temps voulu.

Pourquoi un fichier provisoire ? La vidéo est encodée en deux passages (§8.3) : le calque doit donc
être relu deux fois, à l'identique. Pourquoi l'écrire ici plutôt que par FFmpeg ? Chaque image du
calque doit commencer au moment exact d'une image de la vidéo, même quand leurs écarts varient
(fréquence variable d'un iPhone ou d'un enregistrement d'écran). FFmpeg, lui, ne sait recevoir des
images qu'à une fréquence fixe. Un MOV, si : chaque image y a sa durée, comptée dans l'unité de temps
de la vidéo elle-même (1/30 000 s, 1/600 s…), donc sans arrondi. Et une image qui ne change pas (rien
ne bouge) n'y est écrite qu'une fois, avec une durée plus longue : le fichier reste petit.

Le format QuickTime (le MOV) range le fichier en « boîtes » : une taille, un nom de 4 lettres, puis
le contenu. Ici : « ftyp » (le genre de fichier), « mdat » (les images, à la suite), puis « moov » (la
table des matières : taille des images, leurs durées, où elles sont). Seul ce dont FFmpeg a besoin
est écrit (spécification QuickTime d'Apple, « QuickTime File Format »).
"""

from __future__ import annotations

import struct
from pathlib import Path

MATRICE_IDENTITE = struct.pack(">9I", 0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000)


def boite(nom: bytes, *contenu: bytes) -> bytes:
    """Une boîte : sa taille (4 octets, elle comprise), son nom (4 lettres), son contenu."""
    corps = b"".join(contenu)
    return struct.pack(">I", 8 + len(corps)) + nom + corps


def boite_pleine(nom: bytes, version: int, drapeaux: int, *contenu: bytes) -> bytes:
    """Une boîte « pleine » : version (1 octet) et drapeaux (3 octets) avant le contenu."""
    return boite(nom, struct.pack(">I", (version << 24) | drapeaux), *contenu)


class EcritureMovPng:
    """Écrit un MOV d'images PNG, chacune avec sa durée (en unités de `echelle` par seconde).

    ajouter() une image après l'autre, puis fermer(). Si une image est identique à la précédente,
    prolonger() allonge la précédente au lieu de la recopier."""

    def __init__(self, chemin: Path, largeur: int, hauteur: int, echelle: int):
        if echelle <= 0 or largeur <= 0 or hauteur <= 0:
            raise ValueError("taille et unité de temps du calque provisoire invalides")
        self.chemin, self.largeur, self.hauteur, self.echelle = chemin, largeur, hauteur, echelle
        self._tailles: list[int] = []
        self._durees: list[int] = []
        self._fichier = chemin.open("wb")
        self._fichier.write(boite(b"ftyp", b"qt  ", struct.pack(">I", 0x200), b"qt  "))
        self._debut_mdat = self._fichier.tell()
        # « mdat » de taille encore inconnue : taille écrite sur 8 octets (marqueur 1), complétée à la fin.
        self._fichier.write(struct.pack(">I4sQ", 1, b"mdat", 0))
        self._debut_images = self._fichier.tell()

    @property
    def nombre(self) -> int:
        return len(self._tailles)

    @property
    def duree(self) -> int:
        return sum(self._durees)

    def ajouter(self, png: bytes, duree: int) -> None:
        if duree <= 0:
            raise ValueError("une image du calque doit durer au moins une unité de temps")
        self._fichier.write(png)
        self._tailles.append(len(png))
        self._durees.append(duree)

    def prolonger(self, duree: int) -> None:
        """La dernière image dure `duree` unités de plus (elle ne change pas)."""
        if not self._durees:
            raise ValueError("aucune image à prolonger")
        self._durees[-1] += duree

    def fermer(self) -> None:
        fichier = self._fichier
        fin_images = fichier.tell()
        fichier.seek(self._debut_mdat + 8)
        fichier.write(struct.pack(">Q", fin_images - self._debut_mdat))
        fichier.seek(fin_images)
        fichier.write(self._moov())
        fichier.close()

    def annuler(self) -> None:
        self._fichier.close()
        self.chemin.unlink(missing_ok=True)

    # --- Table des matières ----------------------------------------------------------------------

    def _moov(self) -> bytes:
        duree = self.duree
        mvhd = boite_pleine(
            b"mvhd", 1, 0,
            struct.pack(">QQIQ", 0, 0, self.echelle, duree),  # dates (inutiles ici), unité de temps, durée
            struct.pack(">IH10x", 0x10000, 0x100),  # vitesse 1, volume 1
            MATRICE_IDENTITE,
            bytes(24),  # aperçu, affiche, sélection, moment courant : rien
            struct.pack(">I", 2),  # numéro de la prochaine piste
        )
        tkhd = boite_pleine(
            b"tkhd", 1, 0x3,  # piste active, dans le film
            struct.pack(">QQI4xQ8xhhh2x", 0, 0, 1, duree, 0, 0, 0),
            MATRICE_IDENTITE,
            struct.pack(">II", self.largeur << 16, self.hauteur << 16),
        )
        mdhd = boite_pleine(b"mdhd", 1, 0, struct.pack(">QQIQHH", 0, 0, self.echelle, duree, 0, 0))
        hdlr = boite_pleine(b"hdlr", 0, 0, b"mhlr", b"vide", bytes(12), b"\x0cVideoHandler")
        vmhd = boite_pleine(b"vmhd", 0, 1, struct.pack(">H3H", 0, 0, 0, 0))
        dinf = boite(b"dinf", boite_pleine(b"dref", 0, 0, struct.pack(">I", 1), boite_pleine(b"alis", 0, 1)))
        nom_du_codec = b"PNG"
        entree_png = boite(
            b"png ",
            bytes(6), struct.pack(">H", 1),  # réservé, n° de la référence de données
            struct.pack(">HH4sII", 0, 0, b"UGCS", 0, 0x200),  # version, révision, fabricant, qualités
            struct.pack(">HHIIIH", self.largeur, self.hauteur, 0x480000, 0x480000, 0, 1),  # 72 ppp, 1 image par échantillon
            bytes([len(nom_du_codec)]) + nom_du_codec + bytes(31 - len(nom_du_codec)),
            struct.pack(">Hh", 32, -1),  # 32 bits par pixel (avec transparence), pas de palette
        )
        stsd = boite_pleine(b"stsd", 0, 0, struct.pack(">I", 1), entree_png)
        stts = boite_pleine(b"stts", 0, 0, *self._durees_regroupees())
        stsc = boite_pleine(b"stsc", 0, 0, struct.pack(">IIII", 1, 1, self.nombre, 1))  # un seul bloc
        stsz = boite_pleine(b"stsz", 0, 0, struct.pack(">II", 0, self.nombre), struct.pack(f">{self.nombre}I", *self._tailles))
        co64 = boite_pleine(b"co64", 0, 0, struct.pack(">IQ", 1, self._debut_images))
        stbl = boite(b"stbl", stsd, stts, stsc, stsz, co64)
        minf = boite(b"minf", vmhd, dinf, stbl)
        mdia = boite(b"mdia", mdhd, hdlr, minf)
        trak = boite(b"trak", tkhd, mdia)
        return boite(b"moov", mvhd, trak)

    def _durees_regroupees(self) -> list[bytes]:
        """Table « stts » : les durées, regroupées quand elles se suivent identiques (nombre, durée)."""
        groupes: list[list[int]] = []
        for duree in self._durees:
            if groupes and groupes[-1][1] == duree:
                groupes[-1][0] += 1
            else:
                groupes.append([1, duree])
        return [struct.pack(">I", len(groupes)), *(struct.pack(">II", nombre, duree) for nombre, duree in groupes)]
