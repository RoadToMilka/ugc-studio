"""Bouton maison (§9) : icône et texte centrés en hauteur, même écart icône → texte partout."""

import math

import pytest
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetricsF, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QDialog, QLineEdit, QMenu, QVBoxLayout

from ugc_studio.ui.composants.bouton import (
    VARIANTES,
    Bouton,
    activer_avec_entree,
    dessiner_icone_et_texte,
    dessiner_texte_centre_a_l_oeil,
)
from ugc_studio.ui.composants.elements import bouton
from ugc_studio.ui.polices import police
from ugc_studio.ui.theme import Couleurs, Dimensions, Espacements, Hauteurs, Opacites, Typo, qcolor

ROUGE, VERT = QColor(255, 0, 0), QColor(0, 255, 0)


def test_un_seul_ecart_celui_de_la_barre_laterale():
    assert Dimensions.ECART_ICONE_TEXTE == Espacements.M == 12


def test_taille_d_un_bouton_avec_icone(app_configuree, qtbot):
    tester = bouton("Tester", nom_icone="refresh-cw")
    qtbot.addWidget(tester)
    mesures = QFontMetricsF(police(Typo.COURANT, Typo.GRAISSE_MOYENNE))
    contenu = Dimensions.ICONE_PETITE + Dimensions.ECART_ICONE_TEXTE + mesures.horizontalAdvance("Tester")
    assert tester.sizeHint().width() == math.ceil(contenu) + 2 * Espacements.L
    assert tester.sizeHint().height() == Hauteurs.CONTROLE
    assert tester.iconSize().width() == Dimensions.ICONE_PETITE


def test_bouton_icone_carre(app_configuree, qtbot):
    plus = bouton("", variante="icone", nom_icone="ellipsis")
    qtbot.addWidget(plus)
    assert (plus.sizeHint().width(), plus.sizeHint().height()) == (Hauteurs.PETIT_BOUTON, Hauteurs.PETIT_BOUTON)


def _dessiner(texte: str, icone_a_droite: bool = False) -> QImage:
    """Dessine une « icône » rouge de 16 px et un texte vert sur fond noir."""
    largeur, hauteur = 240, Hauteurs.CONTROLE
    image = QImage(largeur, hauteur, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.black)
    icone = QPixmap(Dimensions.ICONE_PETITE, Dimensions.ICONE_PETITE)
    icone.fill(ROUGE)
    peintre = QPainter(image)
    dessiner_icone_et_texte(
        peintre,
        QRectF(0, 0, largeur, hauteur),
        icone,
        Dimensions.ICONE_PETITE,
        texte,
        police(Typo.COURANT, Typo.GRAISSE_MOYENNE),
        VERT,
        icone_a_droite=icone_a_droite,
    )
    peintre.end()
    return image


