"""Le journal d'erreurs ne doit jamais contenir de clé API (§10)."""

import io
import logging
import sys
import threading

from ugc_studio import journal
from ugc_studio.journal import MASQUE, FormateurMasque, configurer_journal, declarer_secret, masquer

CLE_GOOGLE = "AIza" + "S" * 20 + "x1y2z3_-abcdefg"  # 39 caractères, format d'une clé Google


def test_cle_google_masquee():
    texte = masquer(f"Appel avec la clé {CLE_GOOGLE} refusé")
    assert CLE_GOOGLE not in texte
    assert MASQUE in texte


def test_parametre_key_dans_une_adresse():
    texte = masquer("https://exemple.com/v1beta/models?key=abcdef123456&alt=json")
    assert "abcdef123456" not in texte
    assert "key=" + MASQUE in texte
    assert "&alt=json" in texte


def test_entetes_http():
    texte = masquer("x-goog-api-key: supersecret99\nAuthorization: Bearer eyJhbGciOi.abc.def")
    assert "supersecret99" not in texte
    assert "eyJhbGciOi" not in texte


def test_secret_declare_masque_partout():
    declarer_secret("mon-secret-tres-particulier")
    assert "particulier" not in masquer("valeur=mon-secret-tres-particulier ; fin")


def test_texte_ordinaire_intact():
    texte = "Génération terminée : 1234 tokens, 0.007 €"
    assert masquer(texte) == texte


def test_trace_erreur_masquee():
    flux = io.StringIO()
    gestionnaire = logging.StreamHandler(flux)
    gestionnaire.setFormatter(FormateurMasque("%(message)s"))
    enregistreur = logging.getLogger("test_trace_erreur_masquee")
    enregistreur.addHandler(gestionnaire)
    try:
        raise ValueError(f"clé refusée : {CLE_GOOGLE}")
    except ValueError:
        enregistreur.exception("Échec")
    finally:
        enregistreur.removeHandler(gestionnaire)
    assert CLE_GOOGLE not in flux.getvalue()
    assert "ValueError" in flux.getvalue()


def test_fichier_journal(tmp_path, monkeypatch):
    # configurer_journal remplace les « crochets » d'erreurs de Python : on les restaure après le test.
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    fichier = tmp_path / "journal" / "ugc-studio.log"
    configurer_journal(fichier)
    logging.getLogger("ugc_studio.test").warning("Essai avec %s", CLE_GOOGLE)
    for gestionnaire in logging.getLogger().handlers:
        gestionnaire.flush()
    contenu = fichier.read_text(encoding="utf-8")
    assert "Essai avec" in contenu
    assert CLE_GOOGLE not in contenu
    # Remettre le module dans son état initial pour les autres tests.
    logging.getLogger().removeHandler(journal._gestionnaire)
    journal._gestionnaire.close()
    journal._gestionnaire = None
