"""Écoute pendant la génération (§5.6) : réponse « en flux » de Google, lue morceau par morceau."""

import base64
import json
from array import array

import pytest

from serveur_factice import ServeurFactice
from ugc_studio.audio import FREQUENCE_TTS, lire_wav, wav_depuis_pcm
from ugc_studio.audio_flux import FORMAT_TTS, Convertisseur, FormatAudio
from ugc_studio.fournisseurs.base import Adaptateur, ErreurFournisseur
from ugc_studio.fournisseurs.google import AdaptateurGoogle, lire_flux_voix, pcm_du_morceau
from ugc_studio.fournisseurs.http import EvenementSse, lire_sse
from ugc_studio.fournisseurs.voix import Replique, RequeteVoix, ResultatVoix
from ugc_studio.generation import PAUSE_ENTRE_MORCEAUX_S, preparer, produire_audio
from ugc_studio.projets import RepliqueProjet

CLE = "AIza" + "C" * 35
PCM_1 = array("h", [100] * 2400).tobytes()  # 0,1 s
PCM_2 = array("h", [-100] * 4800).tobytes()  # 0,2 s


@pytest.fixture
def serveur():
    s = ServeurFactice()
    yield s
    s.arreter()


def _sse(*evenements: dict) -> bytes:
    """Corps d'une réponse « text/event-stream », comme celle de l'API Interactions."""
    lignes = []
    for evenement in evenements:
        lignes.append(f"event: {evenement['event_type']}")
        lignes.append(f"data: {json.dumps(evenement)}")
        lignes.append("")
    lignes += ["event: done", "data: [DONE]", "", ""]
    return "\n".join(lignes).encode("utf-8")


def _morceau(pcm: bytes, **champs) -> dict:
    delta = {"type": "audio", "mime_type": "audio/l16", "data": base64.b64encode(pcm).decode(), **champs}
    return {"index": 0, "delta": delta, "event_type": "step.delta"}


FIN = {
    "interaction": {"id": "i1", "status": "completed", "usage": {"total_input_tokens": 12, "total_output_tokens": 8}},
    "event_type": "interaction.completed",
}


def test_evenements_d_un_flux():
    lignes = [
        b": maintien de la connexion\n",
        b"event: step.delta\n",
        b'data: {"a": 1,\n',
        b'data:  "b": 2}\n',
        b"\n",
        b"data: [DONE]\r\n",
    ]
    assert list(lire_sse(lignes)) == [
        EvenementSse("step.delta", '{"a": 1,\n "b": 2}'),
        EvenementSse("", "[DONE]"),  # dernier événement sans ligne vide finale
    ]


def test_voix_en_flux(serveur):
    serveur.programmer(
        200,
        _sse(
            {"interaction": {"id": "i1", "status": "in_progress"}, "event_type": "interaction.created"},
            {"index": 0, "step": {"type": "model_output"}, "event_type": "step.start"},
            _morceau(PCM_1, sample_rate=24000, channels=1),
            _morceau(PCM_2, sample_rate=24000, channels=1),
            {"index": 0, "event_type": "step.stop"},
            FIN,
        ),
        {"Content-Type": "text/event-stream"},
    )
    recus = []
    requete = RequeteVoix("gemini-3.8-flash-tts", "Kore", (Replique("Salut", "chaleureux"),))
    resultat = AdaptateurGoogle(CLE, url_api=serveur.url).generer_voix(requete, lambda pcm, f: recus.append((pcm, f)))

    envoi = serveur.requetes[0]
    assert json.loads(envoi["corps"])["stream"] is True
    assert envoi["entetes"]["accept"] == "text/event-stream"
    assert envoi["entetes"]["x-goog-api-key"] == CLE
    # Chaque morceau est transmis dès son arrivée, dans l'ordre…
    assert recus == [(PCM_1, 24000), (PCM_2, 24000)]
    # … et la prise complète les réunit, avec les tokens de l'événement final (pour le coût).
    pcm, frequence, canaux = lire_wav(resultat.audio_wav)
    assert (pcm, frequence, canaux) == (PCM_1 + PCM_2, 24000, 1)
    assert resultat.duree_s == pytest.approx(0.3)
    assert (resultat.tokens_entree, resultat.tokens_sortie) == (12, 8)


