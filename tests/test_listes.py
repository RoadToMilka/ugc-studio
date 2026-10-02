"""Listes déroulantes intégrées au champ (V1.1, revues en V3.1 ; composants/liste_deroulante.py et elements.py)."""

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QHelpEvent, QImage, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyleOptionComboBox,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from ugc_studio.ui.composants.bulle import cacher_bulle, texte_de_la_bulle
from ugc_studio.ui.composants.elements import liste_deroulante
from ugc_studio.ui.composants.liste_deroulante import DelegueChoix, VueChoix
from ugc_studio.ui.theme import Couleurs, Dimensions, Hauteurs

LONG = "Kore · Ferme · féminine · une voix au nom beaucoup trop long pour le champ"


def _fenetre_avec_liste(qtbot, largeur: int = 400):
    fenetre = QWidget()
    disposition = QVBoxLayout(fenetre)
    liste = liste_deroulante()
    for numero in range(12):
        liste.addItem(f"Choix {numero}", numero)
    liste.setCurrentIndex(3)
    disposition.addWidget(liste)
    disposition.addStretch(1)
    qtbot.addWidget(fenetre)
    fenetre.resize(largeur, 300)
    fenetre.show()
    qtbot.waitExposed(fenetre)
    return fenetre, liste


def test_la_liste_s_ouvre_8_px_sous_le_champ_avec_le_choix_actuel(app_configuree, qtbot):
    """V3.1 : 8 px d'écart avec le champ, coins arrondis (fenêtre transparente autour), tous les choix
    à leur place, le choix actuel compris (jusqu'à la 3.0.0, il restait dans le champ seulement)."""
    _fenetre, liste = _fenetre_avec_liste(qtbot)
    option = QStyleOptionComboBox()
    liste.initStyleOption(option)
    assert liste.style().styleHint(QStyle.StyleHint.SH_ComboBox_Popup, option, liste) == 0  # pas par-dessus
    assert isinstance(liste.view(), VueChoix) and isinstance(liste.itemDelegate(), DelegueChoix)
    assert liste.maxVisibleItems() == Dimensions.LISTE_CHOIX_VISIBLES
    liste.showPopup()
    vue = liste.view()
    qtbot.waitUntil(vue.isVisible, timeout=2000)
    assert not any(vue.isRowHidden(rang) for rang in range(liste.count()))  # le choix actuel aussi
    conteneur = vue.window()
    assert conteneur.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # coins arrondis
    haut_de_la_liste = conteneur.mapToGlobal(QPoint(0, 0))
    bas_du_champ = liste.mapToGlobal(QPoint(0, liste.height()))
    assert haut_de_la_liste.y() - bas_du_champ.y() == Dimensions.ECART_LISTE == 8
    assert abs(haut_de_la_liste.x() - bas_du_champ.x()) <= 1
    assert abs(conteneur.width() - liste.width()) <= 2  # même largeur que le champ
    # Les choix commencent au même endroit que le texte du champ (plus de décalage vers la droite).
    texte_du_champ = liste.style().subControlRect(
        QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxEditField, liste
    )
    option_choix = QStyleOptionViewItem()
    option_choix.rect = vue.visualRect(liste.model().index(4, 0))
    liste.itemDelegate().initStyleOption(option_choix, liste.model().index(4, 0))
    texte_du_choix = vue.style().subElementRect(QStyle.SubElement.SE_ItemViewItemText, option_choix, vue)
    debut_champ = liste.mapToGlobal(texte_du_champ.topLeft()).x()
    debut_choix = vue.viewport().mapToGlobal(texte_du_choix.topLeft()).x()
    assert abs(debut_choix - debut_champ) <= 2
    # Clavier : ↓ passe au choix suivant, Entrée le prend.
    qtbot.keyClick(vue, Qt.Key.Key_Down)
    qtbot.keyClick(vue, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: not vue.isVisible(), timeout=2000)
    assert liste.currentIndex() == 4


def _couleur_du_choix(liste, rang: int, survole: bool) -> QColor:
    """Couleur au milieu d'un choix dessiné par la liste (fond de la liste ouverte autour)."""
    image = QImage(200, Hauteurs.CHOIX_LISTE, QImage.Format.Format_ARGB32)
    image.fill(QColor(Couleurs.SURFACE_ELEVEE))
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 200, Hauteurs.CHOIX_LISTE)
    option.state = QStyle.StateFlag.State_Enabled | (QStyle.StateFlag.State_Selected if survole else QStyle.StateFlag(0))
    peintre = QPainter(image)
    liste.itemDelegate().paint(peintre, option, liste.model().index(rang, 0))
    peintre.end()
    return image.pixelColor(2, Hauteurs.CHOIX_LISTE // 2)  # à gauche du texte


def test_choix_actuel_en_mauve_et_choix_survole_en_gris(app_configuree, qtbot):
    _fenetre, liste = _fenetre_avec_liste(qtbot)
    fond = QColor(Couleurs.SURFACE_ELEVEE)
    actuel = _couleur_du_choix(liste, 3, survole=False)
    assert actuel != fond and actuel.blue() > actuel.green() and actuel.red() > actuel.green()  # mauve
    assert _couleur_du_choix(liste, 5, survole=True) == QColor(Couleurs.BORDURE)  # gris
    assert _couleur_du_choix(liste, 5, survole=False) == fond  # les autres : sans fond


def test_texte_trop_long_abrege_dans_le_champ(app_configuree, qtbot):
    _fenetre, liste = _fenetre_avec_liste(qtbot, largeur=260)
    liste.insertItem(0, LONG)
    liste.setCurrentIndex(0)
    affiche = liste.texte_affiche()
    assert affiche.endswith("…") and len(affiche) < len(LONG)  # « Kore · Ferme · fémi… »
    # Au survol : le texte complet.
    centre = QPoint(liste.width() // 2, liste.height() // 2)
    QApplication.sendEvent(liste, QHelpEvent(QEvent.Type.ToolTip, centre, liste.mapToGlobal(centre)))
    assert texte_de_la_bulle().replace("\n", " ") == LONG  # la bulle de l'app (V3.2), en lignes courtes
    cacher_bulle()
    liste.setCurrentIndex(1)
    assert liste.texte_affiche() == "Choix 0"  # texte court : rien n'est abrégé


def test_separations_en_fine_ligne(app_configuree, qtbot):
    """Séparations (ex. entre favoris, voix créées et voix de base) : une fine ligne, pas un choix."""
    _fenetre, liste = _fenetre_avec_liste(qtbot)
    liste.insertSeparator(2)
    delegue, option = liste.itemDelegate(), QStyleOptionViewItem()
    assert delegue.sizeHint(option, liste.model().index(2, 0)).height() == Dimensions.SEPARATEUR_LISTE
    assert delegue.sizeHint(option, liste.model().index(0, 0)).height() >= Hauteurs.CHOIX_LISTE
