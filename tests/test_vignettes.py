"""Vignettes du module Renommer (V4, lot 2) : petites, dans le bon sens, transparence gardée, une image
illisible ne bloque pas les autres, et « arrêter » arrête."""

import threading

from PIL import Image

from ugc_studio.images.redimensionnement import ORIENTATION
from ugc_studio.images.vignettes import faire_les_vignettes, vignette


def test_vignette_petite_et_dans_le_bon_sens(tmp_path):
    exif = Image.Exif()
    exif[ORIENTATION] = 6  # enregistrée couchée : 1600 × 1200, vue 1200 × 1600
    Image.new("RGB", (1600, 1200), (200, 60, 40)).save(tmp_path / "photo.jpg", quality=90, exif=exif.tobytes())
    petite = vignette(tmp_path / "photo.jpg", 120)
    assert petite.size == (90, 120) and petite.mode == "RGBA"
    Image.new("RGBA", (400, 100), (0, 0, 255, 0)).save(tmp_path / "logo.png")
    logo = vignette(tmp_path / "logo.png", 120)
    assert logo.size == (120, 30) and logo.getpixel((5, 5))[3] == 0  # transparence gardée
    Image.new("RGB", (40, 30)).save(tmp_path / "minuscule.png")
    assert vignette(tmp_path / "minuscule.png", 120).size == (40, 30)  # jamais agrandie


def test_faire_les_vignettes(tmp_path):
    for nom in ("a.png", "b.png", "c.png"):
        Image.new("RGB", (300, 200)).save(tmp_path / nom)
    (tmp_path / "abimee.jpg").write_bytes(b"pas une image")
    recues = {}
    nombre = faire_les_vignettes(
        [tmp_path / nom for nom in ("a.png", "abimee.jpg", "b.png", "c.png")],
        60,
        lambda image: image.size,
        lambda valeur: recues.__setitem__(valeur[0].name, valeur[1]),
        threading.Event(),
    )
    assert nombre == 4 and recues == {"a.png": (60, 40), "abimee.jpg": None, "b.png": (60, 40), "c.png": (60, 40)}


def test_arreter_les_vignettes(tmp_path):
    Image.new("RGB", (300, 200)).save(tmp_path / "a.png")
    arret = threading.Event()
    arret.set()
    recues = []
    assert faire_les_vignettes([tmp_path / "a.png"] * 5, 60, lambda image: image, recues.append, arret) == 0
    assert recues == []