def test_erreur_en_cours_de_flux(serveur):
    serveur.programmer(
        200,
        _sse(_morceau(PCM_1), {"error": {"message": "Internal error", "code": "internal"}, "event_type": "error"}),
    )
    recus = []
    with pytest.raises(ErreurFournisseur) as erreur:
        AdaptateurGoogle(CLE, url_api=serveur.url).generer_voix(
            RequeteVoix("m", "Kore", (Replique("a"),)), lambda pcm, f: recus.append(pcm)
        )
    assert erreur.value.code == "generation" and "Internal error" in erreur.value.message
    assert recus == [PCM_1]  # le début a déjà été entendu


def test_flux_coupe_avant_la_fin():
    evenements = [EvenementSse("step.delta", json.dumps(_morceau(PCM_1)))]
    with pytest.raises(ErreurFournisseur) as erreur:
        lire_flux_voix(evenements, lambda pcm, f: None)
    assert erreur.value.code == "reseau"


def test_generation_en_echec_signalee_a_la_fin():
    fin = {"interaction": {"status": "failed", "errors": [{"message": "Voice not found"}]}, "event_type": "interaction.completed"}
    evenements = [EvenementSse("", json.dumps(e)) for e in (_morceau(PCM_1), fin)]
    with pytest.raises(ErreurFournisseur, match="Voice not found"):
        lire_flux_voix(evenements, lambda pcm, f: None)


def test_audio_seulement_dans_la_reponse_finale():
    """Aucun morceau en route : l'audio de la réponse finale est utilisé."""
    fin = {
        "interaction": {
            "status": "completed",
            "steps": [{"type": "model_output", "content": [{"type": "audio", "data": base64.b64encode(PCM_2).decode()}]}],
            "usage": {"total_input_tokens": 3, "total_output_tokens": 5},
        },
        "event_type": "interaction.completed",
    }
    resultat = lire_flux_voix([EvenementSse("", json.dumps(fin))], lambda pcm, f: None)
    assert resultat.duree_s == pytest.approx(0.2)


def test_nouvel_essai_si_google_surcharge_avant_le_flux(serveur, monkeypatch):
    from ugc_studio.fournisseurs import google

    monkeypatch.setattr(google, "PAUSE_AVANT_NOUVEL_ESSAI", 0)
    serveur.programmer(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "overloaded"}})
    serveur.programmer(200, _sse(_morceau(PCM_1), FIN))
    resultat = AdaptateurGoogle(CLE, url_api=serveur.url).generer_voix(
        RequeteVoix("m", "Kore", (Replique("a"),)), lambda pcm, f: None
    )
    assert resultat.duree_s == pytest.approx(0.1)
    assert len(serveur.requetes) == 2


def test_cle_refusee_en_flux(serveur):
    serveur.programmer(400, {"error": {"code": 400, "message": "API key not valid.", "details": [{"reason": "API_KEY_INVALID"}]}})
    with pytest.raises(ErreurFournisseur) as erreur:
        AdaptateurGoogle(CLE, url_api=serveur.url).generer_voix(RequeteVoix("m", "Kore", (Replique("a"),)), lambda p, f: None)
    assert erreur.value.code == "cle_invalide"


def test_formats_des_morceaux():
    # Fréquence écrite dans le type (« audio/l16;rate=16000 »).
    donnees = base64.b64encode(PCM_1).decode()
    assert pcm_du_morceau({"data": donnees, "mime_type": "audio/l16;rate=16000"}) == (PCM_1, 16000)
    # Sans précision : 24 kHz, le format du TTS.
    assert pcm_du_morceau({"data": donnees}) == (PCM_1, FREQUENCE_TTS)
    # Morceau au format WAV : on garde les échantillons.
    wav = base64.b64encode(wav_depuis_pcm(PCM_2, 16000)).decode()
    assert pcm_du_morceau({"data": wav, "mime_type": "audio/wav"}) == (PCM_2, 16000)


