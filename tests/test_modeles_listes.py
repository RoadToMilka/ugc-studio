"""Listes « Modèle » des modules (V1.1) : seuls les modèles chargés sont proposés ; le modèle d'un
projet est toujours gardé (et rechargé s'il ne l'était plus)."""

import pytest

from ugc_studio.modeles_charges import VOIX
from ugc_studio.ui.pages.voix import PageVoix

ACCESSIBLES = ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-2.5-pro-preview-tts"]


@pytest.fixture
def atelier(app_configuree, qtbot, services, tmp_path):
    connexion = services.connexions.ajouter("google", "Perso", "AIza-cle-factice-123456")
    services.connexions.enregistrer_test(connexion.identifiant, True, "ok", ACCESSIBLES)
    services.projets.creer("Sérum", tmp_path)
    page = PageVoix(services)
    qtbot.addWidget(page)
    return page.atelier


def _modeles(liste) -> list[str]:
    return [liste.itemData(index) for index in range(liste.count())]


def test_seuls_les_modeles_charges_sont_proposes(atelier, services):
    assert _modeles(atelier.modele) == ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"]
    services.modeles.definir([*services.modeles.charges(), "gemini-2.5-pro-preview-tts"])
    assert "gemini-2.5-pro-preview-tts" in _modeles(atelier.modele)  # la liste suit, sans rouvrir


def test_le_modele_du_projet_est_utilise_dans_voix(atelier, services):
    assert services.modeles.utilise_dans("gemini-3.8-flash-tts") == [VOIX]
    atelier.modele.setCurrentIndex(atelier.modele.findData("gemini-3.8-flash-lite-tts"))
    assert services.modeles.utilise_dans("gemini-3.8-flash-lite-tts") == [VOIX]  # en direct


def test_projet_avec_un_modele_non_charge(app_configuree, qtbot, services, tmp_path):
    """Projet d'une version précédente, avec un ancien modèle : il est gardé et rechargé, sans rien
    changer dans le projet."""
    connexion = services.connexions.ajouter("google", "Perso", "AIza-cle-factice-123456")
    services.connexions.enregistrer_test(connexion.identifiant, True, "ok", ACCESSIBLES)
    projet = services.projets.creer("Ancien", tmp_path)
    projet.voix.modele = "gemini-2.5-pro-preview-tts"
    page = PageVoix(services)
    qtbot.addWidget(page)
    assert page.atelier.modele.currentData() == "gemini-2.5-pro-preview-tts"
    assert services.modeles.est_charge("gemini-2.5-pro-preview-tts")
    assert services.projets.projet.voix.modele == "gemini-2.5-pro-preview-tts"
