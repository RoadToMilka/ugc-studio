"""Moteur de dessin des sous-titres (V2, lot 3 ; cahier des charges §7.7) : un seul morceau de code
pour l'aperçu et, en V3, pour les exports.

Le principe :
- Le texte devient des **formes** (le contour exact de chaque lettre, QPainterPath) à la taille
  réelle de la vidéo, par exemple 1080 × 1920. L'aperçu les dessine en plus petit ; l'export de la
  V3 les dessinera à 100 %, sur un fond transparent (image()). Une forme réduite garde exactement
  ses proportions : ce que montre l'aperçu est ce qui sera exporté, à la finesse de l'écran près.
- Le **découpage** mesure la largeur des lignes avec ce même moteur (mesure()) : « ça tient » veut
  dire « ça tient une fois dessiné ».
- La place de chaque ligne et de chaque mot vient de mise_en_page.py (testé sans interface).
- Ce qui ne bouge pas (au lot 3 : un sous-titre entier, avec son ombre) est dessiné une fois par
  taille d'affichage, puis gardé en mémoire : pendant la lecture, l'aperçu ne fait que le recopier.

Police (lot 3) : Inter SemiBold, à la taille du texte arrondie au pixel de la vidéo, comme la mesure
de la V1 : un projet de la 1.1.0 garde exactement son découpage.

Ordre de dessin : ombre, puis remplissage (le contour, le fond et la lueur arrivent au lot 4).
"""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QTransform

from ..mise_en_page import Bloc, Metriques, placer
from ..sous_titres import MotAffiche, ReglagesSousTitres, SousTitre, cadre
from ..style_sous_titres import Couleur, StyleTexte
from ..ui.polices import police

RENDUS_GARDES = 96  # sous-titres déjà dessinés gardés en mémoire (toutes tailles d'affichage confondues)
FLOU_MINIMUM = 0.75  # en dessous (en pixels de l'image), le flou ne se verrait pas : il n'est pas calculé


def police_du_texte(style: StyleTexte, taille_px: int) -> QFont:
    """Police du style à cette taille (en pixels de la vidéo). Inter passe par ui/polices.py, qui
    choisit la bonne famille selon la graisse (particularité de Windows)."""
    return police(max(1, taille_px), style.graisse)


def qcouleur(couleur: Couleur, opaque: bool = False) -> QColor:
    """Couleur du style → couleur Qt (avec son opacité, sauf si `opaque`)."""
    resultat = QColor(couleur.rouge, couleur.vert, couleur.bleu)
    if not opaque:
        resultat.setAlphaF(couleur.opacite / 100)
    return resultat


