"""Listes déroulantes intégrées au champ (V1.1, composants/liste_deroulante.py et elements.py)."""

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyleOptionComboBox,
    QStyleOptionViewItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ugc_studio.ui.composants.elements import liste_deroulante
from ugc_studio.ui.composants.liste_deroulante import DelegueChoix, VueChoix
from ugc_studio.ui.theme import Dimensions, Hauteurs

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


def test_la_liste_s_ouvre_sous_le_champ_sans_le_choix_actuel(app_configuree, qtbot):
    _fenetre, liste = _fenetre_avec_liste(qtbot)
    option = QStyleOptionComboBox()
    liste.initStyleOption(option)
    assert liste.style().styleHint(QStyle.StyleHint.SH_ComboBox_Popup, option, liste) == 0  # pas par-dessus
    assert isinstance(liste.view(), VueChoix) and isinstance(liste.itemDelegate(), DelegueChoix)
    assert liste.maxVisibleItems() == Dimensions.LISTE_CHOIX_VISIBLES
    liste.showPopup()
    vue = liste.view()
    qtbot.waitUntil(vue.isVisible, timeout=2000)
    assert vue.isRowHidden(3) and not vue.isRowHidden(4)  # le choix actuel reste dans le champ
    conteneur = vue.window()
    haut_de_la_liste = conteneur.mapToGlobal(QPoint(0, 0))
    bas_du_champ = liste.mapToGlobal(QPoint(0, liste.height()))
    assert abs(haut_de_la_liste.y() - bas_du_champ.y()) <= 2 and abs(haut_de_la_liste.x() - bas_du_champ.x()) <= 1
    assert abs(conteneur.width() - liste.width()) <= 2  # même largeur que le champ
    # Clavier : ↓ passe au choix suivant (le choix actuel, caché, est sauté), Entrée le prend.
    qtbot.keyClick(vue, Qt.Key.Key_Down)
    qtbot.keyClick(vue, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: not vue.isVisible(), timeout=2000)
    assert liste.currentIndex() == 4
    assert not vue.isRowHidden(3)


def test_texte_trop_long_abrege_dans_le_champ(app_configuree, qtbot):
    _fenetre, liste = _fenetre_avec_liste(qtbot, largeur=260)
    liste.insertItem(0, LONG)
    liste.setCurrentIndex(0)
    affiche = liste.texte_affiche()
    assert affiche.endswith("…") and len(affiche) < len(LONG)  # « Kore · Ferme · fémi… »
    # Au survol : le texte complet.
    centre = QPoint(liste.width() // 2, liste.height() // 2)
    QApplication.sendEvent(liste, QHelpEvent(QEvent.Type.ToolTip, centre, liste.mapToGlobal(centre)))
    assert QToolTip.text() == LONG
    QToolTip.hideText()
    liste.setCurrentIndex(1)
    assert liste.texte_affiche() == "Choix 0"  # texte court : rien n'est abrégé


def test_separations_en_fine_ligne(app_configuree, qtbot):
    """Séparations (ex. entre favoris, voix créées et voix de base) : une fine ligne, pas un choix."""
    _fenetre, liste = _fenetre_avec_liste(qtbot)
    liste.insertSeparator(2)
    delegue, option = liste.itemDelegate(), QStyleOptionViewItem()
    assert delegue.sizeHint(option, liste.model().index(2, 0)).height() == Dimensions.SEPARATEUR_LISTE
    assert delegue.sizeHint(option, liste.model().index(0, 0)).height() >= Hauteurs.CHOIX_LISTE
