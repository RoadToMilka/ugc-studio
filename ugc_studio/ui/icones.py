"""Icônes de l'interface.

Ce sont des fichiers SVG (dessins vectoriels, nets à toutes les tailles) de la collection
Lucide, rangés dans ugc_studio/ressources/icones/. Ils sont dessinés avec la couleur
« currentColor » : on la remplace par une couleur du thème au moment de les afficher.
"""

from __future__ import annotations

import re
from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ..chemins import dossier_cache, dossier_ressources
from .theme import Couleurs, Dimensions

# Zooms d'affichage Windows courants (100 % à 300 %) : une image est préparée pour chacun,
# pour que les icônes restent nettes quel que soit le réglage de l'écran.
ECHELLES = (1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0)


def svg_colore(nom: str, couleur: str, taille: int | None = None, rempli: bool = False, trait: float | None = None) -> str:
    """Contenu SVG de l'icône `nom`, dessinée dans la couleur demandée.

    `rempli` : l'intérieur de l'icône est peint aussi (ex. étoile pleine pour une note).
    `trait` : épaisseur du trait (2 dans les icônes Lucide, sur une grille de 24) ; ex. une coche
    plus épaisse, lisible dans une petite case à cocher.
    """
    svg = (dossier_ressources() / "icones" / f"{nom}.svg").read_text(encoding="utf-8")
    if rempli:
        svg = svg.replace('fill="none"', 'fill="currentColor"', 1)
    if trait is not None:
        svg = re.sub(r'stroke-width="[\d.]+"', f'stroke-width="{trait}"', svg, count=1)
    svg = svg.replace("currentColor", couleur)
    if taille is not None:
        svg = re.sub(r'width="\d+"', f'width="{taille}"', svg, count=1)
        svg = re.sub(r'height="\d+"', f'height="{taille}"', svg, count=1)
    return svg


def image_svg(svg: str, cote: int) -> QPixmap:
    """Dessine un SVG dans une image carrée de `cote` pixels."""
    image = QPixmap(cote, cote)
    image.fill(Qt.GlobalColor.transparent)
    rendu = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    peintre = QPainter(image)
    peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
    rendu.render(peintre, QRectF(0, 0, cote, cote))
    peintre.end()
    return image


def icone(
    nom: str,
    couleur: str = Couleurs.TEXTE_SECONDAIRE,
    couleur_active: str | None = None,
    couleur_desactivee: str = Couleurs.TEXTE_DESACTIVE,
    taille: int = Dimensions.ICONE,
    rempli: bool = False,
) -> QIcon:
    """Icône Qt prête à l'emploi.

    `couleur_active` : couleur quand l'élément est sélectionné / coché (état « On »).
    Chaque icône n'est dessinée qu'une fois (8 zooms × 4 états) : une liste de 100 voix réutilise
    les mêmes images au lieu de les redessiner 100 fois.
    """
    return QIcon(_icone_dessinee(nom, couleur, couleur_active, couleur_desactivee, taille, rempli))


@lru_cache(maxsize=512)
def _icone_dessinee(
    nom: str, couleur: str, couleur_active: str | None, couleur_desactivee: str, taille: int, rempli: bool
) -> QIcon:
    resultat = QIcon()
    variantes = [
        (QIcon.Mode.Normal, QIcon.State.Off, couleur),
        (QIcon.Mode.Active, QIcon.State.Off, couleur),
        (QIcon.Mode.Selected, QIcon.State.Off, couleur),
        (QIcon.Mode.Disabled, QIcon.State.Off, couleur_desactivee),
    ]
    if couleur_active is not None:
        variantes += [
            (QIcon.Mode.Normal, QIcon.State.On, couleur_active),
            (QIcon.Mode.Active, QIcon.State.On, couleur_active),
            (QIcon.Mode.Selected, QIcon.State.On, couleur_active),
            (QIcon.Mode.Disabled, QIcon.State.On, couleur_desactivee),
        ]
    for mode, etat, teinte in variantes:
        svg = svg_colore(nom, teinte, rempli=rempli)
        for echelle in ECHELLES:
            resultat.addPixmap(image_svg(svg, round(taille * echelle)), mode, etat)
    return resultat


def icone_menu(nom: str, couleur: str = Couleurs.TEXTE_SECONDAIRE) -> QIcon:
    """Icône d'une ligne de menu, dessinée à la taille exacte des menus (16 px) pour rester nette."""
    return icone(nom, couleur, taille=Dimensions.ICONE_PETITE)


def fichier_icone(nom: str, couleur: str, taille: int = Dimensions.ICONE_PETITE, trait: float | None = None) -> str:
    """Chemin d'un fichier SVG recoloré, pour la feuille de style (qui ne lit que des fichiers).

    Le fichier est rangé dans le dossier « cache » des données de l'app et recréé si besoin.
    """
    dossier = dossier_cache() / "icones"
    dossier.mkdir(parents=True, exist_ok=True)
    epaisseur = "" if trait is None else f"-{trait}"
    chemin = dossier / f"{nom}-{couleur.lstrip('#').lower()}-{taille}{epaisseur}.svg"
    contenu = svg_colore(nom, couleur, taille, trait=trait)
    if not chemin.exists() or chemin.read_text(encoding="utf-8") != contenu:
        chemin.write_text(contenu, encoding="utf-8")
    return chemin.as_posix()


def icones_feuille_de_style() -> dict[str, str]:
    """Images utilisées par la feuille de style (voir theme.feuille_de_style)."""
    return {
        "fleche": fichier_icone("chevron-down", Couleurs.TEXTE_SECONDAIRE),
        "fleche_desactivee": fichier_icone("chevron-down", Couleurs.TEXTE_DESACTIVE),
        # La coche remplit la case (sans sa bordure), d'un trait plus épais que les autres icônes.
        "coche": fichier_icone("check", Couleurs.TEXTE, Dimensions.CASE_A_COCHER - 2 * Dimensions.BORDURE, Dimensions.COCHE_TRAIT),
    }
