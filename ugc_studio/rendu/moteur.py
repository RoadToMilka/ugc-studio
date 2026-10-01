"""Moteur de dessin des sous-titres (V2 ; cahier des charges §7.7 et §7.9) : un seul morceau de code
pour l'aperçu et, en V3, pour les exports.

Le principe :
- Le texte devient des **formes** (le contour exact de chaque lettre, QPainterPath) à la taille
  réelle de la vidéo, par exemple 1080 × 1920. L'aperçu les dessine en plus petit ; l'export de la
  V3 les dessinera à 100 %, sur un fond transparent (image()). Une forme réduite garde exactement
  ses proportions : ce que montre l'aperçu est ce qui sera exporté, à la finesse de l'écran près.
- Le **découpage** mesure la largeur des lignes avec ce même moteur (mesure) : « ça tient » veut
  dire « ça tient une fois dessiné », contour et fond compris (lot 4).
- La place de chaque ligne et de chaque mot vient de mise_en_page.py (testé sans interface).
- Ce qui ne bouge pas (un sous-titre entier, avec ses effets) est dessiné une fois par taille
  d'affichage, puis gardé en mémoire : pendant la lecture, l'aperçu ne fait que le recopier.

Police : celle du style, à la taille du texte arrondie au pixel de la vidéo. Inter SemiBold sans
espacement est exactement la mesure de la V1 : un ancien projet garde son découpage. Une police
introuvable (autre ordinateur, police désinstallée) est remplacée par Inter (police_remplacee).

Ordre de dessin (lot 4, §7.4) : ombre, fond, lueur, contour, remplissage. Le contour est dessiné
autour des lettres (un trait deux fois plus épais, sous le remplissage) : elles gardent leur
épaisseur.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QTransform,
)

from ..mise_en_page import Bloc, Metriques, placer
from ..sous_titres import MotAffiche, ReglagesSousTitres, SousTitre, cadre
from ..style_sous_titres import FOND_BLOC, FOND_LIGNE, FOND_MOT, Couleur, StyleTexte
from ..ui.polices import poids_qt, police
from ..ui.theme import Typo
from .polices import POLICE_DE_SECOURS, famille_pour, graisse_proche

RENDUS_GARDES = 96  # sous-titres déjà dessinés gardés en mémoire (toutes tailles d'affichage confondues)
FLOU_MINIMUM = 0.75  # en dessous (en pixels de l'image), le flou ne se verrait pas : il n'est pas calculé


def police_du_texte(style: StyleTexte, taille_px: int) -> tuple[QFont, bool]:
    """Police du style à cette taille (en pixels de la vidéo), et si elle a dû être remplacée par
    Inter (introuvable sur cet ordinateur). Inter passe par ui/polices.py, comme en V1."""
    taille_px = max(1, taille_px)
    remplacee = False
    if style.police == Typo.FAMILLE:
        resultat = police(taille_px, style.graisse)
    else:
        famille = famille_pour(style.police, style.graisse)
        if famille is None:
            remplacee = True
            resultat = police(taille_px, graisse_proche(POLICE_DE_SECOURS, style.graisse))
        else:
            resultat = QFont(famille)
            resultat.setPixelSize(taille_px)
            resultat.setWeight(poids_qt(style.graisse))
    return resultat, remplacee


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


class MesureDuMoteur:
    """Largeur d'une ligne pour le découpage (texte, plus le débord du contour et du fond de chaque
    côté) ; texte() : la largeur du texte seul, pour placer les mots.

    Espace entre les lettres : Qt l'ajoute aussi après la dernière lettre ; il est retiré ici, pour
    qu'une ligne (ou le fond d'un mot) reste centrée sur ses lettres."""

    def __init__(self, metriques: QFontMetricsF, debord: float, espace_lettres: float = 0.0):
        self._metriques = metriques
        self.debord = debord
        self._espace_lettres = espace_lettres
        self._largeurs: dict[str, float] = {}

    def texte(self, texte: str) -> float:
        if texte not in self._largeurs:
            largeur = self._metriques.horizontalAdvance(texte)
            self._largeurs[texte] = largeur - self._espace_lettres if texte else largeur
        return self._largeurs[texte]

    def __call__(self, texte: str) -> float:
        return self.texte(texte) + 2 * self.debord


class Moteur:
    """Moteur de dessin pour une vidéo de `largeur` × `hauteur` pixels et des réglages donnés.
    Un nouveau moteur est créé à chaque changement de réglage (ses mémoires repartent de zéro)."""

    def __init__(self, reglages: ReglagesSousTitres, largeur: int, hauteur: int):
        self.reglages = reglages
        self.largeur, self.hauteur = largeur, hauteur
        style = reglages.texte
        self.zone = cadre(reglages, largeur, hauteur)
        self.taille_px = max(1, round(hauteur * style.taille_pct / 100))
        self.police, self.police_remplacee = police_du_texte(style, self.taille_px)
        espace_lettres = self.px(style.espaces.lettres_pct)
        if espace_lettres:
            self.police.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, espace_lettres)
        if style.espaces.mots_pct:
            self.police.setWordSpacing(self.px(style.espaces.mots_pct))
        metriques = QFontMetricsF(self.police)
        contour = self.px(style.contour.epaisseur_pct) if style.contour.actif else 0.0
        fond = style.fond
        bordure = self.px(fond.bordure_epaisseur_pct) if fond.visible and fond.bordure else 0.0
        debord_x = max(contour, self.px(fond.marge_x_pct) + bordure if fond.visible else 0.0)
        debord_y = max(contour, self.px(fond.marge_y_pct) + bordure if fond.visible else 0.0)
        self.metriques = Metriques(
            metriques.ascent(),
            metriques.descent(),
            metriques.lineSpacing() * style.espaces.interligne_pct / 100,
            debord_x,
            debord_y,
        )
        self.mesure = MesureDuMoteur(metriques, debord_x, espace_lettres)
        self._formes_des_mots: dict[str, QPainterPath] = {}
        self._rendus: OrderedDict[tuple, Rendu] = OrderedDict()

    def px(self, pourcentage: float) -> float:
        """% de la hauteur de la vidéo → pixels de la vidéo."""
        return self.hauteur * pourcentage / 100

    # --- Mise en page --------------------------------------------------------------------------

    def bloc(self, sous_titre: SousTitre, mots: list[MotAffiche]) -> Bloc:
        return placer(sous_titre, mots, self.reglages, self.zone, self.metriques, self.mesure.texte)

    # --- Formes --------------------------------------------------------------------------------

    def _forme_du_mot(self, texte: str) -> QPainterPath:
        """Contour des lettres d'un mot, sa ligne de base en y = 0 et son début en x = 0."""
        if texte not in self._formes_des_mots:
            forme = QPainterPath()
            forme.addText(QPointF(0, 0), self.police, texte)
            self._formes_des_mots[texte] = forme
        return self._formes_des_mots[texte]

    def formes_des_lignes(self, bloc: Bloc) -> list[QPainterPath]:
        """Contour des lettres de chaque ligne, à leur place dans la vidéo."""
        formes = []
        for numero, ligne in enumerate(bloc.lignes):
            forme = QPainterPath()
            forme.setFillRule(Qt.FillRule.WindingFill)  # lettres qui se touchent : jamais de trou
            for mot in bloc.mots:
                if mot.ligne != numero:
                    continue
                transformation = QTransform()
                transformation.translate(mot.x, ligne.base)
                transformation.scale(bloc.echelle, bloc.echelle)  # mot seul rapetissé (§7.3)
                forme.addPath(transformation.map(self._forme_du_mot(mot.texte)))
            formes.append(forme)
        return formes

    def forme(self, bloc: Bloc) -> QPainterPath:
        """Contour de toutes les lettres du sous-titre, à leur place dans la vidéo."""
        forme = QPainterPath()
        forme.setFillRule(Qt.FillRule.WindingFill)
        for ligne in self.formes_des_lignes(bloc):
            forme.addPath(ligne)
        return forme

    def _trait_du_contour(self, forme: QPainterPath) -> QPainterPath | None:
        contour = self.reglages.texte.contour
        if not contour.actif or contour.epaisseur_pct <= 0:
            return None
        traceur = QPainterPathStroker()
        traceur.setWidth(2 * self.px(contour.epaisseur_pct))  # la moitié dépasse : autour des lettres
        nets = contour.angles == "nets"
        traceur.setJoinStyle(Qt.PenJoinStyle.MiterJoin if nets else Qt.PenJoinStyle.RoundJoin)
        traceur.setCapStyle(Qt.PenCapStyle.SquareCap if nets else Qt.PenCapStyle.RoundCap)
        trait = traceur.createStroke(forme)
        trait.setFillRule(Qt.FillRule.WindingFill)
        return trait

    def _rectangles_du_fond(self, bloc: Bloc) -> list[QRectF]:
        fond = self.reglages.texte.fond
        if not fond.visible or not bloc.lignes:
            return []
        marge_x, marge_y = self.px(fond.marge_x_pct), self.px(fond.marge_y_pct)
        haut_lettres = self.metriques.ascendante * bloc.echelle
        bas_lettres = self.metriques.descendante * bloc.echelle

        def boite(gauche: float, droite: float, premiere, derniere) -> QRectF:
            haut = premiere.base - haut_lettres - marge_y
            return QRectF(gauche - marge_x, haut, droite - gauche + 2 * marge_x, derniere.base + bas_lettres + marge_y - haut)

        if fond.mode == FOND_MOT:
            return [boite(m.x, m.x + m.largeur, bloc.lignes[m.ligne], bloc.lignes[m.ligne]) for m in bloc.mots]
        if fond.mode == FOND_LIGNE:
            return [boite(ligne.x, ligne.x + ligne.largeur, ligne, ligne) for ligne in bloc.lignes]
        if fond.mode == FOND_BLOC:
            gauche = min(ligne.x for ligne in bloc.lignes)
            droite = max(ligne.x + ligne.largeur for ligne in bloc.lignes)
            return [boite(gauche, droite, bloc.lignes[0], bloc.lignes[-1])]
        return []

    def forme_du_fond(self, bloc: Bloc) -> QPainterPath | None:
        """Fond derrière chaque mot, chaque ligne, ou un seul bloc (rectangles arrondis)."""
        rectangles = self._rectangles_du_fond(bloc)
        if not rectangles:
            return None
        arrondi = self.px(self.reglages.texte.fond.arrondi_pct)
        forme = QPainterPath()
        forme.setFillRule(Qt.FillRule.WindingFill)
        for rectangle in rectangles:
            rayon = min(arrondi, rectangle.height() / 2, rectangle.width() / 2)
            forme.addRoundedRect(rectangle, rayon, rayon)
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
        rendu = self._dessiner_rendu(self.bloc(sous_titre, mots), echelle * ratio_ecran)
        rendu.image.setDevicePixelRatio(ratio_ecran)
        self._rendus[cle] = rendu
        while len(self._rendus) > RENDUS_GARDES:
            self._rendus.popitem(last=False)
        return rendu

    def _dessiner_rendu(self, bloc: Bloc, echelle: float) -> Rendu:
        style = self.reglages.texte
        ombre, lueur, fond = style.ombre, style.lueur, style.fond
        lignes = self.formes_des_lignes(bloc)
        texte = QPainterPath()
        texte.setFillRule(Qt.FillRule.WindingFill)
        for ligne in lignes:
            texte.addPath(ligne)
        trait = self._trait_du_contour(texte)
        silhouette = QPainterPath(texte)  # le texte et son contour (ombre portée par le texte, lueur)
        if trait is not None:
            silhouette.addPath(trait)
        forme_fond = self.forme_du_fond(bloc)
        bordure = self.px(fond.bordure_epaisseur_pct) if forme_fond is not None and fond.bordure else 0.0

        ombre_visible = ombre.active and ombre.couleur.opacite > 0
        porteuse = forme_fond if ombre_visible and ombre.portee == "fond" and forme_fond is not None else silhouette
        dx, dy, flou = self.px(ombre.decalage_x_pct), self.px(ombre.decalage_y_pct), self.px(ombre.flou_pct)
        halo = self.px(lueur.taille_pct) if lueur.active and lueur.intensite_pct > 0 else 0.0

        boite = silhouette.boundingRect()
        if forme_fond is not None:
            boite = boite.united(forme_fond.boundingRect().adjusted(-bordure, -bordure, bordure, bordure))
        if ombre_visible:
            boite = boite.united(porteuse.boundingRect().translated(dx, dy).adjusted(-2 * flou, -2 * flou, 2 * flou, 2 * flou))
        if halo:
            boite = boite.united(silhouette.boundingRect().adjusted(-2 * halo, -2 * halo, 2 * halo, 2 * halo))
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

        def calque_flou(forme: QPainterPath, couleur: Couleur, rayon: float, decalage=(0.0, 0.0)) -> QImage:
            calque = _image_vide(largeur, hauteur)
            peintre = peintre_sur(calque, decalage)
            peintre.fillPath(forme, qcouleur(couleur, opaque=True))
            peintre.end()
            return flouter(calque, rayon * echelle)

        image = _image_vide(largeur, hauteur)
        if ombre_visible:  # 1. ombre
            calque = calque_flou(porteuse, ombre.couleur, flou, (dx, dy))
            peintre = QPainter(image)
            peintre.setOpacity(ombre.couleur.opacite / 100)
            peintre.drawImage(QPointF(0, 0), calque)
            peintre.end()
        peintre = peintre_sur(image)
        if forme_fond is not None:  # 2. fond (et sa bordure)
            peintre.fillPath(forme_fond, qcouleur(fond.couleur))
            if bordure > 0:
                # Le tour des fonds réunis : deux fonds de ligne qui se touchent n'ont pas de trait entre eux.
                peintre.strokePath(forme_fond.simplified(), QPen(qcouleur(fond.bordure_couleur), bordure))
        peintre.end()
        if halo:  # 3. lueur : la silhouette élargie de la moitié du halo, puis floutée
            traceur = QPainterPathStroker()
            traceur.setWidth(halo)
            traceur.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            traceur.setCapStyle(Qt.PenCapStyle.RoundCap)
            elargie = QPainterPath(silhouette)
            elargie.addPath(traceur.createStroke(silhouette))
            calque = calque_flou(elargie, lueur.couleur, halo)
            peintre = QPainter(image)
            peintre.setOpacity(lueur.couleur.opacite / 100 * lueur.intensite_pct / 100)
            peintre.drawImage(QPointF(0, 0), calque)
            peintre.end()
        peintre = peintre_sur(image)
        if trait is not None:  # 4. contour
            peintre.fillPath(trait, qcouleur(style.contour.couleur))
        for ligne, forme in zip(bloc.lignes, lignes, strict=True):  # 5. remplissage
            peintre.fillPath(forme, self._pinceau(ligne, bloc))
        peintre.end()
        return Rendu(image, gauche, haut)

    def _pinceau(self, ligne, bloc: Bloc):
        """Couleur du texte, ou dégradé de deux couleurs sur la ligne (vertical, horizontal, en biais)."""
        style = self.reglages.texte
        if not style.degrade.actif:
            return qcouleur(style.couleur)
        haut = ligne.base - self.metriques.ascendante * bloc.echelle
        bas = ligne.base + self.metriques.descendante * bloc.echelle
        gauche, droite = ligne.x, ligne.x + ligne.largeur
        if style.degrade.direction == "horizontal":
            degrade = QLinearGradient(QPointF(gauche, haut), QPointF(droite, haut))
        elif style.degrade.direction == "biais":
            degrade = QLinearGradient(QPointF(gauche, haut), QPointF(droite, bas))
        else:
            degrade = QLinearGradient(QPointF(gauche, haut), QPointF(gauche, bas))
        degrade.setColorAt(0, qcouleur(style.couleur))
        degrade.setColorAt(1, qcouleur(style.degrade.couleur))
        return degrade

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
