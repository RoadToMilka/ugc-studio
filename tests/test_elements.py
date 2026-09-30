"""Éléments de base de l'interface (ui/composants/elements.py)."""

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from ugc_studio.ui.composants.elements import case_a_cocher, champ_decimal, champ_entier, glissiere, liste_deroulante


def _molette(element) -> QWheelEvent:
    """Un cran de molette (vers le bas) au-dessus de l'élément."""
    centre = QPointF(element.width() / 2, element.height() / 2)
    evenement = QWheelEvent(
        centre,
        element.mapToGlobal(centre),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(element, evenement)
    return evenement


def test_la_molette_fait_defiler_la_page_sans_changer_les_valeurs(app_configuree, qtbot):
    """Faire défiler une page avec la molette ne doit pas changer au passage le modèle choisi, un
    réglage ou le moment de lecture."""
    liste = liste_deroulante()
    liste.addItems(["Gemini 3.8 Flash TTS", "Gemini 3.8 Flash Lite TTS", "Autre"])
    entier = champ_entier(1, 20)
    entier.setValue(5)
    decimal = champ_decimal(0.0, 5.0, 0.1, 1, " s")
    decimal.setValue(0.6)
    barre = glissiere()
    barre.setRange(0, 1000)
    barre.setValue(500)
    page = QWidget()
    disposition = QVBoxLayout(page)
    for element in (liste, entier, decimal, barre):
        disposition.addWidget(element)
    qtbot.addWidget(page)
    page.show()
    for element, valeur in ((liste, liste.currentIndex), (entier, entier.value), (decimal, decimal.value), (barre, barre.value)):
        avant = valeur()
        evenement = _molette(element)
        assert valeur() == avant, type(element).__name__
        assert not evenement.isAccepted()  # l'évènement continue vers la page, qui défile


def test_champs_de_nombre(app_configuree, qtbot):
    champ = champ_decimal(0.0, 5.0, 0.1, 1, " s", "Durée minimale")
    qtbot.addWidget(champ)
    champ.setValue(9.0)
    assert champ.value() == 5.0 and champ.suffix() == " s" and champ.toolTip() == "Durée minimale"
    assert champ.buttonSymbols() == champ.ButtonSymbols.NoButtons


def test_case_a_cocher_avec_explication(app_configuree, qtbot):
    zone, case = case_a_cocher("Séparer les voix", "Chaque mot reçoit la personne qui parle.")
    qtbot.addWidget(zone)
    (legende,) = zone.findChildren(QLabel)
    assert case.text() == "Séparer les voix"
    assert legende.wordWrap() and legende.contentsMargins().left() > 0  # alignée sur le texte de la case
    zone.setEnabled(False)  # griser la zone grise la case et son explication
    assert not case.isEnabled() and not legende.isEnabled()
    zone, case = case_a_cocher("TOUT EN MAJUSCULES")
    qtbot.addWidget(zone)
    assert zone.findChildren(QLabel) == []