# --- Génération : transmission des morceaux, y compris pour un script long ----------------------


class FauxFlux(Adaptateur):
    identifiant = "google"
    nom = "Faux"

    def __init__(self):
        super().__init__("cle-de-test-123456")
        self.appels = 0

    def lister_modeles(self):
        return []

    def generer_voix(self, requete, recevoir_audio=None):
        self.appels += 1
        if recevoir_audio is not None:
            recevoir_audio(PCM_1, FREQUENCE_TTS)
        wav = wav_depuis_pcm(PCM_1)
        return ResultatVoix(wav, 0.1, 10, 20)


def test_script_long_ecoute_avec_le_silence_des_morceaux():
    phrase = " ".join(["mot"] * 50) + ". "
    commande = preparer("google", "gemini-3.8-flash-tts", "Kore", [RepliqueProjet([{"texte": phrase * 200}])], None)
    faux = FauxFlux()
    recus = []
    resultat = produire_audio(faux, commande, 25, recevoir_audio=lambda pcm, f: recus.append(pcm))
    assert faux.appels >= 2
    silence = b"\x00" * int(PAUSE_ENTRE_MORCEAUX_S * FREQUENCE_TTS) * 2
    # Entre deux requêtes, le même silence que dans la prise recollée.
    assert recus == [PCM_1] + [silence, PCM_1] * (faux.appels - 1)
    pcm, _, _ = lire_wav(resultat.audio_wav)
    assert pcm == b"".join(recus)


def test_sans_ecoute_pas_de_flux():
    faux = FauxFlux()
    commande = preparer("google", "m", "Kore", [RepliqueProjet([{"texte": "Bonjour"}])], None)
    produire_audio(faux, commande, 25)
    assert faux.appels == 1


# --- Conversion vers le format de la carte son ----------------------------------------------------


def test_convertisseur_sans_changement():
    assert Convertisseur(FORMAT_TTS).convertir(PCM_1) == PCM_1


def test_convertisseur_48_khz_stereo_sans_coupure_entre_morceaux():
    convertisseur = Convertisseur(FormatAudio(48000, 2, "float"))
    rampe = array("h", [0, 1000, 2000, 3000, 4000, 5000]).tobytes()
    # Coupure au milieu d'un échantillon : l'octet isolé attend le morceau suivant.
    sortie = array("f")
    sortie.frombytes(convertisseur.convertir(rampe[:5]) + convertisseur.convertir(rampe[5:]))
    gauche, droite = sortie[::2], sortie[1::2]
    assert list(gauche) == list(droite)  # même son à gauche et à droite
    assert [round(v * 32768) for v in gauche] == [0, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500]


def test_convertisseur_44_1_khz():
    convertisseur = Convertisseur(FormatAudio(44100, 1, "int16"))
    sortie = array("h")
    for debut in range(0, 1000, 100):
        sortie.frombytes(convertisseur.convertir(array("h", range(debut, debut + 100)).tobytes()))
    ecarts = {b - a for a, b in zip(sortie, sortie[1:], strict=False)}
    assert ecarts <= {0, 1}  # la rampe reste régulière, sans saut entre deux morceaux
    assert abs(len(sortie) - 1000 * 44100 / 24000) < 2


def test_convertisseur_entiers_32_et_8_bits():
    valeurs = array("h", [0, 32767, -32768]).tobytes()
    sortie = array("i")
    sortie.frombytes(Convertisseur(FormatAudio(24000, 1, "int32")).convertir(valeurs))
    assert list(sortie) == [0, 32767 << 16, -32768 << 16]
    assert list(Convertisseur(FormatAudio(24000, 1, "uint8")).convertir(valeurs)) == [128, 255, 0]
