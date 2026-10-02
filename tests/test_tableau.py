"""Tableaux (V1.1, composants/tableau.py) : une ligne par case, colonnes de texte qui se resserrent
d'abord, barre horizontale en dernier recours, texte complet au survol."""

from PySide6.QtCore import QEvent
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication, QTableWidgetItem

from ugc_studio.ui.composants.bulle import cacher_bulle, texte_de_la_bulle
from ugc_studio.ui.composants.tableau import Colonne, Tableau
from ugc_studio.ui.theme import Dimensions, Hauteurs

COLONNES = (
    Colonne("Date"),
    Colonne("Projet", texte=True),
    Colonne("Modèle", texte=True, etiree=True),
    Colonne("Coût", a_droite=True),
)
LIGNES = (
    ("30/09/2026 18:22", "Sérum Glowzy", "Gemini 3.8 Flash TTS", "0.1469 €"),
    ("30/09/2026 15:27", "Brosse lissante chauffante pour cheveux", "Gemini 3.5 Transcribe", "0.0195 €"),
)


def _tableau(qtbot, largeur: int, lignes=LIGNES) -> Tableau:
    tableau = Tableau(COLONNES)
    qtbot.addWidget(tableau)
    tableau.setRowCount(len(lignes))
    for rang, valeurs in enumerate(lignes):
        for colonne, texte in enumerate(valeurs):
            tableau.setItem(rang, colonne, QTableWidgetItem(texte))
    tableau.resize(largeur, 300)
    tableau.show()
    tableau.contenu_change()
    return tableau


def test_une_ligne_par_case(app_configuree, qtbot):
    tableau = _tableau(qtbot, 900)
    assert not tableau.wordWrap()
    assert [tableau.rowHeight(rang) for rang in range(tableau.rowCount())] == [Hauteurs.LIGNE_TABLEAU] * 2


def test_texte_ecrit_sur_deux_lignes(app_configuree, qtbot):
    """Seule exception : un texte écrit exprès sur 2 lignes (un sous-titre) garde ses 2 lignes."""
    tableau = _tableau(qtbot, 900, (("0:01", "Mais ce sérum\nGlowzy a vraiment", "", ""),))
    assert tableau.rowHeight(0) > Hauteurs.LIGNE_TABLEAU


def test_les_colonnes_de_texte_se_resserrent_d_abord(app_configuree, qtbot):
    large = _tableau(qtbot, 1000)
    etroit = _tableau(qtbot, 560)
    # Dates et montants : toujours en entier.
    assert etroit.columnWidth(0) == large.columnWidth(0) and etroit.columnWidth(3) == large.columnWidth(3)
    assert etroit.colonnes_coupees() == []
    # Les colonnes de texte se partagent la place qui reste : tout tient, sans barre.
    assert etroit.columnWidth(1) < large.columnWidth(1)
    assert sum(etroit.columnWidth(i) for i in range(4)) == etroit.viewport().width()
    assert etroit.horizontalScrollBar().maximum() == 0


def test_barre_horizontale_en_dernier_recours(app_configuree, qtbot):
    tableau = _tableau(qtbot, 300)
    assert tableau.columnWidth(1) == min(Dimensions.COLONNE_TEXTE_MIN, tableau.columnWidth(1))
    assert tableau.colonnes_coupees() == []  # le coût reste en entier…
    # … et une barre permet d'aller le voir.
    qtbot.waitUntil(lambda: tableau.horizontalScrollBar().maximum() > 0, timeout=2000)


def test_texte_complet_au_survol(app_configuree, qtbot):
    tableau = _tableau(qtbot, 560)
    index = tableau.model().index(1, 1)  # « Brosse lissante chauffante pour cheveux », abrégé
    centre = tableau.visualRect(index).center()
    evenement = QHelpEvent(QEvent.Type.ToolTip, centre, tableau.viewport().mapToGlobal(centre))
    QApplication.sendEvent(tableau.viewport(), evenement)
    assert texte_de_la_bulle() == "Brosse lissante chauffante pour cheveux"  # la bulle de l'app (V3.2)
    cacher_bulle()


def test_montants_jamais_coupes(app_configuree, qtbot):
    """Coûts au format §4.4 (petites décimales) : mesurés avec les polices qui les dessinent."""
    from PySide6.QtWidgets import QStyleOptionViewItem

    from ugc_studio.ui.composants.montant_label import ROLE_MONTANT, DelegueMontant

    tableau = Tableau((Colonne("Projet", texte=True), Colonne("Coût", a_droite=True)))
    qtbot.addWidget(tableau)
    tableau.setItemDelegateForColumn(1, DelegueMontant(tableau))
    tableau.setRowCount(2)
    tableau.setItem(0, 0, QTableWidgetItem("Sérum Glowzy"))
    for rang, montant in enumerate(("12.3456", "")):  # vide : prix inconnu
        case = QTableWidgetItem()
        case.setData(ROLE_MONTANT, montant)
        tableau.setItem(rang, 1, case)
    tableau.resize(200, 200)
    tableau.show()
    tableau.contenu_change()
    delegue = tableau.itemDelegateForColumn(1)
    besoin = max(delegue.sizeHint(QStyleOptionViewItem(), tableau.model().index(rang, 1)).width() for rang in range(2))
    assert tableau.columnWidth(1) >= besoin and tableau.colonnes_coupees() == []
    assert not tableau.grab().isNull()  # se dessine sans erreur
