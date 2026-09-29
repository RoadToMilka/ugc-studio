"""Tableau des capacités (§3.4) : seuls les modèles compatibles sont proposés."""

from ugc_studio.fournisseurs.capacites import Capacite, deviner_capacites, modele_connu, modeles_pour


def test_modeles_du_cahier_des_charges():
    tts = modele_connu("gemini-3.8-flash-tts")
    assert Capacite.TTS in tts.capacites and Capacite.TTS_BALISES in tts.capacites
    assert str(tts.prix_entree) == "0.50" and str(tts.prix_sortie) == "9.00"
    lite = modele_connu("gemini-3.8-flash-lite-tts")
    assert str(lite.prix_sortie) == "6.00"
    stt = modele_connu("gemini-3.5-transcribe")
    assert Capacite.STT_MOTS_HORODATES in stt.capacites
    assert stt.prix_entree is None  # prix à renseigner


def test_capacites_devinees_pour_un_nouveau_modele():
    assert Capacite.TTS in deviner_capacites("gemini-3.9-flash-tts")
    assert Capacite.STT in deviner_capacites("gemini-4-transcribe")
    assert deviner_capacites("gemini-3.5-flash") == frozenset()


def test_croisement_cles_et_taches():
    disponibles = {"gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-3.5-transcribe", "gemini-3.5-flash"}
    voix = modeles_pour({Capacite.TTS}, disponibles)
    assert [c.identifiant for c in voix] == ["gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts"]
    assert all(c.compatible for c in voix)


def test_modele_stt_sans_mots_horodates_marque_incompatible():
    disponibles = {"gemini-3.5-transcribe", "vieux-transcribe-sans-mots"}
    # Modèle inventé pour le test : on lui retire l'horodatage par mot.
    choix = modeles_pour({Capacite.STT, Capacite.STT_MOTS_HORODATES, Capacite.STT_VOCABULAIRE}, disponibles)
    par_id = {c.identifiant: c for c in choix}
    assert par_id["gemini-3.5-transcribe"].compatible
    assert not par_id["vieux-transcribe-sans-mots"].compatible  # vocabulaire non deviné
    assert choix[0].identifiant == "gemini-3.5-transcribe"  # les compatibles d'abord


def test_raison_incompatibilite_animation(monkeypatch):
    from ugc_studio.fournisseurs import capacites

    monkeypatch.setattr(capacites, "deviner_capacites", lambda _i: frozenset({Capacite.STT}))
    (choix,) = capacites.modeles_pour({Capacite.STT, Capacite.STT_MOTS_HORODATES}, {"x-transcribe"})
    assert not choix.compatible
    assert "animation" in choix.raison
