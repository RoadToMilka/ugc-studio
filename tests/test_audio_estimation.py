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
    estimation = estimer(" ".join(["mot"] * 27), "", "gemini-3.8-flash-tts", prix)
    assert estimation.tokens_entree == tokens_texte(" ".join(["mot"] * 27))
    assert estimation.tokens_sortie == 250  # 10 s × 25 tokens/s (valeur de départ, page des tarifs Google)
    assert estimation.cout_eur == prix.cout_eur("gemini-3.8-flash-tts", estimation.tokens_entree, 250)


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


def test_estimation_de_plusieurs_repliques(tmp_path):
    from ugc_studio.estimation import estimer_repliques
    from ugc_studio.fournisseurs.voix import Replique

    prix = CataloguePrix(tmp_path / "prix.json")
    une = estimer_repliques([Replique("Bonjour à toutes et à tous", "warm")], "gemini-3.8-flash-tts", prix)
    deux = estimer_repliques(
        [Replique("Bonjour à toutes et à tous", "warm"), Replique("", "ignored"), Replique("Bonjour à toutes et à tous", "warm")],
        "gemini-3.8-flash-tts",
        prix,
    )
    assert deux.caracteres == 2 * une.caracteres
    assert deux.tokens_entree == 2 * une.tokens_entree  # chaque réplique envoie son style
    assert deux.duree_s == pytest.approx(2 * une.duree_s)


def test_repliques_reparties_en_plusieurs_requetes_si_trop_longues():
    from ugc_studio.estimation import TOKENS_SORTIE_MAX, _trop_long, duree_parlee, regrouper
    from ugc_studio.fournisseurs.voix import Replique

    phrase = " ".join(["mot"] * 50) + ". "
    repliques = [Replique(phrase * 40, f"style {n}") for n in range(4)]
    groupes = regrouper(repliques, 25)
    assert len(groupes) > 1
    assert all(not _trop_long(groupe, 25) for groupe in groupes)
    # Rien n'est perdu, et chaque morceau garde le style de sa réplique.
    assert sum(duree_parlee(r.texte) for g in groupes for r in g) == pytest.approx(
        sum(duree_parlee(r.texte) for r in repliques), rel=0.01
    )
    assert {r.style for g in groupes for r in g} == {f"style {n}" for n in range(4)}
    assert TOKENS_SORTIE_MAX > 0
    assert regrouper([Replique("Court.", "a"), Replique("", "b")], 25) == [(Replique("Court.", "a"),)]