def _boite(image: QImage, teste) -> tuple[int, int, int, int]:
    """Plus petit rectangle (gauche, haut, droite, bas) contenant les pixels qui passent le test."""
    points = [
        (x, y) for y in range(image.height()) for x in range(image.width()) if teste(image.pixelColor(x, y))
    ]
    xs, ys = [x for x, _ in points], [y for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def _est_icone(c: QColor) -> bool:
    return c.red() > 200 and c.green() < 60


def _est_texte(c: QColor) -> bool:
    return c.green() > 110 and c.red() < 60


def test_icone_et_texte_centres_en_hauteur_avec_le_bon_ecart(app_configuree):
    image = _dessiner("HHH")  # majuscules plates : leur encre va exactement du haut des capitales à la ligne de base
    ig, ih, id_, ib = _boite(image, _est_icone)
    tg, th, _td, tb = _boite(image, _est_texte)
    # Icône centrée en hauteur
    assert (ib - ih + 1) == Dimensions.ICONE_PETITE
    assert ih == (Hauteurs.CONTROLE - Dimensions.ICONE_PETITE) // 2
    # Texte centré sur le même milieu que l'icône (à un pixel près, arrondi de l'anticrénelage)
    assert abs((th + tb) / 2 - (ih + ib) / 2) <= 1
    # Écart icône → texte = ECART_ICONE_TEXTE (+ la petite marge dessinée avant la lettre « H »)
    marge_h = QFontMetricsF(police(Typo.COURANT, Typo.GRAISSE_MOYENNE)).leftBearing("H")
    assert abs((tg - id_ - 1) - (Dimensions.ECART_ICONE_TEXTE + marge_h)) <= 1


def test_icone_a_droite_meme_ecart(app_configuree):
    image = _dessiner("HHH", icone_a_droite=True)
    ig, _ih, _id, _ib = _boite(image, _est_icone)
    _tg, _th, td, _tb = _boite(image, _est_texte)
    marge_h = QFontMetricsF(police(Typo.COURANT, Typo.GRAISSE_MOYENNE)).rightBearing("H")
    assert abs((ig - td - 1) - (Dimensions.ECART_ICONE_TEXTE + marge_h)) <= 1


def _encre_dans_une_pastille(texte: str) -> tuple[int, int, int, int]:
    """Dessine `texte` centré à l'œil dans une pastille (fond noir, texte vert) : sa boîte d'encre."""
    largeur, hauteur = 120, Hauteurs.PASTILLE
    image = QImage(largeur, hauteur, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.black)
    peintre = QPainter(image)
    dessiner_texte_centre_a_l_oeil(
        peintre, QRectF(0, 0, largeur, hauteur), texte, police(Typo.LEGENDE, Typo.GRAISSE_MOYENNE), VERT
    )
    peintre.end()
    return _boite(image, _est_texte)


def test_texte_des_pastilles_centre_a_l_oeil(app_configuree):
    """Badges de balises et pastilles (§5.2). Avant, Qt centrait la « boîte » de la police : un mot
    en minuscules paraissait 1 à 2 px trop bas. Maintenant :
    - un mot en minuscules (« xxx » : son encre va du haut des minuscules à la ligne de base) a
      ses minuscules au milieu de la pastille ;
    - un mot qui commence par une majuscule (« Retenue ») reste équilibré : son encre est au milieu,
      à un pixel près."""
    milieu = Hauteurs.PASTILLE / 2
    gauche, haut, droite, bas = _encre_dans_une_pastille("xxx")
    assert abs((haut + bas + 1) / 2 - milieu) <= 0.75
    assert abs((gauche + droite + 1) / 2 - 60) <= 1  # centré en largeur aussi
    _g, haut, _d, bas = _encre_dans_une_pastille("Retenue")
    assert abs((haut + bas + 1) / 2 - milieu) <= 1


@pytest.mark.parametrize("variante", VARIANTES)
def test_chaque_variante_se_dessine(app_configuree, qtbot, variante):
    element = Bouton("" if variante == "icone" else "Générer", variante, "mic")
    qtbot.addWidget(element)
    element.show()
    assert not element.grab().isNull()
    element.setEnabled(False)
    assert not element.grab().isNull()


def test_variante_inconnue_refusee(app_configuree):
    with pytest.raises(ValueError):
        Bouton("x", "clignotant")
    with pytest.raises(ValueError):
        Bouton("x", "discret")  # ancien style, remplacé par « contour » (v1.0.2)


def test_quatre_styles_et_l_etat_selectionne(app_configuree, qtbot):
    """Principal : mauve. Normal : fond gris clair. Contour : pas de fond, contour gris.
    Icône : ni fond ni contour. Sélectionné (onglet actif, bouton coché) : contour mauve et fond
    mauve léger, comme le module actif de la barre latérale."""
    principal, normal, contour, icone_seule = (
        Bouton("Générer l'audio", "principal"),
        Bouton("Tester la clé"),
        Bouton("Accentuer", "contour"),
        Bouton("", "icone", "ellipsis"),
    )
    for element in (principal, normal, contour, icone_seule):
        qtbot.addWidget(element)
    assert principal._apparence().contour == qcolor(Couleurs.ACCENT)
    assert normal._apparence().fond == qcolor(Couleurs.SURFACE_ELEVEE)
    assert contour._apparence().fond is None and contour._apparence().contour is not None
    assert icone_seule._apparence().fond is None and icone_seule._apparence().contour is None

    for bouton_cochable in (normal, contour):
        bouton_cochable.setCheckable(True)
        bouton_cochable.setChecked(True)
        apparence = bouton_cochable._apparence()
        assert apparence.fond == qcolor(Couleurs.ACCENT, Opacites.TEINTE_SELECTION)
        assert apparence.contour == qcolor(Couleurs.ACCENT) and apparence.texte == Couleurs.TEXTE

    contour.setChecked(False)
    contour.setEnabled(False)
    assert contour._apparence().fond is None and contour._apparence().texte == Couleurs.TEXTE_DESACTIVE


def test_le_menu_s_ouvre_et_le_bouton_se_releve(app_configuree, qtbot):
    plus = bouton("", variante="icone", nom_icone="ellipsis")
    qtbot.addWidget(plus)
    plus.show()
    menu = QMenu(plus)
    menu.addAction("Renommer…")
    plus.setMenu(menu)
    ouvertures = []
    menu.aboutToShow.connect(lambda: ouvertures.append(True))
    QTimer.singleShot(50, menu.close)
    qtbot.mousePress(plus, Qt.MouseButton.LeftButton)  # ouvre le menu (jusqu'à sa fermeture)
    assert ouvertures == [True]
    assert not plus.isDown()


def test_touche_entree(app_configuree, qtbot):
    dialogue = QDialog()
    qtbot.addWidget(dialogue)
    disposition = QVBoxLayout(dialogue)
    champ = QLineEdit()
    disposition.addWidget(champ)
    appels: list[str] = []
    annuler = bouton("Annuler", action=lambda: appels.append("annuler"))
    valider = bouton("Valider", variante="principal", action=lambda: appels.append("valider"))
    disposition.addWidget(annuler)
    disposition.addWidget(valider)
    activer_avec_entree(valider, dialogue)
    dialogue.show()

    # Entrée dans un champ de texte : le bouton « par défaut » est déclenché.
    qtbot.keyClick(champ, Qt.Key.Key_Return)
    assert appels == ["valider"]

    # Bouton sélectionné au clavier : Entrée le déclenche lui.
    qtbot.keyClick(annuler, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: appels == ["valider", "annuler"])

    # Bouton par défaut désactivé : rien ne se passe.
    valider.setEnabled(False)
    qtbot.keyClick(champ, Qt.Key.Key_Return)
    assert appels == ["valider", "annuler"]


def test_projet_attenue_sans_projet(app_configuree, qtbot):
    """V3.1 : le projet ouvert est en haut de la barre latérale (il quitte le bandeau)."""
    from ugc_studio.ui.composants.barre_laterale import AIDE_PROJET, TEXTE_SANS_PROJET, BarreLaterale

    barre = BarreLaterale((), ())
    qtbot.addWidget(barre)
    projet = barre.bouton_projet
    assert projet.text() == TEXTE_SANS_PROJET and projet.est_attenue() and projet.toolTip() == AIDE_PROJET
    barre.definir_projet("Sérum Glowzy")
    assert projet.text() == "Sérum Glowzy" and not projet.est_attenue()
    assert projet.toolTip() == f"Sérum Glowzy\n{AIDE_PROJET}"  # nom complet au survol, même abrégé
    assert projet.menu() is barre.menu_projet


def test_bouton_du_projet(app_configuree, qtbot):
    """Contour gris et coins arrondis, sans fond ; le nom à gauche, abrégé par « … » s'il est long ;
    la flèche au bord droit ; toute la largeur de la barre latérale, à la hauteur des champs."""
    from ugc_studio.ui.composants.barre_laterale import BarreLaterale

    barre = BarreLaterale((), ())
    qtbot.addWidget(barre)
    barre.show()
    projet = barre.bouton_projet
    # 12 px de chaque côté, dans la barre latérale (moins sa bordure de droite, 1 px).
    assert projet.width() == Dimensions.LARGEUR_BARRE_LATERALE - Dimensions.BORDURE - 2 * Espacements.M
    assert projet.height() == Hauteurs.CONTROLE
    apparence = projet._apparence()
    assert apparence.fond is None and apparence.contour == qcolor(Couleurs.TEXTE_SECONDAIRE, Opacites.CONTOUR_BOUTON)
    barre.definir_projet("Sérum Glowzy")
    assert projet._apparence().texte == Couleurs.TEXTE and not projet.texte_abrege()
    barre.definir_projet("Sérum éclat Glowzy, campagne de la rentrée 2026")
    assert projet.texte_abrege() and projet.minimumSizeHint().width() < projet.width()
    # La flèche est dessinée contre le bord droit (à 12 px), le nom contre le bord gauche (à 12 px) :
    # pixels opaques et clairs (le contour, lui, est transparent à 65 %).
    image = projet.grab().toImage()
    echelle = image.width() / projet.width()
    traits = [
        x / echelle
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() > 200 and image.pixelColor(x, y).lightness() > 120
    ]
    assert Espacements.M - 1 <= min(traits) <= Espacements.M + 2
    debut_fleche = projet.width() - Espacements.M - Dimensions.ICONE_PETITE
    assert debut_fleche < max(traits) <= projet.width() - Espacements.M  # la flèche, au bord droit
    # Entre le nom abrégé et la flèche : l'écart habituel entre un texte et son icône, vide.
    assert not [x for x in traits if debut_fleche - Dimensions.ECART_ICONE_TEXTE + 1 < x < debut_fleche]
