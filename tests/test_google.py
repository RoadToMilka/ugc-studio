"""Adaptateur Google : requêtes envoyées et traduction des erreurs (avec un serveur local factice)."""

import base64
import json

import pytest

from serveur_factice import ServeurFactice
from ugc_studio.audio import wav_depuis_pcm
from ugc_studio.fournisseurs.base import ErreurFournisseur
from ugc_studio.fournisseurs.google import AdaptateurGoogle, lire_resultat_voix
from ugc_studio.fournisseurs.voix import Replique, RequeteVoix

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


# --- Génération de voix (API Interactions, Gemini 3.8 TTS) -------------------------------------

PCM = b"\x10\x00" * 12_000  # 0,5 s


def _reponse_audio(donnees: bytes, **extra):
    return {
        "status": "completed",
        "steps": [
            {"type": "user_input", "content": [{"type": "text", "text": "…"}]},
            {"type": "model_output", "content": [{"type": "audio", "mime_type": "audio/wav", "data": base64.b64encode(donnees).decode()}]},
        ],
        "usage": {"total_input_tokens": 12, "total_output_tokens": 16},
        **extra,
    }


def test_requete_de_voix(serveur):
    serveur.programmer(200, _reponse_audio(wav_depuis_pcm(PCM)))
    requete = RequeteVoix("gemini-3.8-flash-tts", "Kore", (Replique("Salut <laugh>", "chaleureux"),))
    resultat = AdaptateurGoogle(CLE, url_api=serveur.url).generer_voix(requete)
    envoi = serveur.requetes[0]
    assert (envoi["methode"], envoi["chemin"]) == ("POST", "/interactions")
    corps = json.loads(envoi["corps"])
    assert corps == {
        "model": "gemini-3.8-flash-tts",
        "input": [
            {
                "type": "text",
                "text": "Salut <laugh>",
                "annotations": [{"type": "speech_metadata", "style": "chaleureux"}],
            }
        ],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": "Kore"}]},
    }
    assert resultat.duree_s == pytest.approx(0.5)
    assert (resultat.tokens_entree, resultat.tokens_sortie) == (12, 16)


def test_sans_style_pas_d_annotation(serveur):
    serveur.programmer(200, _reponse_audio(wav_depuis_pcm(PCM)))
    AdaptateurGoogle(CLE, url_api=serveur.url).generer_voix(RequeteVoix("m", "Puck", (Replique("Bonjour"),)))
    assert "annotations" not in json.loads(serveur.requetes[0]["corps"])["input"][0]


def test_audio_brut_enveloppe_en_wav():
    resultat = lire_resultat_voix(
        {"status": "completed", "output_audio": {"type": "audio", "mime_type": "audio/l16", "sample_rate": 24000, "data": base64.b64encode(PCM).decode()}}
    )
    assert resultat.audio_wav[:4] == b"RIFF"
    assert resultat.duree_s == pytest.approx(0.5)


def test_tokens_de_reflexion_comptes_en_sortie():
    donnees = _reponse_audio(wav_depuis_pcm(PCM))
    donnees["usage"]["total_thought_tokens"] = 4
    assert lire_resultat_voix(donnees).tokens_sortie == 20


def test_generation_en_echec():
    with pytest.raises(ErreurFournisseur, match="failed"):
        lire_resultat_voix({"status": "failed", "errors": [{"message": "Voice not found"}]})
    with pytest.raises(ErreurFournisseur, match="aucun audio"):
        lire_resultat_voix({"status": "completed", "steps": []})


def test_nouvel_essai_si_google_surcharge(serveur, monkeypatch):
    from ugc_studio.fournisseurs import google

    monkeypatch.setattr(google, "PAUSE_AVANT_NOUVEL_ESSAI", 0)
    serveur.programmer(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "overloaded"}})
    serveur.programmer(200, _reponse_audio(wav_depuis_pcm(PCM)))
    resultat = AdaptateurGoogle(CLE, url_api=serveur.url).generer_voix(RequeteVoix("m", "Kore", (Replique("a"),)))
    assert resultat.duree_s > 0
    assert len(serveur.requetes) == 2


# --- Texte (API Interactions, ex. Gemini 3.8 Flash) : traduction des styles -------------------


def _reponse_texte(texte: str):
    return {
        "status": "completed",
        "steps": [
            {"type": "user_input", "content": [{"type": "text", "text": "…"}]},
            {"type": "thought", "summary": [{"type": "text", "text": "Translating…"}]},
            {"type": "model_output", "content": [{"type": "text", "text": texte}]},
        ],
        "usage": {"total_input_tokens": 90, "total_output_tokens": 8, "total_thought_tokens": 30},
    }


def test_requete_de_texte(serveur):
    from ugc_studio.fournisseurs.texte import RequeteTexte

    serveur.programmer(200, _reponse_texte("warm and enthusiastic, fast-paced"))
    resultat = AdaptateurGoogle(CLE, url_api=serveur.url).generer_texte(
        RequeteTexte("gemini-3.8-flash", "chaleureux et enthousiaste, débit rapide", "Translate.", "low")
    )
    corps = json.loads(serveur.requetes[0]["corps"])
    assert corps == {
        "model": "gemini-3.8-flash",
        "input": [{"type": "text", "text": "chaleureux et enthousiaste, débit rapide"}],
        "generation_config": {"thinking_level": "low"},
        "system_instruction": "Translate.",
    }
    assert resultat.texte == "warm and enthusiastic, fast-paced"
    assert (resultat.tokens_entree, resultat.tokens_sortie) == (90, 38)  # réflexion comptée en sortie


def test_texte_des_dernieres_etapes_seulement():
    from ugc_studio.fournisseurs.google import trouver_texte

    donnees = _reponse_texte("fin")
    donnees["steps"][2]["content"] = [{"type": "text", "text": "début "}, {"type": "text", "text": "fin"}]
    assert trouver_texte(donnees) == "début fin"
    assert trouver_texte({"output_text": "direct"}) == "direct"
    with pytest.raises(ErreurFournisseur, match="aucun texte"):
        from ugc_studio.fournisseurs.google import lire_resultat_texte

        lire_resultat_texte({"status": "completed", "steps": []})


def test_traduction_d_un_style(serveur):
    from ugc_studio.traduction import MODELE_TRADUCTION, traduire_en_anglais

    serveur.programmer(200, _reponse_texte('"whispered and playful"\n'))
    resultat = traduire_en_anglais(AdaptateurGoogle(CLE, url_api=serveur.url), "  chuchoté,   complice ")
    assert resultat.texte == "whispered and playful"  # guillemets et retour à la ligne retirés
    corps = json.loads(serveur.requetes[0]["corps"])
    assert corps["model"] == MODELE_TRADUCTION == "gemini-3.8-flash"
    assert corps["input"][0]["text"] == "chuchoté, complice"
    assert "English" in corps["system_instruction"]