def _image_vide(largeur: int, hauteur: int) -> QImage:
    image = QImage(max(1, largeur), max(1, hauteur), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    return image


def flouter(image: QImage, rayon: float) -> QImage:
    """Image floutée d'environ `rayon` pixels : réduite (chaque point devient la moyenne de ses
    voisins), puis agrandie à sa taille (lissée). Rapide, et toujours le même résultat."""
    if rayon < FLOU_MINIMUM:
        return image
    largeur, hauteur = image.width(), image.height()
    facteur = max(1.0, rayon / 2)
    petite = image.scaled(
        max(1, round(largeur / facteur)),
        max(1, round(hauteur / facteur)),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return petite.scaled(largeur, hauteur, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


@dataclass(frozen=True)
class Rendu:
    """Un sous-titre dessiné à une taille d'affichage : son image et sa place, en pixels de
    l'image par rapport au coin haut gauche de la vidéo (nombres entiers : l'image tombe pile sur
    les pixels, l'aperçu à 100 % et l'export sont donc identiques)."""

    image: QImage
    x: int
    y: int


class Moteur:
    """Moteur de dessin pour une vidéo de `largeur` × `hauteur` pixels et des réglages donnés.
    Un nouveau moteur est créé à chaque changement de réglage (ses mémoires repartent de zéro)."""

    def __init__(self, reglages: ReglagesSousTitres, largeur: int, hauteur: int):
        self.reglages = reglages
        self.largeur, self.hauteur = largeur, hauteur
        self.zone = cadre(reglages, largeur, hauteur)
        self.taille_px = max(1, round(hauteur * reglages.texte.taille_pct / 100))
        self.police = police_du_texte(reglages.texte, self.taille_px)
        self._metriques_qt = QFontMetricsF(self.police)
        self.metriques = Metriques(
            self._metriques_qt.ascent(), self._metriques_qt.descent(), self._metriques_qt.lineSpacing()
        )
        self._largeurs: dict[str, float] = {}
        self._formes_des_mots: dict[str, QPainterPath] = {}
        self._rendus: OrderedDict[tuple, Rendu] = OrderedDict()

    # --- Mesure (découpage) et mise en page ------------------------------------------------------

    def mesure(self, texte: str) -> float:
        """Largeur d'une ligne de texte, en pixels de la vidéo, telle qu'elle sera dessinée."""
        if texte not in self._largeurs:
            self._largeurs[texte] = self._metriques_qt.horizontalAdvance(texte)
        return self._largeurs[texte]

    def bloc(self, sous_titre: SousTitre, mots: list[MotAffiche]) -> Bloc:
        return placer(sous_titre, mots, self.reglages, self.zone, self.metriques, self.mesure)

    # --- Formes --------------------------------------------------------------------------------

    def _forme_du_mot(self, texte: str) -> QPainterPath:
        """Contour des lettres d'un mot, sa ligne de base en y = 0 et son début en x = 0."""
        if texte not in self._formes_des_mots:
            forme = QPainterPath()
            forme.addText(QPointF(0, 0), self.police, texte)
            self._formes_des_mots[texte] = forme
        return self._formes_des_mots[texte]

    def forme(self, bloc: Bloc) -> QPainterPath:
        """Contour de toutes les lettres du sous-titre, à leur place dans la vidéo."""
        forme = QPainterPath()
        forme.setFillRule(Qt.FillRule.WindingFill)  # lettres qui se touchent : jamais de trou
        for mot in bloc.mots:
            ligne = bloc.lignes[mot.ligne]
            transformation = QTransform()
            transformation.translate(mot.x, ligne.base)
            transformation.scale(bloc.echelle, bloc.echelle)  # mot seul rapetissé (§7.3)
            forme.addPath(transformation.map(self._forme_du_mot(mot.texte)))
        return forme

    # --- Dessin ---------------------------------------------------------------------------------

    def rendu(self, sous_titre: SousTitre, mots: list[MotAffiche], echelle: float, ratio_ecran: float = 1.0) -> Rendu:
        """Le sous-titre dessiné à `echelle` points par pixel de vidéo, sur un écran qui a
        `ratio_ecran` pixels réels par point (gardé en mémoire)."""
        cle = (
            sous_titre.premier_mot, sous_titre.dernier_mot, tuple(sous_titre.lignes), sous_titre.echelle,
            round(echelle, 6), round(ratio_ecran, 4),
        )
        if cle in self._rendus:
            self._rendus.move_to_end(cle)
            return self._rendus[cle]
        rendu = self._dessiner_rendu(self.forme(self.bloc(sous_titre, mots)), echelle * ratio_ecran)
        rendu.image.setDevicePixelRatio(ratio_ecran)
        self._rendus[cle] = rendu
        while len(self._rendus) > RENDUS_GARDES:
            self._rendus.popitem(last=False)
        return rendu

    def _dessiner_rendu(self, forme: QPainterPath, echelle: float) -> Rendu:
        style = self.reglages.texte
        ombre = style.ombre
        dx = dy = flou = 0.0
        if ombre.active and ombre.couleur.opacite > 0:
            dx, dy = self.hauteur * ombre.decalage_x_pct / 100, self.hauteur * ombre.decalage_y_pct / 100
            flou = self.hauteur * ombre.flou_pct / 100
        boite = forme.boundingRect()
        if ombre.active:
            boite = boite.united(boite.translated(dx, dy).adjusted(-2 * flou, -2 * flou, 2 * flou, 2 * flou))
        gauche, haut = math.floor(boite.left() * echelle) - 1, math.floor(boite.top() * echelle) - 1
        droite, bas = math.ceil(boite.right() * echelle) + 1, math.ceil(boite.bottom() * echelle) + 1
        largeur, hauteur = droite - gauche, bas - haut

        def peintre_sur(image: QImage, decalage: tuple[float, float] = (0.0, 0.0)) -> QPainter:
            peintre = QPainter(image)
            peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
            peintre.translate(-gauche, -haut)
            peintre.scale(echelle, echelle)
            peintre.translate(*decalage)
            return peintre

        image = _image_vide(largeur, hauteur)
        if ombre.active and ombre.couleur.opacite > 0:
            calque = _image_vide(largeur, hauteur)
            peintre = peintre_sur(calque, (dx, dy))
            peintre.fillPath(forme, qcouleur(ombre.couleur, opaque=True))
            peintre.end()
            calque = flouter(calque, flou * echelle)
            peintre = QPainter(image)
            peintre.setOpacity(ombre.couleur.opacite / 100)
            peintre.drawImage(QPointF(0, 0), calque)
            peintre.end()
        peintre = peintre_sur(image)
        peintre.fillPath(forme, qcouleur(style.couleur))
        peintre.end()
        return Rendu(image, gauche, haut)

    def dessiner(
        self,
        peintre: QPainter,
        origine: QPointF,
        echelle: float,
        sous_titre: SousTitre,
        mots: list[MotAffiche],
        ratio_ecran: float = 1.0,
    ) -> None:
        """Dessine le sous-titre avec le coin haut gauche de la vidéo en `origine` (coordonnées du
        peintre) et `echelle` points du peintre par pixel de vidéo. `ratio_ecran` : pixels réels de
        l'écran par point (écran à 150 % : 1,5), pour un texte net sur tous les écrans."""
        rendu = self.rendu(sous_titre, mots, echelle, ratio_ecran)
        peintre.drawImage(QPointF(origine.x() + rendu.x / ratio_ecran, origine.y() + rendu.y / ratio_ecran), rendu.image)

    def image(self, sous_titre: SousTitre | None, mots: list[MotAffiche]) -> QImage:
        """Image transparente à la taille de la vidéo, avec ce sous-titre (aucun : image vide). C'est
        l'image que l'export de la V3 assemblera, une par image du film."""
        image = _image_vide(self.largeur, self.hauteur)
        if sous_titre is not None:
            peintre = QPainter(image)
            self.dessiner(peintre, QPointF(0, 0), 1.0, sous_titre, mots)
            peintre.end()
        return image
