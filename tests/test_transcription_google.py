"""Transcription avec Google (§6) : dépôt du fichier (API Files), options, mots horodatés."""

import json

import pytest

from serveur_factice import ServeurFactice
from ugc_studio.fournisseurs.base import ErreurFournisseur
from ugc_studio.fournisseurs.google import AdaptateurGoogle, config_transcription, lire_resultat_transcription, secondes
from ugc_studio.fournisseurs.stt import MotTranscrit, RequeteTranscription

CLE = "AIza" + "D" * 35
AUDIO = b"RIFF" + b"\x00" * 60


@pytest.fixture
def serveur():
    s = ServeurFactice()
    yield s
    s.arreter()


def _reponse_transcription(**extra):
    return {
        "status": "completed",
        "steps": [
            {"type": "user_input", "content": [{"type": "audio", "uri": "…"}]},
            {
                "type": "model_output",
                "content": [
                    {
                        "type": "text",
                        "text": "Franchement, je n'y croyais pas.",
                        "annotations": [
                            {"type": "word_info", "text": "Franchement,", "speaker": "spk_1", "start_offset": "0.100s", "end_offset": "0.720s"},
                            {"type": "word_info", "text": "je", "speaker": "spk_1", "start_offset": "0.800s", "end_offset": "0.900s"},
                            {"type": "word_info", "text": "n'y", "speaker": "spk_1", "start_offset": "0.900s", "end_offset": "1.050s"},
                            {"type": "word_info", "text": "croyais", "speaker": "spk_2", "start_offset": "1.050s", "end_offset": "1.500s"},
                            {"type": "word_info", "text": "pas.", "speaker": "spk_2", "start_offset": "1.500s", "end_offset": "1.800s"},
                        ],
                    }
                ],
            },
        ],
        "usage": {"total_input_tokens": 50, "total_output_tokens": 12},
        **extra,
    }


def _programmer_depot(serveur, etat="ACTIVE"):
    serveur.programmer(200, {}, {"X-Goog-Upload-URL": f"{serveur.url}/upload/session-1"})
    serveur.programmer(
        200, {"file": {"name": "files/abc123", "uri": "https://exemple/files/abc123", "mimeType": "audio/wav", "state": etat}}
    )


def test_transcription_complete(serveur):
    _programmer_depot(serveur)
    serveur.programmer(200, _reponse_transcription())
    serveur.programmer(200, {})  # suppression du fichier déposé
    requete = RequeteTranscription("gemini-3.5-transcribe", AUDIO, langue="fr-FR", separation_voix=True, nom="Sérum.wav")
    resultat = AdaptateurGoogle(CLE, url_api=serveur.url).transcrire(requete)

    depart, envoi, transcription, suppression = serveur.requetes
    # 1. Début du dépôt : taille et type annoncés, clé dans l'en-tête.
    assert (depart["methode"], depart["chemin"]) == ("POST", "/upload/files")
    assert depart["entetes"]["x-goog-upload-protocol"] == "resumable"
    assert depart["entetes"]["x-goog-upload-command"] == "start"
    assert depart["entetes"]["x-goog-upload-header-content-length"] == str(len(AUDIO))
    assert depart["entetes"]["x-goog-upload-header-content-type"] == "audio/wav"
    assert depart["entetes"]["x-goog-api-key"] == CLE
    assert json.loads(depart["corps"]) == {"file": {"display_name": "Sérum.wav"}}
    # 2. Envoi des octets à l'adresse donnée par Google.
    assert (envoi["chemin"], envoi["corps"]) == ("/upload/session-1", AUDIO)
    assert envoi["entetes"]["x-goog-upload-command"] == "upload, finalize"
    assert envoi["entetes"]["x-goog-upload-offset"] == "0"
    # 3. Transcription du fichier déposé, avec les options.
    assert transcription["chemin"] == "/interactions"
    corps = json.loads(transcription["corps"])
    assert corps["input"] == [{"type": "audio", "uri": "https://exemple/files/abc123", "mime_type": "audio/wav"}]
    assert corps["generation_config"]["transcription_config"] == {
        "language_codes": ["fr-FR"],
        "mode": {"type": "verbatim", "timestamp_granularities": ["word"], "diarization_mode": "speaker"},
    }
    # 4. Le fichier déposé est supprimé.
    assert (suppression["methode"], suppression["chemin"]) == ("DELETE", "/files/abc123")

    assert resultat.texte == "Franchement, je n'y croyais pas."
    assert resultat.mots[0] == MotTranscrit("Franchement,", 0.1, 0.72, "spk_1")
    assert [m.locuteur for m in resultat.mots] == ["spk_1", "spk_1", "spk_1", "spk_2", "spk_2"]
    assert (resultat.tokens_entree, resultat.tokens_sortie) == (50, 12)


