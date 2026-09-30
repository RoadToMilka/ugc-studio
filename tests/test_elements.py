"""Éléments de base de l'interface (ui/composants/elements.py)."""

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QLabel, QStyle, QStyleOptionButton, QVBoxLayout, QWidget

from ugc_studio.ui.composants.elements import (
    Info,
    case_a_cocher,
    champ_decimal,
    champ_entier,
    glissiere,
    info,
    liste_deroulante,
    pastille,
)
from ugc_studio.ui.theme import Dimensions, Espacements, Hauteurs


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
    """L'explication d'une case est une info : ampoule sous la case, texte aligné sur celui de la case."""
    zone, case = case_a_cocher("Séparer les voix", "Chaque mot reçoit la personne qui parle.")
    qtbot.addWidget(zone)
    zone.resize(zone.sizeHint())
    zone.show()
    (explication,) = zone.findChildren(Info)
    (legende,) = zone.findChildren(QLabel)
    assert case.text() == "Séparer les voix"
    assert legende.wordWrap() and explication.text() == "Chaque mot reçoit la personne qui parle."
    option = QStyleOptionButton()
    case.initStyleOption(option)
    debut_texte_case = case.style().subElementRect(QStyle.SubElement.SE_CheckBoxContents, option, case).left()
    assert abs(legende.mapTo(zone, QPoint(0, 0)).x() - (case.x() + debut_texte_case)) <= 1
    ampoule = explication.ampoule.mapTo(zone, QPoint(0, 0)).x()
    assert case.x() <= ampoule and ampoule + Dimensions.ICONE_PETITE <= case.x() + Dimensions.CASE_A_COCHER
    zone.setEnabled(False)  # griser la zone grise la case et son explication
    assert not case.isEnabled() and not legende.isEnabled() and not explication.ampoule.isEnabled()
    zone, case = case_a_cocher("Tout en majuscules")
    qtbot.addWidget(zone)
    assert zone.findChildren(QLabel) == []


def test_info_avec_ampoule(app_configuree, qtbot):
    """Une info commence par l'ampoule ; une donnée ou un message d'état s'affichent sans elle."""
    aide = info("Une fin de phrase termine alors toujours le sous-titre.")
    qtbot.addWidget(aide)
    aide.show()
    assert aide.ampoule.isVisible() and aide.etiquette.wordWrap()
    assert aide.ampoule.width() == Dimensions.ICONE_PETITE  # même taille, donc même trait, que les icônes des boutons
    assert aide.etiquette.x() == Dimensions.ICONE_PETITE + Espacements.S
    assert not aide.grab().isNull()  # se dessine sans erreur

    aide.afficher_etat("Récupération du taux auprès de la BCE…")
    assert not aide.ampoule.isVisible() and aide.etiquette.property("role") == "legende"
    aide.afficher_etat("Taux non récupéré : pas de réseau", erreur=True)
    assert aide.etiquette.property("role") == "legende-erreur"
    aide.setText("Taux de départ, à vérifier.")
    assert aide.ampoule.isVisible() and aide.etiquette.property("role") == "legende"
    assert aide.text() == "Taux de départ, à vérifier."

    explication = info("Tes styles enregistrés, rangés par catégorie.", "secondaire")
    qtbot.addWidget(explication)
    explication.afficher_etat("Erreur", erreur=True)
    assert explication.etiquette.property("role") == "erreur"


def test_pastille(app_configuree, qtbot):
    """Pastille (« Retenue », « Par défaut ») : dessinée par l'app pour centrer son texte à l'œil ;
    elle reste une étiquette de texte (QLabel), à la hauteur du thème."""
    retenue = pastille("Retenue")
    qtbot.addWidget(retenue)
    assert isinstance(retenue, QLabel) and retenue.text() == "Retenue"
    assert retenue.sizeHint().height() == Hauteurs.PASTILLE
    assert not retenue.grab().isNull()  # se dessine sans erreur
