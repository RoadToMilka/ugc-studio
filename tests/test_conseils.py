"""Bouton « Conseils » (V1.1) : dans le bandeau pour chaque module (V3.1), en haut à droite des
fenêtres ; il ouvre les conseils de la page, en français."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QFrame, QLabel

from ugc_studio.connexions import CoffreMemoire
from ugc_studio.conseils import CONSEILS_STYLE
from ugc_studio.conseils_des_pages import PAGES
from ugc_studio.services import creer_services
from ugc_studio.ui.composants.bouton import Bouton
from ugc_studio.ui.composants.conseils import TEXTE_BOUTON, DialogueConseils
from ugc_studio.ui.fenetre_principale import FenetrePrincipale
from ugc_studio.ui.theme import Espacements


def _boutons_conseils(racine) -> list[Bouton]:
    return [b for b in racine.findChildren(Bouton) if b.text() == TEXTE_BOUTON]


@pytest.fixture
def fenetre(app_configuree, qtbot):
    fenetre = FenetrePrincipale(creer_services(CoffreMemoire()))
    qtbot.addWidget(fenetre)
    return fenetre


def test_chaque_module_a_son_bouton_conseils(fenetre, tmp_path):
    """Dans chaque module, avec ou sans projet ouvert : le bandeau montre le bouton « Conseils » de
    la page affichée, qui ouvre les conseils du module (V3.1 : il quitte le haut de la page)."""
    for avec_projet in (False, True):
        if avec_projet:
            fenetre.services.projets.creer("Sérum", tmp_path)
        for module in ("script", "voix", "transcription", "sous-titres", "reglages"):
            fenetre.afficher_module(module)
            entete = fenetre.entete.entete_affichee()
            assert entete is fenetre.page_affichee().entete, (module, avec_projet)
            bouton = entete.conseils
            assert bouton is fenetre.page_affichee().bouton_conseils
            assert bouton.property("conseils") == module and bouton.variante == "contour"
            assert bouton.text() == TEXTE_BOUTON


def test_conseils_dans_le_bandeau_au_bout_du_titre(fenetre):
    """Le bouton est au bout de la partie titre du bandeau, juste avant la ligne verticale qui la
    sépare du coût de la session, centré en hauteur."""
    fenetre.show()
    fenetre.afficher_module("reglages")
    page, entete = fenetre.page("reglages"), fenetre.entete
    bouton = page.bouton_conseils
    assert entete.isAncestorOf(bouton) and not page.isAncestorOf(bouton)
    assert abs(bouton.mapTo(entete, QPoint(0, bouton.height() // 2)).y() - entete.height() // 2) <= 1
    (ligne,) = [f for f in entete.findChildren(QFrame) if f.property("role") == "separateur-vertical"]
    droite = bouton.mapTo(entete, QPoint(bouton.width(), 0)).x()
    assert ligne.mapTo(entete, QPoint(0, 0)).x() == droite + Espacements.L  # juste avant la ligne
    titre = page.titre
    assert titre.text() == "Réglages" and entete.isAncestorOf(titre)
    assert titre.mapTo(entete, QPoint(titre.width(), 0)).x() <= bouton.mapTo(entete, QPoint(0, 0)).x()


def test_le_bouton_ouvre_les_conseils(fenetre, qtbot, monkeypatch):
    ouvertes: list[DialogueConseils] = []
    monkeypatch.setattr(DialogueConseils, "exec", lambda self: ouvertes.append(self) or 0)
    fenetre.show()
    fenetre.afficher_module("transcription")
    bouton = fenetre.page("transcription").sans_projet.bouton_conseils
    qtbot.mouseClick(bouton, Qt.MouseButton.LeftButton)
    (dialogue,) = ouvertes
    assert dialogue.page is PAGES["transcription"]
    assert dialogue.windowTitle() == "Transcription • Conseils"
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
