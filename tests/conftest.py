"""Préparation commune à tous les tests."""

import os
import sys
from datetime import date

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


# Date « du jour » fixée pendant les tests : les prix de Google changent à des dates annoncées
# (ex. hausse du 01/01/2027), et un test ne doit pas donner un autre résultat selon le jour où il
# est lancé.
AUJOURD_HUI_DES_TESTS = date(2026, 10, 1)


@pytest.fixture(autouse=True)
def date_du_jour_fixe(monkeypatch):
    monkeypatch.setattr("ugc_studio.prix.aujourd_hui", lambda: AUJOURD_HUI_DES_TESTS)
    return AUJOURD_HUI_DES_TESTS


def _fenetres_sans_parent(app) -> dict[int, object]:
    """Fenêtres ouvertes qui n'appartiennent à aucune autre (repérées par leur adresse en mémoire)."""
    import shiboken6

    return {shiboken6.getCppPointer(fenetre)[0]: fenetre for fenetre in app.topLevelWidgets() if fenetre.parent() is None}


@pytest.fixture(autouse=True)
def fenetres_supprimees_apres_le_test():
    """Après chaque test d'interface, les fenêtres qu'il a ouvertes sont vraiment supprimées.

    Pourquoi : pytest-qt ferme les fenêtres d'un test et demande leur suppression « dès que Qt
    reprendra la main » (deleteLater) ; or, entre deux tests, Qt ne reprend jamais la main. Elles
    restaient donc en mémoire, et chaque préparation de l'app (thème, police, avant chaque test) les
    repeignait toutes : les tests ralentissaient au fil de la série (plus de 30 minutes au lot 5).
    Les fenêtres ouvertes sans passer par qtbot sont fermées de la même façon. Une fenêtre qui
    appartient à une autre (liste ouverte d'un menu déroulant…) part avec elle."""
    widgets = sys.modules.get("PySide6.QtWidgets")
    app = widgets.QApplication.instance() if widgets is not None else None
    avant = set(_fenetres_sans_parent(app)) if app is not None else set()
    yield
    widgets = sys.modules.get("PySide6.QtWidgets")
    app = widgets.QApplication.instance() if widgets is not None else None
    if app is None:
        return
    from PySide6.QtCore import QEvent

    for adresse, fenetre in _fenetres_sans_parent(app).items():
        if adresse not in avant:
            fenetre.close()
            fenetre.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


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
