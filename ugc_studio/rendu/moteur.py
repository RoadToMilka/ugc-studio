"""Moteur de dessin des sous-titres (V2 ; cahier des charges §7.7, §7.9, §7.10 et §7.11) : un seul
morceau de code pour l'aperçu et, en V3, pour les exports.

Le principe :
- Le texte devient des **formes** (le contour exact de chaque lettre, QPainterPath) à la taille
  réelle de la vidéo, par exemple 1080 × 1920. L'aperçu les dessine en plus petit ; l'export de la
  V3 les dessinera à 100 %, sur un fond transparent (image()). Une forme réduite garde exactement
  ses proportions : ce que montre l'aperçu est ce qui sera exporté, à la finesse de l'écran près.
- Le **découpage** mesure la largeur des lignes avec ce même moteur (mesure) : « ça tient » veut
  dire « ça tient une fois dessiné », contour, fond et agrandissement des mots compris.
- La place de chaque ligne et de chaque mot vient de mise_en_page.py (testé sans interface) ; elle
  est calculée une fois pour le sous-titre entier : rien ne bouge pendant la lecture.
- Ce qui ne bouge pas (un sous-titre, avec un mot actif donné et ses effets) est dessiné une fois
  par taille d'affichage, puis gardé en mémoire : pendant la lecture, l'aperçu ne fait que le
  recopier. Seul le fond qui glisse d'un mot à l'autre (mot actif) est redessiné à chaque image.
- À chaque instant, le sous-titre est **une seule image transparente**, posée d'un coup sur la
  vidéo (aperçu) ou sur le fond transparent (export) : aperçu à 100 % et export restent identiques
  au pixel près, même quand quelque chose bouge (poser plusieurs couches l'une après l'autre sur la
  vidéo arrondirait autrement les bords et les transparences d'un ou deux niveaux sur 255).

Police : celle du style, à la taille du texte arrondie au pixel de la vidéo. Inter SemiBold sans
espacement est exactement la mesure de la V1 : un ancien projet garde son découpage. Une police
introuvable (autre ordinateur, police désinstallée) est remplacée par Inter (police_remplacee).

Ordre de dessin (§7.4) : ombre, fond, lueur, contour, remplissage (puis soulignement). Le contour est
dessiné autour des lettres (un trait deux fois plus épais, sous le remplissage) : elles gardent
leur épaisseur.

États des mots (lot 5, §7.11) : à un instant donné, le mot actif est le dernier mot du sous-titre
déjà commencé (avance de l'allumage comprise) ; ceux d'avant sont « déjà dits », ceux d'après « à
venir » ; un mot accentué du script prend l'état « Accentués » (sauf quand il est actif). Chaque
état a son apparence (comme le texte, sauf ce qui est réglé). Les mots d'un même état sont dessinés
ensemble, puis posés avec l'opacité de cet état ; le mot actif en dernier (il peut être agrandi).

Animations (lot 6, §7.12) : pendant l'animation du mot qui devient actif, ce mot est dessiné à part
(une fois, gardé en mémoire), puis posé à chaque image avec sa taille, son opacité et son décalage
du moment ; le reste du sous-titre ne change pas. Le retour en fondu du mot précédent pose son
apparence de mot actif par-dessus, de moins en moins visible. L'apparition et la disparition du
sous-titre entier agissent sur l'image entière de l'instant (opacité, taille autour du centre du
bloc, glissement). Comme toujours, tout cela est assemblé en une seule image avant d'être posé.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
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

from ..mise_en_page import Bloc, Metriques, MotPlace, placer
from ..sous_titres import MotAffiche, ReglagesSousTitres, SousTitre, cadre
from ..style_sous_titres import (
    ACCENTUES,
    ACTIF,
    ANIM_AUCUNE,
    ANIM_FONDU,
    ANIM_POP,
    ANIM_ZOOM,
    A_VENIR,
    DITS,
    FOND_LIGNE,
    FOND_MOT,
    GLISSEMENT_PCT,
    RETOUR_FONDU,
    SOUS_TITRE_BAS,
    SOUS_TITRE_HAUT,
    Contour,
    Couleur,
    Degrade,
    EtatMot,
    FondMot,
    Lueur,
    Soulignement,
    StyleTexte,
    courbe,
)
from ..ui.polices import poids_qt, police
from ..ui.theme import Typo
from .polices import POLICE_DE_SECOURS, famille_pour, graisse_proche

RENDUS_GARDES = 48  # sous-titres déjà dessinés gardés en mémoire (tailles d'affichage et mots actifs confondus)
FLOU_MINIMUM = 0.75  # en dessous (en pixels de l'image), le flou ne se verrait pas : il n'est pas calculé
ORDRE_DES_ETATS = (A_VENIR, DITS, ACCENTUES, ACTIF)  # le mot actif est dessiné en dernier, par-dessus


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


# Finesse du dessin (V3, lot 1) : 8 bits par couleur pour l'aperçu (le format de l'écran), 16 bits
# pour les exports. En 16 bits, une ombre ou une lueur très transparente garde des nuances douces :
# convertie ensuite en transparence « droite » (non prémultipliée) puis en 10 bits pour le ProRes,
# elle ne fait pas d'« escaliers ». À 8 bits près, les deux dessins sont identiques.
FORMATS_DU_DESSIN = {8: QImage.Format.Format_ARGB32_Premultiplied, 16: QImage.Format.Format_RGBA64_Premultiplied}


def _image_vide(largeur: int, hauteur: int, format_image: QImage.Format = QImage.Format.Format_ARGB32_Premultiplied) -> QImage:
    image = QImage(max(1, largeur), max(1, hauteur), format_image)
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


def _douce(avancee: float) -> float:
    """Courbe douce (ralentit à l'arrivée) pour le fond qui glisse."""
    avancee = min(max(avancee, 0.0), 1.0)
    return 1 - (1 - avancee) ** 3


def _autour(centre_x: float, centre_y: float, taille: float, decalage: float) -> QTransform:
    """Agrandissement `taille` autour du point (centre_x, centre_y), puis décalage vertical."""
    transformation = QTransform()
    transformation.translate(centre_x, centre_y + decalage)
    transformation.scale(taille, taille)
    transformation.translate(-centre_x, -centre_y)
    return transformation


def _assembler(couches: list[tuple[QImage, int, int, float, QTransform]]) -> tuple[QImage, int, int]:
    """Des images posées l'une sur l'autre (chacune à sa place x, y, avec son opacité et sa
    transformation, en pixels réels par rapport au coin de la vidéo) → une seule image transparente,
    juste assez grande, et la place de son coin."""
    boite = QRectF()
    for image, x, y, _opacite, transformation in couches:
        boite = boite.united(transformation.mapRect(QRectF(x, y, image.width(), image.height())))
    gauche, haut = math.floor(boite.left()) - 1, math.floor(boite.top()) - 1
    resultat = _image_vide(math.ceil(boite.right()) + 1 - gauche, math.ceil(boite.bottom()) + 1 - haut, couches[0][0].format())
    peintre = QPainter(resultat)
    peintre.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    for image, x, y, opacite, transformation in couches:
        peintre.resetTransform()
        peintre.translate(-gauche, -haut)
        peintre.setTransform(transformation, True)
        peintre.setOpacity(opacite)
        # Pixel pour pixel (la finesse d'écran que l'image porte ne la réduit pas).
        peintre.drawImage(QRectF(x, y, image.width(), image.height()), image, QRectF(image.rect()))
    peintre.end()
    return resultat, gauche, haut


@dataclass(frozen=True)
class Rendu:
    """Un sous-titre dessiné à une taille d'affichage : son image et sa place, en pixels de
    l'image par rapport au coin haut gauche de la vidéo (nombres entiers : l'image tombe pile sur
    les pixels, l'aperçu à 100 % et l'export sont donc identiques).

    `image` : le sous-titre complet, fond du mot actif compris (à sa place d'arrivée).
    `dessous` et `dessus` : quand le fond du mot actif peut glisser, ce qui passe sous ce fond
    (ombre, fonds) et ce qui passe dessus (les lettres) ; pendant le glissement, l'image de chaque
    instant est refaite avec eux (_composer). Sinon None."""

    image: QImage
    x: int
    y: int
    dessous: QImage | None = None
    dessus: QImage | None = None


@dataclass(frozen=True)
class Instant:
    """Ce que montre un sous-titre à un instant : le mot actif (sa place dans les mots affichés ;
    None : aucun) et depuis combien de temps il l'est (pour le fond qui glisse)."""

    actif: int | None = None
    depuis_s: float = 0.0


@dataclass(frozen=True)
class Apparence:
    """Apparence d'un état des mots : celle du texte, sauf ce que l'état règle (onglet Mots)."""

    visible: bool
    opacite: float  # 0 à 1
    couleur: Couleur
    degrade: Degrade
    contour: Contour
    lueur: Lueur
    fond: FondMot | None
    soulignement: Soulignement | None
    echelle: float  # agrandissement autour du centre du mot
    decalage_pct: float  # vers le bas, en % de la hauteur de la vidéo


def apparence(texte: StyleTexte, etat: EtatMot) -> Apparence:
    def ou(valeur, defaut):
        return defaut if valeur is None else valeur

    return Apparence(
        etat.visible,
        etat.opacite,
        ou(etat.couleur, texte.couleur),
        ou(etat.degrade, texte.degrade),
        ou(etat.contour, texte.contour),
        ou(etat.lueur, texte.lueur),
        etat.fond,
        etat.soulignement,
        etat.echelle,
        etat.decalage_pct,
    )


class MesureDuMoteur:
    """Largeur d'une ligne pour le découpage (texte, plus le débord du contour et des fonds de chaque
    côté, plus l'agrandissement du plus large mot) ; texte() : la largeur du texte seul, pour
    placer les mots.

    Espace entre les lettres : Qt l'ajoute aussi après la dernière lettre ; il est retiré ici, pour
    qu'une ligne (ou le fond d'un mot) reste centrée sur ses lettres."""

    def __init__(self, metriques: QFontMetricsF, debord: float, espace_lettres: float = 0.0, croissance: float = 0.0):
        self._metriques = metriques
        self.debord = debord
        self._espace_lettres = espace_lettres
        self._croissance = croissance  # agrandissement d'un mot (états des mots), en plus de sa taille
        self._largeurs: dict[str, float] = {}

    def texte(self, texte: str) -> float:
        if texte not in self._largeurs:
            largeur = self._metriques.horizontalAdvance(texte)
            self._largeurs[texte] = largeur - self._espace_lettres if texte else largeur
        return self._largeurs[texte]

    def __call__(self, texte: str) -> float:
        largeur = self.texte(texte) + 2 * self.debord
        if self._croissance > 0 and texte.split():
            # Un mot agrandi (autour de son centre) dépasse de chaque côté : au plus le plus large.
            largeur += self._croissance * max(self.texte(mot) for mot in texte.split())
        return largeur


@dataclass
class _MotDessine:
    """Un mot prêt à dessiner : son état, ses formes (déjà à leur place, agrandissement compris) et
    sa boîte (avant agrandissement)."""

    place: MotPlace
    etat: str
    apparence: Apparence
    transformation: QTransform  # agrandissement et décalage de l'état
    lettres: QPainterPath
    trait: QPainterPath | None
    boite: QRectF


class Moteur:
    """Moteur de dessin pour une vidéo de `largeur` × `hauteur` pixels et des réglages donnés.
    Un nouveau moteur est créé à chaque changement de réglage (ses mémoires repartent de zéro).
    `profondeur` : 8 bits par couleur (aperçu) ou 16 bits (exports, V3)."""

    def __init__(self, reglages: ReglagesSousTitres, largeur: int, hauteur: int, profondeur: int = 8):
        self.reglages = reglages
        self.largeur, self.hauteur = largeur, hauteur
        self.format_image = FORMATS_DU_DESSIN[profondeur]
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
        self.apparences = {nom: apparence(style, reglages.mots.etat(nom)) for nom in ORDRE_DES_ETATS}
        utilisees = [
            a for nom, a in self.apparences.items() if a.visible and (nom != ACCENTUES or reglages.mots.accentues_actifs)
        ] or [self.apparences[A_VENIR]]
        animation = reglages.animations.mot
        profil = animation.profil() if animation.active else None
        echelles = [a.echelle for a in utilisees]
        if profil is not None and self.apparences[ACTIF].visible:
            echelles.append(self.apparences[ACTIF].echelle * profil.taille_max / 100)
        croissance = max(0.0, max(echelles) - 1)
        contour = max((self.px(a.contour.epaisseur_pct) if a.contour.actif else 0.0) * a.echelle for a in utilisees)
        fond = style.fond
        bordure = self.px(fond.bordure_epaisseur_pct) if fond.visible and fond.bordure else 0.0
        fonds_x = [self.px(a.fond.marge_x_pct) * a.echelle for a in utilisees if a.fond is not None]
        fonds_y = [self.px(a.fond.marge_y_pct) * a.echelle for a in utilisees if a.fond is not None]
        soulignes = [
            self.px(a.soulignement.distance_pct + a.soulignement.epaisseur_pct) - metriques.descent()
            for a in utilisees
            if a.soulignement is not None
        ]
        debord_x = max([contour, self.px(fond.marge_x_pct) + bordure if fond.visible else 0.0, *fonds_x])
        debord_y = max([contour, self.px(fond.marge_y_pct) + bordure if fond.visible else 0.0, *fonds_y, *soulignes])
        # Un mot agrandi dépasse en haut et en bas ; un décalage vertical aussi.
        debord_y += croissance * (metriques.ascent() + metriques.descent()) / 2
        debord_y += max([abs(self.px(a.decalage_pct)) for a in utilisees] + [abs(self.px(profil.decalage_depart)) if profil else 0.0])
        self.metriques = Metriques(
            metriques.ascent(),
            metriques.descent(),
            metriques.lineSpacing() * style.espaces.interligne_pct / 100,
            debord_x,
            debord_y,
            croissance,
        )
        self.mesure = MesureDuMoteur(metriques, debord_x, espace_lettres, croissance)
        self._formes_des_mots: dict[str, QPainterPath] = {}
        self._rendus: OrderedDict[tuple, Rendu] = OrderedDict()

    def px(self, pourcentage: float) -> float:
        """% de la hauteur de la vidéo → pixels de la vidéo."""
        return self.hauteur * pourcentage / 100

    def _vide(self, largeur: int, hauteur: int) -> QImage:
        """Image transparente, à la finesse du moteur (8 ou 16 bits par couleur)."""
        return _image_vide(largeur, hauteur, self.format_image)

    # --- Mise en page --------------------------------------------------------------------------

    def bloc(self, sous_titre: SousTitre, mots: list[MotAffiche]) -> Bloc:
        return placer(sous_titre, mots, self.reglages, self.zone, self.metriques, self.mesure.texte)

    # --- Mot actif et états des mots (lot 5) -----------------------------------------------------

    def instant(self, sous_titre: SousTitre, mots: list[MotAffiche], temps: float | None) -> Instant:
        """Le mot actif à ce moment de la vidéo : le dernier mot du sous-titre déjà commencé (avance
        de l'allumage comprise). Petit silence entre deux mots : le dernier dit reste allumé ; avant
        le premier mot, aucun. Sans changement d'état des mots ni animation du mot actif, ou sans
        temps : aucun."""
        animations = self.reglages.animations
        besoin = not self.reglages.mots.fixe or animations.mot.active or animations.retour == RETOUR_FONDU
        if temps is None or not besoin:
            return Instant()
        moment = temps + self.reglages.mots.avance_ms / 1000
        actif = None
        for index in range(sous_titre.premier_mot, min(sous_titre.dernier_mot, len(mots))):
            if mots[index].debut <= moment + 1e-6:
                actif = index
            else:
                break
        return Instant(actif, moment - mots[actif].debut if actif is not None else 0.0)

    def etat_du_mot(self, index: int, mots: list[MotAffiche], actif: int | None) -> str:
        if actif is not None and index == actif:
            return ACTIF
        if self.reglages.mots.accentues_actifs and mots[index].accentue:
            return ACCENTUES
        if actif is not None and index < actif:
            return DITS
        return A_VENIR

    # --- Formes --------------------------------------------------------------------------------

    def _forme_du_mot(self, texte: str) -> QPainterPath:
        """Contour des lettres d'un mot, sa ligne de base en y = 0 et son début en x = 0."""
        if texte not in self._formes_des_mots:
            forme = QPainterPath()
            forme.addText(QPointF(0, 0), self.police, texte)
            self._formes_des_mots[texte] = forme
        return self._formes_des_mots[texte]

    def _boite_du_mot(self, place: MotPlace, bloc: Bloc) -> QRectF:
        """Boîte d'un mot : sa largeur, du haut des lettres (accents compris) au bas des jambages."""
        base = bloc.lignes[place.ligne].base
        haut = base - self.metriques.ascendante * bloc.echelle
        return QRectF(place.x, haut, place.largeur, (self.metriques.ascendante + self.metriques.descendante) * bloc.echelle)

    def _transformation(self, boite: QRectF, aspect: Apparence) -> QTransform:
        """Agrandissement autour du centre du mot, puis décalage vertical."""
        transformation = QTransform()
        decalage = self.px(aspect.decalage_pct)
        if aspect.echelle == 1 and not decalage:
            return transformation
        centre = boite.center()
        transformation.translate(centre.x(), centre.y() + decalage)
        transformation.scale(aspect.echelle, aspect.echelle)
        transformation.translate(-centre.x(), -centre.y())
        return transformation

    def _trait(self, forme: QPainterPath, contour: Contour) -> QPainterPath | None:
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

    def _mots_dessines(self, bloc: Bloc, mots: list[MotAffiche], actif: int | None) -> list[_MotDessine]:
        resultat = []
        for place in bloc.mots:
            etat = self.etat_du_mot(place.index, mots, actif)
            aspect = self.apparences[etat]
            boite = self._boite_du_mot(place, bloc)
            transformation = self._transformation(boite, aspect)
            position = QTransform()
            position.translate(place.x, bloc.lignes[place.ligne].base)
            position.scale(bloc.echelle, bloc.echelle)  # mot seul rapetissé (§7.3)
            lettres = position.map(self._forme_du_mot(place.texte))
            lettres.setFillRule(Qt.FillRule.WindingFill)  # lettres qui se touchent : jamais de trou
            trait = self._trait(lettres, aspect.contour)
            resultat.append(
                _MotDessine(
                    place, etat, aspect, transformation, transformation.map(lettres),
                    transformation.map(trait) if trait is not None else None, boite,
                )
            )
        return resultat

    def formes_des_lignes(self, bloc: Bloc) -> list[QPainterPath]:
        """Contour des lettres de chaque ligne, à leur place dans la vidéo (sans état des mots)."""
        formes = []
        for numero, ligne in enumerate(bloc.lignes):
            forme = QPainterPath()
            forme.setFillRule(Qt.FillRule.WindingFill)
            for mot in bloc.mots:
                if mot.ligne != numero:
                    continue
                transformation = QTransform()
                transformation.translate(mot.x, ligne.base)
                transformation.scale(bloc.echelle, bloc.echelle)
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

    def _rectangles_du_fond(self, bloc: Bloc) -> list[QRectF]:
        """Fond de l'onglet Texte derrière chaque mot, chaque ligne ou tout le bloc (avant
        l'agrandissement d'un mot par son état)."""
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
        gauche = min(ligne.x for ligne in bloc.lignes)
        droite = max(ligne.x + ligne.largeur for ligne in bloc.lignes)
        return [boite(gauche, droite, bloc.lignes[0], bloc.lignes[-1])]

    def _arrondis(self, rectangles: list[QRectF], arrondi_pct: float, transformation: QTransform | None = None) -> QPainterPath:
        arrondi = self.px(arrondi_pct)
        forme = QPainterPath()
        forme.setFillRule(Qt.FillRule.WindingFill)
        for rectangle in rectangles:
            rayon = min(arrondi, rectangle.height() / 2, rectangle.width() / 2)
            forme.addRoundedRect(rectangle, rayon, rayon)
        return transformation.map(forme) if transformation is not None else forme

    def forme_du_fond(self, bloc: Bloc) -> QPainterPath | None:
        """Fond de l'onglet Texte derrière chaque ligne ou tout le bloc (rectangles arrondis). Celui
        « derrière chaque mot » est dessiné mot par mot (_fond_texte_du_mot) : il suit l'état du mot."""
        if self.reglages.texte.fond.mode == FOND_MOT:
            return None
        rectangles = self._rectangles_du_fond(bloc)
        return self._arrondis(rectangles, self.reglages.texte.fond.arrondi_pct) if rectangles else None

    def _fond_texte_du_mot(self, mot: _MotDessine) -> QPainterPath:
        """Fond de l'onglet Texte « derrière chaque mot », pour ce mot (il suit son agrandissement)."""
        fond = self.reglages.texte.fond
        marge_x, marge_y = self.px(fond.marge_x_pct), self.px(fond.marge_y_pct)
        return self._arrondis([mot.boite.adjusted(-marge_x, -marge_y, marge_x, marge_y)], fond.arrondi_pct, mot.transformation)

    def _fond_d_etat(self, boite: QRectF, fond: FondMot) -> QRectF:
        marge_x, marge_y = self.px(fond.marge_x_pct), self.px(fond.marge_y_pct)
        return boite.adjusted(-marge_x, -marge_y, marge_x, marge_y)

    # --- Dessin ---------------------------------------------------------------------------------

    def rendu(
        self,
        sous_titre: SousTitre,
        mots: list[MotAffiche],
        echelle: float,
        ratio_ecran: float = 1.0,
        actif: int | None = None,
        sans: int | None = None,
        seulement: int | None = None,
    ) -> Rendu:
        """Le sous-titre dessiné à `echelle` points par pixel de vidéo, sur un écran qui a
        `ratio_ecran` pixels réels par point, avec ce mot actif (gardé en mémoire). `sans` : sans ce
        mot (posé à part pendant son animation) ; `seulement` : ce mot seul, avec l'apparence du mot
        actif (pour son animation, ou son retour en fondu)."""
        cle = (
            sous_titre.premier_mot, sous_titre.dernier_mot, tuple(sous_titre.lignes), sous_titre.echelle,
            round(echelle, 6), round(ratio_ecran, 4), actif, sans, seulement,
        )
        if cle in self._rendus:
            self._rendus.move_to_end(cle)
            return self._rendus[cle]
        rendu = self._dessiner_rendu(self.bloc(sous_titre, mots), mots, echelle * ratio_ecran, actif, sans, seulement)
        # Seule l'image finale connaît l'écran ; `dessous` et `dessus` restent en pixels réels, pour
        # refaire l'image d'un instant (_composer).
        rendu.image.setDevicePixelRatio(ratio_ecran)
        self._rendus[cle] = rendu
        while len(self._rendus) > RENDUS_GARDES:
            self._rendus.popitem(last=False)
        return rendu

    def _dessiner_rendu(
        self,
        bloc: Bloc,
        mots: list[MotAffiche],
        echelle: float,
        actif: int | None,
        sans: int | None = None,
        seulement: int | None = None,
    ) -> Rendu:
        style = self.reglages.texte
        ombre, fond = style.ombre, style.fond
        dessines = [
            mot
            for mot in self._mots_dessines(bloc, mots, seulement if seulement is not None else actif)
            if mot.place.index != sans and (seulement is None or mot.place.index == seulement)
        ]
        visibles = [mot for mot in dessines if mot.apparence.visible]
        groupes = {nom: [mot for mot in visibles if mot.etat == nom] for nom in ORDRE_DES_ETATS}
        forme_fond = self.forme_du_fond(bloc) if seulement is None else None  # fond des lignes : pas sur un mot seul
        bordure = self.px(fond.bordure_epaisseur_pct) if fond.visible and fond.bordure else 0.0
        # Fond surligné du mot actif : posé entre ce qui passe dessous et les lettres (_composer) ; il
        # compte dans la boîte de l'image, depuis le mot précédent s'il peut en glisser. Il reste avec
        # le sous-titre quand le mot est posé à part (`sans`) : il ne s'anime pas avec lui.
        fond_actif = self._fond_actif(bloc, actif) if actif is not None and seulement is None else None
        glisse_possible = fond_actif is not None and self._depart_du_glissement(bloc, actif) is not None

        def reunies(formes) -> QPainterPath:
            """Formes réunies : là où elles se touchent, pas de double opacité."""
            forme = QPainterPath()
            forme.setFillRule(Qt.FillRule.WindingFill)
            for une in formes:
                if une is not None:
                    forme.addPath(une)
            return forme

        silhouettes = {
            nom: reunies([forme for mot in liste for forme in (mot.lettres, mot.trait)]) for nom, liste in groupes.items() if liste
        }
        # Fond « derrière chaque mot » de l'onglet Texte, et fonds surlignés des états (sauf celui du
        # mot actif, dessiné à part : il peut glisser), réunis par état.
        fonds_texte = {
            nom: reunies(self._fond_texte_du_mot(mot) for mot in liste)
            for nom, liste in groupes.items()
            if liste and fond.mode == FOND_MOT
        }
        fonds_etats = {
            nom: reunies(
                self._arrondis([self._fond_d_etat(mot.boite, mot.apparence.fond)], mot.apparence.fond.arrondi_pct, mot.transformation)
                for mot in liste
            )
            for nom, liste in groupes.items()
            if liste and nom != ACTIF and self.apparences[nom].fond is not None
        }

        ombre_visible = ombre.active and ombre.couleur.opacite > 0
        par_le_fond = ombre.portee == "fond" and (forme_fond is not None or bool(fonds_texte))
        dx, dy, flou = self.px(ombre.decalage_x_pct), self.px(ombre.decalage_y_pct), self.px(ombre.flou_pct)
        halos = {
            nom: self.px(self.apparences[nom].lueur.taille_pct)
            for nom in silhouettes
            if self.apparences[nom].lueur.active and self.apparences[nom].lueur.intensite_pct > 0
        }

        # Boîte de l'image : tout ce qui sera dessiné, flous compris.
        boite = QRectF()
        for forme in silhouettes.values():
            boite = boite.united(forme.boundingRect())
        if forme_fond is not None:
            boite = boite.united(forme_fond.boundingRect().adjusted(-bordure, -bordure, bordure, bordure))
        for forme in [*fonds_texte.values(), *fonds_etats.values()]:
            boite = boite.united(forme.boundingRect().adjusted(-bordure, -bordure, bordure, bordure))
        for mot in visibles:
            if mot.apparence.soulignement is not None:
                boite = boite.united(mot.transformation.mapRect(self._rect_du_soulignement(mot)))
        if fond_actif is not None:
            boite = boite.united(fond_actif.boundingRect())
            if glisse_possible:  # pendant le glissement, le fond reste entre ses places de départ et d'arrivée
                boite = boite.united(self._fond_actif(bloc, actif, 0.0).boundingRect())
        if ombre_visible and not boite.isEmpty():
            boite = boite.united(boite.translated(dx, dy).adjusted(-2 * flou, -2 * flou, 2 * flou, 2 * flou))
        for nom, halo in halos.items():
            boite = boite.united(silhouettes[nom].boundingRect().adjusted(-2 * halo, -2 * halo, 2 * halo, 2 * halo))
        if boite.isEmpty():  # aucun mot visible (ex. tous « à venir », invisibles) ni fond
            boite = QRectF(bloc.x, bloc.y, max(1.0, bloc.largeur), max(1.0, bloc.hauteur))
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

        def poser(cible: QImage, calque: QImage, opacite: float) -> None:
            peintre = QPainter(cible)
            peintre.setOpacity(opacite)
            peintre.drawImage(QPointF(0, 0), calque)
            peintre.end()

        dessous = self._vide(largeur, hauteur)
        image = self._vide(largeur, hauteur) if fond_actif is not None else dessous

        # 1. Ombre : celle des lettres (et de leur contour) des mots visibles, ou celle des fonds ;
        #    un état à moitié transparent a une ombre à moitié transparente.
        if ombre_visible:
            calque = self._vide(largeur, hauteur)
            peintre = peintre_sur(calque, (dx, dy))
            couleur = qcouleur(ombre.couleur, opaque=True)
            if par_le_fond and forme_fond is not None:
                peintre.fillPath(forme_fond, couleur)
            for nom in silhouettes:
                teinte = QColor(couleur)
                teinte.setAlphaF(self.apparences[nom].opacite)
                forme = fonds_texte.get(nom) if par_le_fond else silhouettes[nom]
                if forme is not None:
                    peintre.fillPath(forme, teinte)
            peintre.end()
            poser(dessous, flouter(calque, flou * echelle), ombre.couleur.opacite / 100)

        # 2. Fonds : celui de l'onglet Texte (lignes, bloc ou mots), puis ceux des états (sauf le mot
        #    actif, dont le fond est posé à part, au-dessus : il peut glisser).
        peintre = peintre_sur(dessous)
        if forme_fond is not None:
            peintre.fillPath(forme_fond, qcouleur(fond.couleur))
            if bordure > 0:
                # Le tour des fonds réunis : deux fonds de ligne qui se touchent n'ont pas de trait entre eux.
                peintre.strokePath(forme_fond.simplified(), QPen(qcouleur(fond.bordure_couleur), bordure))
        for nom in ORDRE_DES_ETATS:
            peintre.setOpacity(self.apparences[nom].opacite)
            if nom in fonds_texte:
                peintre.fillPath(fonds_texte[nom], qcouleur(fond.couleur))
                if bordure > 0:
                    peintre.strokePath(fonds_texte[nom].simplified(), QPen(qcouleur(fond.bordure_couleur), bordure))
            if nom in fonds_etats:
                peintre.fillPath(fonds_etats[nom], qcouleur(self.apparences[nom].fond.couleur))
        peintre.end()

        # 3 à 5. Chaque état : lueur, contour, remplissage, soulignement ; posé avec son opacité.
        for nom in ORDRE_DES_ETATS:
            liste = groupes.get(nom) or []
            if not liste:
                continue
            aspect = self.apparences[nom]
            direct = aspect.opacite >= 1  # opaque : dessiné directement, sans calque intermédiaire
            calque = image if direct else self._vide(largeur, hauteur)
            if nom in halos:
                traceur = QPainterPathStroker()
                traceur.setWidth(halos[nom])
                traceur.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                traceur.setCapStyle(Qt.PenCapStyle.RoundCap)
                elargie = QPainterPath(silhouettes[nom])
                elargie.addPath(traceur.createStroke(silhouettes[nom]))
                lumiere = self._vide(largeur, hauteur)
                peintre = peintre_sur(lumiere)
                peintre.fillPath(elargie, qcouleur(aspect.lueur.couleur, opaque=True))
                peintre.end()
                poser(calque, flouter(lumiere, halos[nom] * echelle), aspect.lueur.couleur.opacite / 100 * aspect.lueur.intensite_pct / 100)
            peintre = peintre_sur(calque)
            for mot in liste:
                if mot.trait is not None:
                    peintre.fillPath(mot.trait, qcouleur(aspect.contour.couleur))
            for mot in liste:
                peintre.fillPath(mot.lettres, self._pinceau(bloc.lignes[mot.place.ligne], bloc, aspect, mot.transformation))
            for mot in liste:
                if aspect.soulignement is not None:
                    trait = QPainterPath()
                    trait.addRect(self._rect_du_soulignement(mot))
                    peintre.fillPath(mot.transformation.map(trait), qcouleur(aspect.soulignement.couleur))
            peintre.end()
            if not direct:
                poser(image, calque, aspect.opacite)
        if fond_actif is None:
            return Rendu(image, gauche, haut)
        # Le sous-titre complet, fond du mot actif à sa place d'arrivée ; les deux couches restent
        # en mémoire seulement si ce fond peut glisser (images refaites pendant le glissement).
        complet = self._composer(dessous, image, fond_actif, gauche, haut, echelle)
        if glisse_possible:
            return Rendu(complet, gauche, haut, dessous, image)
        return Rendu(complet, gauche, haut)

    def _rect_du_soulignement(self, mot: _MotDessine) -> QRectF:
        souligne = mot.apparence.soulignement
        base = mot.boite.top() + self.metriques.ascendante * (mot.boite.height() / (self.metriques.ascendante + self.metriques.descendante))
        return QRectF(mot.boite.left(), base + self.px(souligne.distance_pct), mot.boite.width(), self.px(souligne.epaisseur_pct))

    def _pinceau(self, ligne, bloc: Bloc, aspect: Apparence, transformation: QTransform):
        """Couleur du texte, ou dégradé de deux couleurs sur la ligne (vertical, horizontal, en biais).
        Un mot agrandi garde le dégradé de sa ligne, agrandi avec lui."""
        if not aspect.degrade.actif:
            return qcouleur(aspect.couleur)
        haut = ligne.base - self.metriques.ascendante * bloc.echelle
        bas = ligne.base + self.metriques.descendante * bloc.echelle
        gauche, droite = ligne.x, ligne.x + ligne.largeur
        if aspect.degrade.direction == "horizontal":
            degrade = QLinearGradient(QPointF(gauche, haut), QPointF(droite, haut))
        elif aspect.degrade.direction == "biais":
            degrade = QLinearGradient(QPointF(gauche, haut), QPointF(droite, bas))
        else:
            degrade = QLinearGradient(QPointF(gauche, haut), QPointF(gauche, bas))
        degrade.setColorAt(0, qcouleur(aspect.couleur))
        degrade.setColorAt(1, qcouleur(aspect.degrade.couleur))
        pinceau = QBrush(degrade)
        if not transformation.isIdentity():
            pinceau.setTransform(transformation)
        return pinceau

    # --- Animations (lot 6) ----------------------------------------------------------------------

    def _avancee_du_mot(self, instant: Instant) -> float | None:
        """Avancée (0 à 1) de l'animation du mot actif, ou None (pas d'animation en cours)."""
        animation = self.reglages.animations.mot
        if instant.actif is None or not animation.active or not self.apparences[ACTIF].visible:
            return None
        duree = animation.duree_ms / 1000
        return instant.depuis_s / duree if instant.depuis_s < duree else None

    def _retour(self, sous_titre: SousTitre, instant: Instant) -> tuple[int, float] | None:
        """Retour en fondu du mot précédent à « déjà dit » : (son index, ce qu'il garde de son
        apparence de mot actif, de 1 à 0), ou None."""
        animations = self.reglages.animations
        if animations.retour != RETOUR_FONDU or animations.retour_duree_ms <= 0 or instant.actif is None:
            return None
        precedent = instant.actif - 1
        duree = animations.retour_duree_ms / 1000
        if precedent < sous_titre.premier_mot or instant.depuis_s >= duree:
            return None
        return precedent, 1 - instant.depuis_s / duree

    def valeurs_du_mot(self, avancee: float) -> tuple[float, float, float]:
        """Taille (facteur), opacité (0 à 1) et décalage (en pixels de la vidéo, vers le bas) du mot
        actif à cette avancée de son animation."""
        profil = self.reglages.animations.mot.profil()
        t = courbe(profil.courbe, avancee)
        if profil.sommet not in (profil.depart, profil.arrivee) or profil.sommet > max(profil.depart, profil.arrivee):
            # Deux temps : jusqu'au sommet, puis jusqu'à l'arrivée.
            if avancee < 0.5:
                taille = profil.depart + (profil.sommet - profil.depart) * courbe(profil.courbe, avancee * 2)
            else:
                taille = profil.sommet + (profil.arrivee - profil.sommet) * courbe(profil.courbe, (avancee - 0.5) * 2)
        else:
            taille = profil.depart + (profil.arrivee - profil.depart) * t
        opacite = (profil.opacite_depart + (100 - profil.opacite_depart) * min(max(t, 0.0), 1.0)) / 100
        decalage = self.px(profil.decalage_depart) * (1 - t)
        return max(taille, 0.0) / 100, opacite, decalage

    def _sous_titre_anime(self, sous_titre: SousTitre, temps: float | None) -> tuple[float, float, float] | None:
        """Apparition ou disparition du sous-titre entier à ce moment : (taille, opacité, décalage en
        pixels de la vidéo), ou None. Elles restent dans les temps du sous-titre."""
        animations = self.reglages.animations
        if temps is None:
            return None
        duree_totale = max(sous_titre.fin - sous_titre.debut, 1e-3)
        depuis, reste = temps - sous_titre.debut, sous_titre.fin - temps
        app = min(animations.apparition_duree_ms / 1000, duree_totale / 2)
        dis = min(animations.disparition_duree_ms / 1000, duree_totale / 2)
        if animations.apparition != ANIM_AUCUNE and app > 0 and 0 <= depuis < app:
            return self._effet_du_sous_titre(animations.apparition, depuis / app, entree=True)
        if animations.disparition != ANIM_AUCUNE and dis > 0 and 0 <= reste < dis:
            return self._effet_du_sous_titre(animations.disparition, reste / dis, entree=False)
        return None

    def _effet_du_sous_titre(self, nom: str, avancee: float, entree: bool) -> tuple[float, float, float]:
        """`avancee` va de 0 (invisible) à 1 (sous-titre normal) : à l'envers pour une disparition."""
        t = courbe("douce", avancee)
        glissement = self.px(GLISSEMENT_PCT) * (1 - t)
        if nom == ANIM_FONDU:
            return 1.0, t, 0.0
        if nom == ANIM_POP:
            taille = 0.9 + 0.16 * t if avancee < 0.6 else 1.06 - 0.06 * courbe("douce", (avancee - 0.6) / 0.4)
            return taille, min(1.0, avancee * 2), 0.0
        if nom == ANIM_ZOOM:
            return 0.85 + 0.15 * t, t, 0.0
        if nom == SOUS_TITRE_HAUT:  # entre par le bas en montant ; sort par le haut
            return 1.0, t, glissement if entree else -glissement
        if nom == SOUS_TITRE_BAS:  # entre par le haut en descendant ; sort par le bas
            return 1.0, t, -glissement if entree else glissement
        return 1.0, 1.0, 0.0

    # --- Fond du mot actif (lot 5) ----------------------------------------------------------------

    def _depart_du_glissement(self, bloc: Bloc, actif: int) -> MotPlace | None:
        """Le mot d'où glisse le fond du mot actif : le mot précédent, sur la même ligne (sur une
        autre ligne, le fond ne glisse pas : il apparaît sous le mot). None si ce fond ne glisse pas."""
        aspect = self.apparences[ACTIF]
        fond = aspect.fond
        if fond is None or not aspect.visible or not fond.glisse or fond.duree_glisse_ms <= 0:
            return None
        places = {place.index: place for place in bloc.mots}
        place, precedente = places.get(actif), places.get(actif - 1)
        if place is None or precedente is None or precedente.ligne != place.ligne:
            return None
        return precedente

    def _avancee_du_glissement(self, sous_titre: SousTitre, mots: list[MotAffiche], instant: Instant) -> float | None:
        """Où en est le fond du mot actif qui glisse depuis le mot précédent (0 : sous ce mot ; vers
        1 : arrivé), courbe douce comprise ; None s'il ne glisse pas, ou plus."""
        fond = self.apparences[ACTIF].fond
        if instant.actif is None or fond is None or instant.depuis_s >= fond.duree_glisse_ms / 1000:
            return None
        if self._depart_du_glissement(self.bloc(sous_titre, mots), instant.actif) is None:
            return None
        return _douce(instant.depuis_s / (fond.duree_glisse_ms / 1000))

    def en_mouvement(self, sous_titre: SousTitre, mots: list[MotAffiche], temps: float | None) -> bool:
        """Quelque chose bouge-t-il à ce moment (fond qui glisse, mot animé, retour en fondu,
        apparition ou disparition du sous-titre) ? L'aperçu se redessine alors à chaque image."""
        if temps is None:
            return False
        instant = self.instant(sous_titre, mots, temps)
        return (
            self._avancee_du_glissement(sous_titre, mots, instant) is not None
            or self._avancee_du_mot(instant) is not None
            or self._retour(sous_titre, instant) is not None
            or self._sous_titre_anime(sous_titre, temps) is not None
        )

    def _fond_actif(self, bloc: Bloc, actif: int, avancee: float = 1.0) -> QPainterPath | None:
        """Fond surligné du mot actif, en pixels de la vidéo (agrandissement et décalage du mot
        compris) ; None s'il n'en a pas. `avancee` inférieure à 1 : en train de glisser depuis le mot
        précédent (même ligne)."""
        aspect = self.apparences[ACTIF]
        if aspect.fond is None or not aspect.visible:
            return None
        place = next((p for p in bloc.mots if p.index == actif), None)
        if place is None:
            return None
        boite = self._boite_du_mot(place, bloc)
        rectangle = self._fond_d_etat(boite, aspect.fond)
        precedente = self._depart_du_glissement(bloc, actif) if avancee < 1 else None
        if precedente is not None:
            depart = self._fond_d_etat(self._boite_du_mot(precedente, bloc), aspect.fond)
            rectangle = QRectF(
                depart.left() + (rectangle.left() - depart.left()) * avancee,
                depart.top() + (rectangle.top() - depart.top()) * avancee,
                depart.width() + (rectangle.width() - depart.width()) * avancee,
                depart.height() + (rectangle.height() - depart.height()) * avancee,
            )
        return self._arrondis([rectangle], aspect.fond.arrondi_pct, self._transformation(boite, aspect))

    def _couleur_du_fond_actif(self) -> QColor:
        aspect = self.apparences[ACTIF]
        couleur = qcouleur(aspect.fond.couleur)
        couleur.setAlphaF(couleur.alphaF() * aspect.opacite)
        return couleur

    def fond_du_mot_actif(self, sous_titre: SousTitre, mots: list[MotAffiche], instant: Instant) -> tuple[QPainterPath, QColor] | None:
        """Fond surligné du mot actif à cet instant (en pixels de la vidéo) et sa couleur : s'il
        glisse, il part du mot précédent (même ligne) et arrive sur le mot actif en `duree_glisse_ms`."""
        if instant.actif is None:
            return None
        avancee = self._avancee_du_glissement(sous_titre, mots, instant)
        forme = self._fond_actif(self.bloc(sous_titre, mots), instant.actif, 1.0 if avancee is None else avancee)
        return None if forme is None else (forme, self._couleur_du_fond_actif())

    def _composer(self, dessous: QImage, dessus: QImage, fond: QPainterPath | None, gauche: int, haut: int, echelle: float) -> QImage:
        """Une seule image : ce qui passe sous le fond du mot actif, ce fond (en pixels de la vidéo),
        puis les lettres. L'aperçu et l'export posent ensuite cette même image, d'un seul coup : ils
        restent identiques au pixel près (poser les couches une à une sur la vidéo arrondirait
        autrement les bords et les transparences)."""
        image = dessous.copy()
        peintre = QPainter(image)
        if fond is not None:
            peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
            peintre.translate(-gauche, -haut)
            peintre.scale(echelle, echelle)
            peintre.fillPath(fond, self._couleur_du_fond_actif())
            peintre.resetTransform()
        peintre.drawImage(QPointF(0, 0), dessus)
        peintre.end()
        return image

    # --- L'image d'un instant ---------------------------------------------------------------------

    def image_de_l_instant(
        self,
        sous_titre: SousTitre,
        mots: list[MotAffiche],
        echelle: float,
        ratio_ecran: float = 1.0,
        temps: float | None = None,
    ) -> tuple[QImage, int, int]:
        """Le sous-titre à ce moment : une seule image transparente, en pixels réels de l'écran, et
        la place de son coin (x, y), en pixels réels par rapport au coin haut gauche de la vidéo.

        Tout y est assemblé (fond qui glisse, mot animé, retour en fondu, apparition ou disparition
        du sous-titre) : l'aperçu et l'export posent ensuite cette même image, d'un seul coup. Ils
        restent ainsi identiques au pixel près, même pendant une animation."""
        reelle = echelle * ratio_ecran
        instant = self.instant(sous_titre, mots, temps)
        avancee = self._avancee_du_mot(instant)
        retour = self._retour(sous_titre, instant)
        effet = self._sous_titre_anime(sous_titre, temps)

        # Le sous-titre, sans le mot actif pendant son animation (posé à part, plus bas).
        base = self.rendu(sous_titre, mots, echelle, ratio_ecran, instant.actif, sans=instant.actif if avancee is not None else None)
        image, x, y = base.image, base.x, base.y
        if base.dessous is not None:
            glissement = self._avancee_du_glissement(sous_titre, mots, instant)
            if glissement is not None:  # le fond glisse : refait pour cet instant
                fond = self._fond_actif(self.bloc(sous_titre, mots), instant.actif, glissement)
                image = self._composer(base.dessous, base.dessus, fond, x, y, reelle)

        # Par-dessus : le mot précédent qui garde un peu de son apparence de mot actif, puis le mot
        # actif animé (taille, opacité et décalage du moment, autour du centre du mot).
        couches = [(image, x, y, 1.0, QTransform())]
        if retour is not None:
            precedent, part = retour
            mot = self.rendu(sous_titre, mots, echelle, ratio_ecran, precedent, seulement=precedent)
            couches.append((mot.image, mot.x, mot.y, part, QTransform()))
        if avancee is not None:
            bloc = self.bloc(sous_titre, mots)
            place = next((p for p in bloc.mots if p.index == instant.actif), None)
            if place is not None:
                taille, opacite, decalage = self.valeurs_du_mot(avancee)
                centre = self._boite_du_mot(place, bloc).center()
                mot = self.rendu(sous_titre, mots, echelle, ratio_ecran, instant.actif, seulement=instant.actif)
                transformation = _autour(centre.x() * reelle, centre.y() * reelle, taille, decalage * reelle)
                couches.append((mot.image, mot.x, mot.y, opacite, transformation))
        if len(couches) > 1:
            image, x, y = _assembler(couches)

        # Apparition ou disparition du sous-titre entier : l'image entière, autour du centre du bloc.
        if effet is not None:
            taille, opacite, decalage = effet
            bloc = self.bloc(sous_titre, mots)
            centre_x, centre_y = (bloc.x + bloc.largeur / 2) * reelle, (bloc.y + bloc.hauteur / 2) * reelle
            image, x, y = _assembler([(image, x, y, opacite, _autour(centre_x, centre_y, taille, decalage * reelle))])
        if image.devicePixelRatio() != ratio_ecran:
            image.setDevicePixelRatio(ratio_ecran)
        return image, x, y

    def dessiner(
        self,
        peintre: QPainter,
        origine: QPointF,
        echelle: float,
        sous_titre: SousTitre,
        mots: list[MotAffiche],
        ratio_ecran: float = 1.0,
        temps: float | None = None,
    ) -> None:
        """Dessine le sous-titre avec le coin haut gauche de la vidéo en `origine` (coordonnées du
        peintre) et `echelle` points du peintre par pixel de vidéo. `ratio_ecran` : pixels réels de
        l'écran par point (écran à 150 % : 1,5), pour un texte net sur tous les écrans. `temps` : le
        moment de la vidéo (mot actif et animations ; sans temps, aucun mot n'est actif).

        Toujours une seule image posée : celle que l'export assemblera (image())."""
        image, x, y = self.image_de_l_instant(sous_titre, mots, echelle, ratio_ecran, temps)
        peintre.drawImage(QPointF(origine.x() + x / ratio_ecran, origine.y() + y / ratio_ecran), image)

    def image(self, sous_titre: SousTitre | None, mots: list[MotAffiche], temps: float | None = None) -> QImage:
        """Image transparente à la taille de la vidéo, avec ce sous-titre à ce moment (aucun : image
        vide). C'est l'image que l'export de la V3 assemblera, une par image du film."""
        image = self._vide(self.largeur, self.hauteur)
        if sous_titre is not None:
            peintre = QPainter(image)
            self.dessiner(peintre, QPointF(0, 0), 1.0, sous_titre, mots, temps=temps)
            peintre.end()
        return image
