"""Génère l'icône de l'app (ugc_studio/ressources/app.ico et app.png) avec les couleurs du thème.

Outil de développement, lancé une seule fois (pas par l'app). Il demande la bibliothèque
Pillow. Le dessin : un carré aux coins arrondis en dégradé mauve, avec une onde sonore (la voix)
au-dessus de deux lignes de sous-titres.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from ugc_studio.ui.theme import Couleurs, composantes  # noqa: E402

COTE = 1024  # dessin en grand, puis réduction : les bords restent lisses
TAILLES_ICO = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]


def degrade(cote: int, debut: str, fin: str) -> Image.Image:
    """Dégradé en diagonale, du coin haut-gauche (début) au coin bas-droit (fin)."""
    d, f = composantes(debut), composantes(fin)
    image = Image.new("RGB", (cote, cote))
    pixels = image.load()
    for y in range(cote):
        for x in range(cote):
            t = (x + y) / (2 * (cote - 1))
            pixels[x, y] = tuple(round(d[i] + (f[i] - d[i]) * t) for i in range(3))
    return image


def dessiner() -> Image.Image:
    fond = degrade(COTE, Couleurs.ACCENT_SURVOL, Couleurs.ACCENT_PRESSE)
    masque = Image.new("L", (COTE, COTE), 0)
    ImageDraw.Draw(masque).rounded_rectangle((0, 0, COTE - 1, COTE - 1), radius=int(COTE * 0.23), fill=255)
    icone = Image.new("RGBA", (COTE, COTE), (0, 0, 0, 0))
    icone.paste(fond, (0, 0), masque)

    # Les motifs sont dessinés sur un calque séparé puis fondus sur le fond : la ligne « douce »
    # se mélange ainsi au mauve au lieu de rendre l'icône transparente à cet endroit.
    calque = Image.new("RGBA", (COTE, COTE), (0, 0, 0, 0))
    dessin = ImageDraw.Draw(calque)
    blanc = (*composantes(Couleurs.TEXTE), 255)
    blanc_doux = (*composantes(Couleurs.TEXTE), 150)

    # Onde sonore : 5 barres arrondies
    hauteurs = (0.20, 0.36, 0.50, 0.36, 0.20)
    largeur = COTE * 0.075
    ecart = COTE * 0.06
    centre_y = COTE * 0.40
    x = (COTE - (len(hauteurs) * largeur + (len(hauteurs) - 1) * ecart)) / 2
    for h in hauteurs:
        demi = COTE * h / 2
        dessin.rounded_rectangle((x, centre_y - demi, x + largeur, centre_y + demi), radius=largeur / 2, fill=blanc)
        x += largeur + ecart

    # Deux lignes de sous-titres
    epaisseur = COTE * 0.07
    dessin.rounded_rectangle(
        (COTE * 0.22, COTE * 0.70, COTE * 0.78, COTE * 0.70 + epaisseur), radius=epaisseur / 2, fill=blanc
    )
    dessin.rounded_rectangle(
        (COTE * 0.34, COTE * 0.80, COTE * 0.66, COTE * 0.80 + epaisseur), radius=epaisseur / 2, fill=blanc_doux
    )
    return Image.alpha_composite(icone, calque)


def main() -> None:
    icone = dessiner()
    dossier = RACINE / "ugc_studio" / "ressources"
    icone.resize((256, 256), Image.Resampling.LANCZOS).save(dossier / "app.png")
    icone.save(dossier / "app.ico", sizes=TAILLES_ICO)
    print("Icône générée dans", dossier)


if __name__ == "__main__":
    main()
