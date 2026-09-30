"""Onglets en boutons (§9.4 bis) : une rangée de boutons au-dessus du contenu."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QFrame, QLabel

from ugc_studio.ui.composants.onglets import Onglets
from ugc_studio.ui.theme import Couleurs, Espacements, qcolor

TITRES = ("Connexions", "Modèles et prix", "Données")


def _onglets(qtbot) -> tuple[Onglets, list[QLabel]]:
    onglets = Onglets()
    qtbot.addWidget(onglets)
    pages = [QLabel(f"Page {titre}") for titre in TITRES]
    for page, titre in zip(pages, TITRES):
        onglets.addTab(page, titre)
    return onglets, pages


def test_premier_onglet_actif_au_depart(app_configuree, qtbot):
    onglets, pages = _onglets(qtbot)
    assert onglets.count() == 3
    assert [onglets.tabText(index) for index in range(3)] == list(TITRES)
    assert onglets.currentIndex() == 0 and onglets.currentWidget() is pages[0] and onglets.widget(2) is pages[2]
    assert onglets.bouton(0).isChecked() and not onglets.bouton(1).isChecked()
    assert {onglets.bouton(index).variante for index in range(3)} == {"contour"}


def test_un_clic_change_d_onglet(app_configuree, qtbot):
    onglets, pages = _onglets(qtbot)
    onglets.show()
    changements: list[int] = []
    onglets.currentChanged.connect(changements.append)
    qtbot.mouseClick(onglets.bouton(2), Qt.MouseButton.LeftButton)
    assert onglets.currentIndex() == 2 and onglets.currentWidget() is pages[2]
    assert changements == [2]
    assert [onglets.bouton(index).isChecked() for index in range(3)] == [False, False, True]  # un seul actif
    qtbot.mouseClick(onglets.bouton(2), Qt.MouseButton.LeftButton)  # recliquer l'onglet actif : il le reste
    assert onglets.bouton(2).isChecked() and changements == [2]


def test_changer_d_onglet_par_le_code(app_configuree, qtbot):
    onglets, _pages = _onglets(qtbot)
    onglets.setCurrentIndex(1)
    assert onglets.currentIndex() == 1 and onglets.bouton(1).isChecked() and not onglets.bouton(0).isChecked()
    onglets.setCurrentIndex(7)  # onglet qui n'existe pas : rien ne change
    assert onglets.currentIndex() == 1
    onglets.setTabEnabled(2, False)
    assert not onglets.bouton(2).isEnabled()


def test_l_onglet_actif_a_l_allure_selectionnee(app_configuree, qtbot):
    """Onglet actif : contour mauve et fond mauve léger, comme le module actif de la barre latérale.
    Les autres : style « contour », sans fond."""
    onglets, _pages = _onglets(qtbot)
    actif, autre = onglets.bouton(0)._apparence(), onglets.bouton(1)._apparence()
    assert actif.contour == qcolor(Couleurs.ACCENT) and actif.fond is not None and actif.texte == Couleurs.TEXTE
    assert autre.fond is None and autre.texte == Couleurs.TEXTE_SECONDAIRE


def test_ligne_puis_espace_puis_boutons(app_configuree, qtbot):
    """De haut en bas : la ligne de séparation, un espace de 16 px, puis la rangée de boutons."""
    onglets, _pages = _onglets(qtbot)
    onglets.resize(600, 300)
    onglets.show()
    (ligne,) = [cadre for cadre in onglets.findChildren(QFrame) if cadre.property("role") == "separateur"]
    bas_de_la_ligne = ligne.mapTo(onglets, QPoint(0, ligne.height())).y()
    haut_des_boutons = onglets.bouton(0).mapTo(onglets, QPoint(0, 0)).y()
    assert haut_des_boutons - bas_de_la_ligne == Espacements.L
