"""Fréquences d'images exactes (V3, §8.2 et §8.4).

Une vidéo « à 29,97 images par seconde » en a en réalité 30 000 pour 1 001 secondes (29,970029…).
Prendre 30 décalerait le calque de 0,1 % : au bout de 10 minutes, 0,6 s (18 images) d'écart avec la
vidéo. Les fréquences sont donc gardées sous forme de fraction exacte (Fraction), la même que celle
de la vidéo, et le moment de chaque image est calculé directement depuis son numéro (numéro × 1 001
÷ 30 000), jamais en ajoutant des durées les unes aux autres : aucune erreur d'arrondi ne
s'accumule, et l'image n du calque tombe exactement sur l'image n de la vidéo.

Qt donne la fréquence d'une vidéo sous forme de nombre à virgule (29,970029…) : elle est ramenée à
la fréquence courante la plus proche (30 000 / 1 001), ou à une fraction simple sinon. FFmpeg, lui,
donne le moment exact de chaque image (source.py) : c'est la référence quand on l'a.
"""

from __future__ import annotations

import math
from fractions import Fraction

# Fréquences utilisées par les caméras, les téléphones et les logiciels de montage.
FREQUENCES_COURANTES: tuple[Fraction, ...] = (
    Fraction(24000, 1001),  # 23,976 (cinéma, en NTSC)
    Fraction(24),
    Fraction(25),  # Europe
    Fraction(30000, 1001),  # 29,97 (NTSC, beaucoup de vidéos de téléphone)
    Fraction(30),
    Fraction(48),
    Fraction(50),
    Fraction(60000, 1001),  # 59,94
    Fraction(60),
    Fraction(90),
    Fraction(100),
    Fraction(120000, 1001),
    Fraction(120),
    Fraction(240),
)
ECART_ACCEPTE = 0.0005  # 0,05 % : 29,970029… devient 29,97 (30 000 / 1 001) ; 30,01 devient 30
DENOMINATEUR_MAX = 1001
FREQUENCE_SANS_VIDEO = Fraction(30)  # projet sans vidéo : 30 images par seconde au départ (§8.4)
FREQUENCE_MIN, FREQUENCE_MAX = 1, 240  # valeur libre (projet sans vidéo)


def frequence_exacte(valeur: float | Fraction | None) -> Fraction | None:
    """Fréquence donnée par Qt (29,970029…) → fraction exacte (30 000 / 1 001). None : inconnue."""
    if valeur is None:
        return None
    if isinstance(valeur, Fraction):
        return valeur if valeur > 0 else None
    try:
        valeur = float(valeur)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(valeur) or valeur <= 0:
        return None
    proche = min(FREQUENCES_COURANTES, key=lambda f: abs(float(f) - valeur))
    if abs(float(proche) - valeur) <= valeur * ECART_ACCEPTE:
        return proche
    return Fraction(valeur).limit_denominator(DENOMINATEUR_MAX)


def temps_de_l_image(numero: int, frequence: Fraction) -> Fraction:
    """Moment exact (en secondes) où commence l'image `numero` (la première est la 0)."""
    return Fraction(numero) / frequence


def nombre_d_images(duree_s: float, frequence: Fraction) -> int:
    """Images nécessaires pour couvrir `duree_s` à cette fréquence (au moins une). Un millième
    d'image de tolérance : 2 s à 25 images par seconde donnent 50 images, pas 51."""
    if duree_s <= 0:
        return 1
    return max(1, math.ceil(duree_s * frequence - Fraction(1, 1000)))


def texte_frequence(frequence: Fraction | None) -> str:
    """30000/1001 → « 29,97 » ; 24000/1001 → « 23,976 » ; 30 → « 30 » (à la française)."""
    if frequence is None:
        return "inconnue"
    texte = f"{float(frequence):.3f}".rstrip("0").rstrip(".")
    return texte.replace(".", ",")


def texte_ffmpeg(frequence: Fraction) -> str:
    """Fréquence écrite pour FFmpeg : « 30000/1001 », exacte."""
    return f"{frequence.numerator}/{frequence.denominator}"


def duree_lisible(secondes: float) -> str:
    """31,03 → « 0:31 » ; 72,5 → « 1:12 » (minutes et secondes entières, arrondies au plus proche)."""
    total = max(0, round(secondes))
    return f"{total // 60}:{total % 60:02d}"
