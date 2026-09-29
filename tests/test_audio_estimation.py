"""Audio WAV et estimation de la durée / du coût avant génération."""

from decimal import Decimal

import pytest

from ugc_studio.audio import concatener_wav, duree_wav, en_wav, lire_wav, wav_depuis_pcm
from ugc_studio.estimation import (
    ajuster_tokens_par_seconde,
    decouper_si_trop_long,
    duree_parlee,
    estimer,
    tokens_texte,
)
from ugc_studio.prix import CataloguePrix

UNE_SECONDE = b"\x01\x00" * 24_000


def test_wav():
    wav = wav_depuis_pcm(UNE_SECONDE)
    assert wav[:4] == b"RIFF"
    assert duree_wav(wav) == pytest.approx(1.0)
    assert en_wav(wav) == wav  # déjà un WAV : inchangé
    assert en_wav(UNE_SECONDE)[:4] == b"RIFF"
    pcm, frequence, canaux = lire_wav(wav)
    assert (pcm, frequence, canaux) == (UNE_SECONDE, 24_000, 1)


def test_recoller_des_morceaux():
    wav = concatener_wav([wav_depuis_pcm(UNE_SECONDE), wav_depuis_pcm(UNE_SECONDE)], silence_s=0.5)
    assert duree_wav(wav) == pytest.approx(2.5)


def test_duree_parlee():
    assert duree_parlee("") == 0
    # 27 mots ≈ 10 s, + une pause longue (1,2 s) + un rire (0,6 s)
    texte = " ".join(["mot"] * 27) + " <long pause> <laugh>"
    assert duree_parlee(texte) == pytest.approx(10 + 1.2 + 0.6)


def test_estimation_du_cout(tmp_path):
    prix = CataloguePrix(tmp_path / "prix.json")
    prix.definir_taux(Decimal("1"))
    estimation = estimer(" ".join(["mot"] * 27), "", "gemini-3.8-flash-tts", prix, tokens_par_seconde=32)
    assert estimation.tokens_entree == tokens_texte(" ".join(["mot"] * 27))
    assert estimation.tokens_sortie == 320  # 10 s × 32 tokens/s
    assert estimation.cout_eur == prix.cout_eur("gemini-3.8-flash-tts", estimation.tokens_entree, 320)


def test_calibrage_des_tokens_audio():
    # Mesure réelle : 250 tokens pour 10 s → 25 tokens/s ; la moyenne s'en rapproche.
    nouveau = ajuster_tokens_par_seconde(32.0, 250, 10.0)
    assert 25 < nouveau < 32
    assert ajuster_tokens_par_seconde(32.0, 0, 10.0) == 32.0


def test_script_long_decoupe_aux_fins_de_phrases():
    phrase = " ".join(["mot"] * 50) + ". "
    texte = phrase * 200  # ≈ 10 000 mots, bien au-delà d'une seule requête
    morceaux = decouper_si_trop_long(texte, 32)
    assert len(morceaux) > 1
    assert all(m.endswith(".") for m in morceaux)
    assert "".join(morceaux).replace(" ", "") == texte.replace(" ", "")
    assert decouper_si_trop_long("Court.", 32) == ["Court."]
