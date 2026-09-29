"""Bouton maison (§9) : icône et texte centrés en hauteur, même écart icône → texte partout."""

import math

import pytest
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetricsF, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QDialog, QLineEdit, QMenu, QVBoxLayout

from ugc_studio.ui.composants.bouton import VARIANTES, Bouton, activer_avec_entree, dessiner_icone_et_texte
from ugc_studio.ui.composants.elements import bouton
from ugc_studio.ui.polices import police
from ugc_studio.ui.theme import Dimensions, Espacements, Hauteurs, Typo

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
    from ugc_studio.ui.composants.entete import TEXTE_SANS_PROJET, Entete

    entete = Entete()
    qtbot.addWidget(entete)
    assert entete.bouton_projet.text() == TEXTE_SANS_PROJET and entete.bouton_projet.est_attenue()
    entete.definir_projet("Sérum Glowzy")
    assert entete.bouton_projet.text() == "Sérum Glowzy" and not entete.bouton_projet.est_attenue()
    assert entete.bouton_projet.menu() is entete.menu_projet
