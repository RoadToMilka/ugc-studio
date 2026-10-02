"""V3, lot 1 (§8.2, §8.4) : fréquences d'images exactes et moment de chaque image (sans interface)."""

from fractions import Fraction

import pytest

from ugc_studio.exports.cadence import (
    duree_lisible,
    frequence_exacte,
    nombre_d_images,
    temps_de_l_image,
    texte_ffmpeg,
    texte_frequence,
)


@pytest.mark.parametrize(
    ("valeur", "attendue"),
    [
        (29.97002997002997, Fraction(30000, 1001)),  # ce que donne Qt pour une vidéo « 29,97 »
        (29.97, Fraction(30000, 1001)),
        (23.976023976, Fraction(24000, 1001)),
        (59.94005994, Fraction(60000, 1001)),
        (25.0, Fraction(25)),
        (30.0, Fraction(30)),
        (30.01, Fraction(30)),  # un iPhone réglé sur 30 : à peine plus ou moins
        (60, Fraction(60)),
        (12.5, Fraction(25, 2)),  # fréquence rare : fraction simple
        (Fraction(10), Fraction(10)),
    ],
)
def test_frequence_exacte(valeur, attendue):
    assert frequence_exacte(valeur) == attendue


@pytest.mark.parametrize("valeur", [None, 0, -25, "illisible", float("nan"), float("inf")])
def test_frequence_inconnue(valeur):
    assert frequence_exacte(valeur) is None


def test_moment_de_chaque_image_sans_decalage_apres_10_minutes():
    """Le moment d'une image vient de son numéro (numéro × 1 001 ÷ 30 000), exactement : après
    10 minutes à 29,97 images par seconde, l'image 17 982 du calque tombe sur l'image 17 982 de la
    vidéo, au même moment, sans rien qui s'accumule. Prendre 30 aurait décalé de 0,6 s."""
    frequence = Fraction(30000, 1001)
    numero = 17_982  # ≈ 600 s
    assert temps_de_l_image(numero, frequence) == Fraction(numero * 1001, 30000)
    # Une vidéo à 29,97 décrite par FFmpeg : unité de temps 1/30 000, images tous les 1 001.
    moments_de_la_video = [Fraction(n * 1001, 30000) for n in range(numero + 1)]
    assert all(temps_de_l_image(n, frequence) == moments_de_la_video[n] for n in range(numero + 1))
    assert abs(float(temps_de_l_image(numero, Fraction(30))) - float(moments_de_la_video[-1])) > 0.5


@pytest.mark.parametrize(
    ("duree", "frequence", "attendu"),
    [(2.0, Fraction(25), 50), (7.4, Fraction(10), 74), (7.42, Fraction(10), 75), (0.0, Fraction(30), 1), (1.0, Fraction(30000, 1001), 30)],
)
def test_nombre_d_images(duree, frequence, attendu):
    assert nombre_d_images(duree, frequence) == attendu


def test_textes():
    assert texte_frequence(Fraction(30000, 1001)) == "29,97"
    assert texte_frequence(Fraction(24000, 1001)) == "23,976"
    assert texte_frequence(Fraction(60000, 1001)) == "59,94"
    assert texte_frequence(Fraction(30)) == "30"
    assert texte_frequence(Fraction(25, 2)) == "12,5"
    assert texte_frequence(None) == "inconnue"
    assert texte_ffmpeg(Fraction(30000, 1001)) == "30000/1001"
    assert texte_ffmpeg(Fraction(30)) == "30/1"
    assert duree_lisible(31.03) == "0:31"
    assert duree_lisible(72.5) == "1:12"
