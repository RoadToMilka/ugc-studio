"""Préparation commune à tous les tests."""

import os

import pytest

# Les tests d'interface tournent sans écran (fenêtres dessinées en mémoire).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def dossier_donnees_temporaire(tmp_path, monkeypatch):
    """Chaque test utilise un dossier de données temporaire : les vraies données ne sont jamais touchées."""
    dossier = tmp_path / "donnees"
    monkeypatch.setenv("UGC_STUDIO_DOSSIER_DONNEES", str(dossier))
    return dossier


@pytest.fixture
def app_configuree(qapp):
    """Application Qt avec le thème, la police et les icônes de UGC Studio."""
    from ugc_studio.app import configurer_application

    configurer_application(qapp)
    return qapp
