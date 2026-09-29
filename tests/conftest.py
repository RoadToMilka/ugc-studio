"""Préparation commune à tous les tests."""

import os

import pytest

# Les tests d'interface tournent sans écran (fenêtres dessinées en mémoire) et sans son.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("UGC_STUDIO_SANS_AUDIO", "1")


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


@pytest.fixture
def services(dossier_donnees_temporaire):
    """Services de l'app (clés, prix, coûts) dans le dossier temporaire, avec un coffre-fort en mémoire."""
    from ugc_studio.connexions import CoffreMemoire
    from ugc_studio.services import creer_services

    return creer_services(CoffreMemoire())
