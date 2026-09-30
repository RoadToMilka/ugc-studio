"""Étape 8 (§3.3) — prise TTS → sous-titres : le script est calé sur les temps de la transcription."""

import pytest

from ugc_studio.alignement import aligner, cle_d_alignement, mots_du_script
from ugc_studio.transcription import Mot


def _transcrits(*mots: tuple[str, float, float]) -> list[Mot]:
    return [Mot(texte, debut, fin) for texte, debut, fin in mots]


def test_cle_d_alignement():
    assert cle_d_alignement("N'y") == "ny"
    assert cle_d_alignement("Sérum,") == "serum"
    assert cle_d_alignement("ANTI-RIDES®") == "antirides"
    assert cle_d_alignement("…") == ""


def test_mots_du_script_ponctuation_jamais_seule():
    assert mots_du_script("Franchement, je n'y croyais pas… Mais ce sérum a changé ma peau en deux semaines !") == [
        "Franchement,", "je", "n'y", "croyais", "pas…", "Mais", "ce", "sérum", "a", "changé", "ma", "peau",
        "en", "deux", "semaines !",
    ]
    assert mots_du_script("Elle m'a dit « Wahou » !") == ["Elle", "m'a", "dit", "« Wahou » !"]
    assert mots_du_script("") == []


def test_mots_identiques_prennent_les_temps_transcrits():
    script = mots_du_script("Ce Sérum Glowzy est top !")
    transcrits = _transcrits(("ce", 0.1, 0.3), ("sérum", 0.3, 0.7), ("glowzy", 0.7, 1.2), ("est", 1.3, 1.5), ("top", 1.5, 1.9))
    mots = aligner(script, transcrits)
    # L'orthographe du script est gardée (majuscules, ponctuation), avec les temps de la transcription.
    assert [(m.texte, m.debut, m.fin) for m in mots] == [
        ("Ce", 0.1, 0.3), ("Sérum", 0.3, 0.7), ("Glowzy", 0.7, 1.2), ("est", 1.3, 1.5), ("top !", 1.5, 1.9),
    ]


def test_mots_differents_partagent_le_passage_transcrit():
    script = mots_du_script("En 2 semaines seulement")
    transcrits = _transcrits(("en", 0.0, 0.2), ("deux", 0.2, 0.5), ("semaines", 0.5, 1.0), ("seulement", 1.0, 1.6))
    mots = aligner(script, transcrits)
    assert [m.texte for m in mots] == ["En", "2", "semaines", "seulement"]
    assert (mots[1].debut, mots[1].fin) == (0.2, 0.5)
    # Un mot écrit collé mais prononcé en deux (« anti-rides » → « anti », « rides ») prend tout le passage.
    mots = aligner(["anti-rides"], _transcrits(("anti", 1.0, 1.3), ("rides", 1.3, 1.8)))
    assert (mots[0].debut, mots[0].fin) == (1.0, 1.8)


def test_mot_absent_place_dans_le_silence():
    script = mots_du_script("Oui vraiment top")
    transcrits = _transcrits(("oui", 0.0, 0.4), ("top", 1.0, 1.4))
    mots = aligner(script, transcrits)
    assert [m.texte for m in mots] == ["Oui", "vraiment", "top"]
    assert mots[1].debut == pytest.approx(0.4) and mots[1].fin == pytest.approx(1.0)


def test_mot_absent_sans_silence_partage_le_mot_d_avant():
    mots = aligner(["très", "très", "bien"], _transcrits(("très", 0.0, 0.4), ("bien", 0.4, 0.8)))
    assert [m.texte for m in mots] == ["très", "très", "bien"]
    assert mots[0].debut == 0.0 and mots[1].fin <= mots[2].debut == 0.4
    assert all(m.fin > m.debut for m in mots)


def test_mots_absents_au_debut_et_a_la_fin():
    mots = aligner(["Alors", "voilà", "merci"], _transcrits(("voilà", 1.0, 1.4)))
    # « Alors » (5 lettres) : juste avant « voilà », le temps de le dire (5 × 70 ms) ;
    # « merci » : juste après.
    assert (mots[0].debut, mots[0].fin) == (0.65, 1.0)
    assert (mots[2].debut, mots[2].fin) == (1.4, 1.75)
    # Premier mot trop tôt pour loger le mot manquant avant lui : ils se partagent son temps.
    mots = aligner(["Ce", "sérum"], _transcrits(("sérum", 0.0, 0.7)))
    assert mots[0].debut == 0.0 and mots[0].fin == mots[1].debut == 0.2 and mots[1].fin == 0.7


def test_mots_transcrits_en_trop_ignores():
    script = mots_du_script("C'est incroyable")
    transcrits = _transcrits(("haha", 0.0, 0.5), ("c'est", 0.6, 0.8), ("euh", 0.8, 1.0), ("incroyable", 1.0, 1.6))
    mots = aligner(script, transcrits)
    assert [(m.texte, m.debut, m.fin) for m in mots] == [("C'est", 0.6, 0.8), ("incroyable", 1.0, 1.6)]


def test_temps_toujours_croissants():
    script = mots_du_script("un deux trois quatre cinq")
    transcrits = _transcrits(("un", 0.0, 0.3), ("trois", 0.3, 0.3), ("cinq", 0.3, 0.6))
    mots = aligner(script, transcrits)
    assert len(mots) == 5
    for precedent, mot in zip(mots, mots[1:]):
        assert mot.debut >= precedent.fin and mot.fin > mot.debut


def test_rien_a_aligner():
    assert aligner(["Bonjour"], []) == []
    assert aligner([], _transcrits(("bonjour", 0.0, 0.5))) == []
