"""Comparer deux vidéos (V4, lot 3) : la vidéo faite par le module et celle exportée par Topaz avec le
même réglage doivent être identiques à l'œil. FFmpeg mesure leur ressemblance image par image (SSIM :
1 pour des images identiques ; au-dessus de 0,99, aucune différence visible).

Pourquoi pas « identiques au bit près » ? Deux encodages d'une même vidéo par la carte graphique ne
donnent pas forcément exactement les mêmes octets ; ce qui compte, c'est l'image."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..exports.ffmpeg import analyser, executer, preparer_ffmpeg

IDENTIQUES = 0.99  # au-dessus : aucune différence visible
PROCHES = 0.97  # au-dessus : de très petites différences
DELAI_S = 3600


def commande_comparaison(ffmpeg: Path, premiere: Path, seconde: Path, largeur: int, hauteur: int) -> list[str]:
    """La seconde vidéo est mise à la taille de la première (si elles diffèrent), puis comparée image
    par image ; FFmpeg écrit le résultat dans ses messages (« SSIM … All:0.998 »)."""
    return [
        str(ffmpeg), "-hide_banner", "-nostdin", "-nostats", "-i", str(premiere), "-i", str(seconde),
        "-lavfi", f"[1:v]scale={largeur}:{hauteur}:flags=bicubic[seconde];[0:v][seconde]ssim",
        "-f", "null", "-",
    ]


def lire_ssim(texte: str) -> float | None:
    trouves = re.findall(r"SSIM .*?All:(\d+(?:\.\d+)?)", texte)
    return float(trouves[-1]) if trouves else None


@dataclass(frozen=True)
class Comparaison:
    ssim: float
    meme_taille: bool

    def message(self) -> str:
        pour_cent = f"{self.ssim * 100:.1f}".replace(".", ",")
        valeur = f"{self.ssim:.4f}".replace(".", ",")
        if self.ssim >= IDENTIQUES:
            verdict = "identiques à l'œil"
        elif self.ssim >= PROCHES:
            verdict = "très proches"
        else:
            verdict = "différentes : vérifie que le préréglage vient bien de cet export"
        taille = "" if self.meme_taille else " (tailles différentes : la seconde a été mise à la taille de la première)"
        return f"Ressemblance : {pour_cent} % (SSIM {valeur}), {verdict}{taille}."


class ComparaisonImpossible(Exception):
    """Message pour l'utilisateur."""


def comparer(premiere: Path, seconde: Path, ffmpeg: Path | None = None) -> Comparaison:
    ffmpeg = ffmpeg or preparer_ffmpeg()
    analyse_1, analyse_2 = analyser(premiere, ffmpeg), analyser(seconde, ffmpeg)
    if analyse_1 is None or analyse_1.images is None:
        raise ComparaisonImpossible(f"« {premiere.name} » n'est pas une vidéo lisible.")
    if analyse_2 is None or analyse_2.images is None:
        raise ComparaisonImpossible(f"« {seconde.name} » n'est pas une vidéo lisible.")
    largeur, hauteur = analyse_1.taille_affichee
    resultat = executer(commande_comparaison(ffmpeg, premiere, seconde, largeur, hauteur), DELAI_S)
    ssim = lire_ssim(resultat.stderr)
    if ssim is None:
        lignes = [ligne for ligne in resultat.stderr.splitlines() if ligne.strip()]
        raise ComparaisonImpossible(f"FFmpeg n'a pas pu comparer les vidéos : {lignes[-1] if lignes else 'erreur inconnue'}")
    return Comparaison(ssim, analyse_1.taille_affichee == analyse_2.taille_affichee)
