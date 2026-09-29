"""Adaptateur Google : requêtes envoyées et traduction des erreurs (avec un serveur local factice)."""

import pytest

from serveur_factice import ServeurFactice
from ugc_studio.fournisseurs.google import AdaptateurGoogle

CLE = "AIza" + "B" * 35


@pytest.fixture
def serveur():
    s = ServeurFactice()
    yield s
    s.arreter()


def _modele(nom, methodes=("generateContent",)):
    return {"name": f"models/{nom}", "displayName": nom.upper(), "supportedGenerationMethods": list(methodes)}


def test_liste_des_modeles_sur_plusieurs_pages(serveur):
    serveur.programmer(200, {"models": [_modele("gemini-3.8-flash-tts")], "nextPageToken": "page2"})
    serveur.programmer(200, {"models": [_modele("gemini-3.5-transcribe")]})
    modeles = AdaptateurGoogle(CLE, url_api=serveur.url).lister_modeles()
    assert [m.identifiant for m in modeles] == ["gemini-3.8-flash-tts", "gemini-3.5-transcribe"]
    assert modeles[0].nom == "GEMINI-3.8-FLASH-TTS"
    premiere, seconde = serveur.requetes
    assert premiere["chemin"] == "/models?pageSize=1000"
    assert seconde["chemin"] == "/models?pageSize=1000&pageToken=page2"


def test_cle_envoyee_dans_l_entete_jamais_dans_l_adresse(serveur):
    serveur.programmer(200, {"models": []})
    AdaptateurGoogle(CLE, url_api=serveur.url).lister_modeles()
    requete = serveur.requetes[0]
    assert requete["entetes"].get("x-goog-api-key") == CLE
    assert CLE not in requete["chemin"]


def test_test_de_cle_reussi(serveur):
    serveur.programmer(200, {"models": [_modele("a"), _modele("b")]})
    resultat = AdaptateurGoogle(CLE, url_api=serveur.url).tester_cle()
    assert resultat.ok
    assert "2 modèles" in resultat.message


@pytest.mark.parametrize(
    ("code", "corps", "code_attendu", "extrait"),
    [
        (
            400,
            {
                "error": {
                    "code": 400,
                    "message": "API key not valid. Please pass a valid API key.",
                    "status": "INVALID_ARGUMENT",
                    "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID"}],
                }
            },
            "cle_invalide",
            "pas valide",
        ),
        (403, {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "denied"}}, "acces_refuse", "accès"),
        (429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota"}}, "quota", "Limite"),
        (503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "overloaded"}}, "serveur", "temporaire"),
        (400, {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "Bad field"}}, "requete", "Bad field"),
    ],
)
def test_erreurs_traduites(serveur, code, corps, code_attendu, extrait):
    serveur.programmer(code, corps)
    resultat = AdaptateurGoogle(CLE, url_api=serveur.url).tester_cle()
    assert not resultat.ok
    assert resultat.code == code_attendu
    assert extrait in resultat.message


def test_serveur_injoignable():
    # Port 9 (« discard ») : personne n'écoute, la connexion échoue immédiatement.
    resultat = AdaptateurGoogle(CLE, url_api="http://127.0.0.1:9").tester_cle()
    assert not resultat.ok
    assert resultat.code == "reseau"
    assert "connexion Internet" in resultat.message
