"""Bouton « Conseils » (V1.1) : en haut à droite de chaque module et des fenêtres, il ouvre les
conseils de la page, en français."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QLabel

from ugc_studio.connexions import CoffreMemoire
from ugc_studio.conseils import CONSEILS_STYLE
from ugc_studio.conseils_des_pages import PAGES
from ugc_studio.services import creer_services
from ugc_studio.ui.composants.bouton import Bouton
from ugc_studio.ui.composants.conseils import TEXTE_BOUTON, DialogueConseils
from ugc_studio.ui.fenetre_principale import FenetrePrincipale


def _boutons_conseils(racine) -> list[Bouton]:
    return [b for b in racine.findChildren(Bouton) if b.text() == TEXTE_BOUTON]


@pytest.fixture
def fenetre(app_configuree, qtbot):
    fenetre = FenetrePrincipale(creer_services(CoffreMemoire()))
    qtbot.addWidget(fenetre)
    return fenetre


def test_chaque_module_a_son_bouton_conseils(fenetre):
    """Dans chaque module, avec ou sans projet ouvert : le bouton ouvre les conseils du module."""
    for module in ("voix", "transcription", "sous-titres", "reglages"):
        boutons = _boutons_conseils(fenetre.page(module))
        assert boutons, module
        assert {b.property("conseils") for b in boutons} == {module}
        assert all(b.variante == "contour" for b in boutons)


def test_bouton_en_haut_a_droite_sur_la_ligne_du_titre(fenetre):
    fenetre.show()
    fenetre.afficher_module("reglages")
    page = fenetre.page("reglages")
    bouton = page.bouton_conseils
    titre = next(e for e in page.findChildren(QLabel) if e.text() == "Réglages")
    centre_bouton = bouton.mapTo(page, QPoint(0, bouton.height() // 2)).y()
    centre_titre = titre.mapTo(page, QPoint(0, titre.height() // 2)).y()
    assert abs(centre_bouton - centre_titre) <= 1  # sur la ligne du titre
    droite = bouton.mapTo(page, QPoint(bouton.width(), 0)).x()
    assert droite >= page.onglets.mapTo(page, QPoint(page.onglets.width(), 0)).x() - 1  # tout à droite


def test_le_bouton_ouvre_les_conseils(fenetre, qtbot, monkeypatch):
    ouvertes: list[DialogueConseils] = []
    monkeypatch.setattr(DialogueConseils, "exec", lambda self: ouvertes.append(self) or 0)
    fenetre.show()
    bouton = fenetre.page("transcription").sans_projet.bouton_conseils
    qtbot.mouseClick(bouton, Qt.MouseButton.LeftButton)
    (dialogue,) = ouvertes
    assert dialogue.page is PAGES["transcription"]
    assert dialogue.windowTitle() == "Transcription / Conseils"
    assert dialogue.parent() is fenetre


def test_fenetre_des_conseils(app_configuree, qtbot):
    dialogue = DialogueConseils(PAGES["voix"])
    qtbot.addWidget(dialogue)
    textes = dialogue.conseils()
    assert textes == [c for rubrique in PAGES["voix"].rubriques for c in rubrique.conseils]
    assert CONSEILS_STYLE[0].francais in textes
    intitules = {e.text() for e in dialogue.findChildren(QLabel) if e.property("role") == "intitule"}
    assert {i.replace("\u00a0", " ") for i in intitules} == {rubrique.titre for rubrique in PAGES["voix"].rubriques}
    # Espaces insécables à la française : « « » et « : » ne restent jamais seuls en bout de ligne.
    affiches = [e.text() for e in dialogue.findChildren(QLabel)]
    assert any("«\u00a0warm and enthusiastic, fast-paced\u00a0»" in texte for texte in affiches)
    assert "Styles\u00a0: les conseils de Google" in intitules
    dialogue.show()
    assert not dialogue.grab().isNull()


def test_plus_de_bloc_conseils_google_sous_le_script(fenetre):
    atelier = fenetre.page("voix").atelier
    textes = {e.text() for e in atelier.findChildren(QLabel)}
    assert "Conseils Google pour les styles" not in textes
    assert not any(conseil.anglais in texte for conseil in CONSEILS_STYLE for texte in textes)


def test_fenetres_avec_bouton_conseils(app_configuree, qtbot, services):
    from ugc_studio.styles import Style
    from ugc_studio.ui.dialogues.assistant_style import DialogueAssistantStyle
    from ugc_studio.ui.dialogues.assistant_voix import DialogueAssistantVoix
    from ugc_studio.ui.dialogues.cle_api import DialogueCle
    from ugc_studio.ui.dialogues.styles import DialogueBibliothequeStyles, DialogueStyle

    for dialogue, cle in (
        (DialogueAssistantStyle(), "assistant-style"),
        (DialogueAssistantVoix(), "assistant-description"),
        (DialogueCle(services.connexions), "cle-api"),
        (DialogueStyle(services, Style("", "", "", "", voix="Leda")), "style"),
        (DialogueBibliothequeStyles(services), "bibliotheque-styles"),
    ):
        qtbot.addWidget(dialogue)
        (bouton,) = _boutons_conseils(dialogue)
        assert bouton.property("conseils") == cle
        # Plus de colonne « Conseils Google » en anglais à côté du formulaire.
        assert "Conseils Google" not in {e.text() for e in dialogue.findChildren(QLabel)}