def test_options_de_transcription():
    base = RequeteTranscription("m", AUDIO)
    assert config_transcription(base) == {"language_codes": [], "mode": {"type": "verbatim", "timestamp_granularities": ["word"]}}
    smart = RequeteTranscription("m", AUDIO, mode="smart", separation_voix=True, langue="en-US")
    # Le mode « smart » (texte seul) n'accepte ni les temps ni la séparation des voix.
    assert config_transcription(smart) == {"language_codes": ["en-US"], "mode": "smart"}


def test_fichier_en_preparation_puis_pret(serveur, monkeypatch):
    from ugc_studio.fournisseurs import google

    monkeypatch.setattr(google, "ATTENTE_FICHIER_PRET", 0)
    _programmer_depot(serveur, etat="PROCESSING")
    serveur.programmer(200, {"name": "files/abc123", "uri": "https://exemple/files/abc123", "state": "ACTIVE"})
    serveur.programmer(200, _reponse_transcription())
    serveur.programmer(200, {})
    resultat = AdaptateurGoogle(CLE, url_api=serveur.url).transcrire(RequeteTranscription("m", AUDIO))
    assert serveur.requetes[2]["methode"] == "GET" and serveur.requetes[2]["chemin"] == "/files/abc123"
    assert len(resultat.mots) == 5


def test_fichier_supprime_meme_si_la_transcription_echoue(serveur):
    _programmer_depot(serveur)
    serveur.programmer(400, {"error": {"code": 400, "message": "custom_vocabulary is incompatible with timestamps."}})
    serveur.programmer(200, {})
    with pytest.raises(ErreurFournisseur, match="incompatible"):
        AdaptateurGoogle(CLE, url_api=serveur.url).transcrire(RequeteTranscription("m", AUDIO))
    assert serveur.requetes[-1]["methode"] == "DELETE"


def test_depot_refuse(serveur):
    serveur.programmer(403, {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "denied"}})
    with pytest.raises(ErreurFournisseur) as erreur:
        AdaptateurGoogle(CLE, url_api=serveur.url).transcrire(RequeteTranscription("m", AUDIO))
    assert erreur.value.code == "acces_refuse"


def test_adresse_de_depot_de_google():
    adaptateur = AdaptateurGoogle(CLE)
    assert adaptateur._url_televersement == "https://generativelanguage.googleapis.com/upload/v1beta"


def test_formats_des_temps():
    assert secondes("1.250s") == 1.25
    assert secondes(2) == 2.0
    assert secondes({"seconds": 3, "nanos": 500_000_000}) == 3.5
    assert secondes("") == 0.0 and secondes("abc") == 0.0


def test_transcription_sans_mots_horodates():
    """Mode « smart » : le texte seul, sans temps."""
    donnees = {"status": "completed", "output_text": "Bonjour à tous.", "usage": {"total_input_tokens": 9}}
    resultat = lire_resultat_transcription(donnees)
    assert (resultat.texte, resultat.mots, resultat.tokens_entree) == ("Bonjour à tous.", [], 9)


def test_transcription_en_echec():
    with pytest.raises(ErreurFournisseur, match="failed"):
        lire_resultat_transcription({"status": "failed", "errors": [{"message": "Audio too long"}]})
