"""Photos fabriquées pour les tests de Doublons (V4.3) : chaque « graine » donne une scène différente
(un fond en dégradé, des formes de toutes les couleurs, un peu de grain), toujours la même pour une même
graine, et ses déclinaisons (comme une photo retouchée)."""

from __future__ import annotations

import io
import random

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps


def photo_factice(graine: int, taille: tuple[int, int] = (480, 640)) -> Image.Image:
    """Une scène reconnaissable, différente pour chaque graine (RGB)."""
    hasard = random.Random(graine)
    largeur, hauteur = taille
    haut = tuple(hasard.randrange(256) for _ in range(3))
    bas = tuple(hasard.randrange(256) for _ in range(3))
    degrade = Image.linear_gradient("L").resize(taille)
    image = Image.composite(Image.new("RGB", taille, bas), Image.new("RGB", taille, haut), degrade)
    dessin = ImageDraw.Draw(image)
    for _ in range(18):
        x0, y0 = hasard.randrange(largeur), hasard.randrange(hauteur)
        x1, y1 = x0 + hasard.randrange(20, largeur // 2), y0 + hasard.randrange(20, hauteur // 2)
        couleur = tuple(hasard.randrange(256) for _ in range(3))
        forme = hasard.choice(("ellipse", "rectangle", "ligne"))
        if forme == "ellipse":
            dessin.ellipse((x0, y0, x1, y1), fill=couleur)
        elif forme == "rectangle":
            dessin.rectangle((x0, y0, x1, y1), fill=couleur)
        else:
            dessin.line((x0, y0, x1, y1), fill=couleur, width=hasard.randrange(3, 14))
    image = image.filter(ImageFilter.GaussianBlur(1.2))
    grain = Image.effect_noise(taille, 18).convert("RGB")
    return Image.blend(image, grain, 0.08)


def en_jpeg(image: Image.Image, qualite: int = 80) -> Image.Image:
    tampon = io.BytesIO()
    image.save(tampon, "JPEG", quality=qualite)
    tampon.seek(0)
    return Image.open(tampon).convert("RGB")


def plus_petite(image: Image.Image, facteur: float = 0.5, qualite: int = 60) -> Image.Image:
    largeur, hauteur = image.size
    return en_jpeg(image.resize((round(largeur * facteur), round(hauteur * facteur)), Image.Resampling.BILINEAR), qualite)


def autres_couleurs(image: Image.Image) -> Image.Image:
    plus_claire = ImageEnhance.Brightness(image).enhance(1.25)
    return ImageEnhance.Color(ImageEnhance.Contrast(plus_claire).enhance(1.2)).enhance(0.6)


def noir_et_blanc(image: Image.Image) -> Image.Image:
    return ImageOps.grayscale(image).convert("RGB")


def miroir(image: Image.Image) -> Image.Image:
    return image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)


def au_carre_avec_bords(image: Image.Image, couleur=(255, 255, 255)) -> Image.Image:
    largeur, hauteur = image.size
    cote = max(largeur, hauteur)
    carre = Image.new("RGB", (cote, cote), couleur)
    carre.paste(image, ((cote - largeur) // 2, (cote - hauteur) // 2))
    return carre


def recadree(image: Image.Image, part: float = 0.6) -> Image.Image:
    """Le centre de la photo, `part` de sa largeur et de sa hauteur."""
    largeur, hauteur = image.size
    l, h = round(largeur * part), round(hauteur * part)
    return image.crop(((largeur - l) // 2, (hauteur - h) // 2, (largeur - l) // 2 + l, (hauteur - h) // 2 + h))
