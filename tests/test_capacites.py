"""Tableau des capacités (§3.4) : seuls les modèles compatibles sont proposés. Tarifs Google (§4.2)."""

from datetime import date
from decimal import Decimal

from ugc_studio.fournisseurs.capacites import (
    HAUSSE_GOOGLE_2027,
    Capacite,
    deviner_capacites,
    modele_connu,
    modeles_pour,
)


def test_modeles_du_cahier_des_charges():
    tts = modele_connu("gemini-3.8-flash-tts")
    assert Capacite.TTS in tts.capacites and Capacite.TTS_BALISES in tts.capacites
    tarif = tts.tarif(date(2026, 10, 1))
    assert (tarif.entree, tarif.sortie) == (Decimal("0.50"), Decimal("9.00"))
    lite = modele_connu("gemini-3.8-flash-lite-tts")
    assert lite.tarif(date(2026, 10, 1)).sortie == Decimal("6.00")
    stt = modele_connu("gemini-3.5-transcribe")
    assert Capacite.STT_MOTS_HORODATES in stt.capacites
    # Page des tarifs Google : 2 $ (audio) et 12 $ (texte) par million de tokens.
    assert (stt.tarif(date(2026, 10, 1)).entree, stt.tarif(date(2026, 10, 1)).sortie) == (Decimal("2.00"), Decimal("12.00"))


def test_hausse_annoncee_au_1er_janvier_2027():
    tts = modele_connu("gemini-3.8-flash-tts")
    assert tts.tarif(date(2026, 12, 31)).sortie == Decimal("9.00")
    assert tts.tarif(HAUSSE_GOOGLE_2027).sortie == Decimal("18.00")
    assert tts.prochain_tarif(date(2026, 10, 1)).depuis == HAUSSE_GOOGLE_2027
    assert tts.prochain_tarif(HAUSSE_GOOGLE_2027) is None
    assert modele_connu("gemini-3.5-transcribe").prochain_tarif(date(2026, 10, 1)) is None


def test_ordre_de_grandeur_google():
    """« 0,00225 $ pour 10 s d'audio » (3.8 Flash TTS) et « ≈ 0,005 $/min » (3.5 Transcribe)."""
    tts = modele_connu("gemini-3.8-flash-tts")
    tarif = tts.tarif(date(2026, 10, 1))
    assert tts.reference.tokens_sortie * tarif.sortie / 1_000_000 / 6 == Decimal("0.00225")
    stt = modele_connu("gemini-3.5-transcribe")
    tarif = stt.tarif(date(2026, 10, 1))
    minute = (stt.reference.tokens_entree * tarif.entree + stt.reference.tokens_sortie * tarif.sortie) / 1_000_000
    assert Decimal("0.0045") < minute < Decimal("0.0055")


def test_anciennes_voix_sans_balises_ni_voice_design():
    for identifiant in ("gemini-3.1-flash-tts-preview", "gemini-2.5-pro-preview-tts", "gemini-2.5-flash-preview-tts"):
        ancien = modele_connu(identifiant)
        assert Capacite.TTS in ancien.capacites
        assert Capacite.TTS_BALISES not in ancien.capacites and Capacite.TTS_VOICE_DESIGN not in ancien.capacites
        assert not ancien.principal


def test_modeles_live_jamais_proposes():
    assert deviner_capacites("gemini-3.5-transcribe-live") == frozenset()
    assert deviner_capacites("gemini-2.5-flash-native-audio-preview-12-2025") == frozenset()
    assert modeles_pour({Capacite.STT}, {"gemini-3.5-transcribe", "gemini-3.5-transcribe-live"})[0].identifiant == (
        "gemini-3.5-transcribe"
    )
    assert len(modeles_pour({Capacite.STT}, {"gemini-3.5-transcribe", "gemini-3.5-transcribe-live"})) == 1


def test_capacites_devinees_pour_un_nouveau_modele():
    assert Capacite.TTS in deviner_capacites("gemini-3.9-flash-tts")
    assert Capacite.STT in deviner_capacites("gemini-4-transcribe")


def test_modeles_de_texte_reconnus_d_apres_leur_nom():
    """V2 : les modèles de texte Gemini 3 et suivants servent au module Script (§2, point 11)."""
    for identifiant in ("gemini-3.5-flash", "gemini-3.8-flash-lite", "gemini-4-pro-preview"):
        capacites = deviner_capacites(identifiant)
        assert {Capacite.TEXTE, Capacite.TEXTE_STRUCTURE, Capacite.TEXTE_PAGES_WEB} <= capacites, identifiant
    for identifiant in (
        "gemini-2.5-flash",  # ancienne génération : ne comprend pas le niveau de réflexion envoyé
        "gemini-3.1-flash-image-preview",
        "gemini-embedding-001",
        "gemini-3-pro-image-preview",
        "gemini-robotics-er-1.5-preview",
        "gemini-3.5-flash-native-audio",
        "gemma-3-27b-it",
        "veo-3.1-generate-preview",
    ):
        assert deviner_capacites(identifiant) == frozenset(), identifiant


def test_modeles_de_texte_du_catalogue():
    flash = modele_connu("gemini-3.8-flash")
    assert {Capacite.TEXTE_STRUCTURE, Capacite.TEXTE_PAGES_WEB} <= flash.capacites
    assert (flash.tarif(date(2026, 10, 1)).entree, flash.tarif(date(2026, 10, 1)).sortie) == (Decimal("0.75"), Decimal("3.75"))
    assert flash.tarif(HAUSSE_GOOGLE_2027).sortie == Decimal("7.50")
    pro = modele_connu("gemini-3.1-pro-preview")
    assert pro.nom == "Gemini 3.1 Pro (aperçu)"
    assert (pro.tarif(date(2026, 10, 1)).entree, pro.tarif(date(2026, 10, 1)).sortie) == (Decimal("2.00"), Decimal("12.00"))
    # Ordre de grandeur annoncé (§10.12) : ≈ 4 à 7 centimes de dollar par script avec 3.8 Flash.
    tarif = flash.tarif(date(2026, 10, 1))
    script = (flash.reference.tokens_entree * tarif.entree + flash.reference.tokens_sortie * tarif.sortie) / 1_000_000
    assert Decimal("0.04") < script < Decimal("0.07")
    textes = modeles_pour({Capacite.TEXTE, Capacite.TEXTE_STRUCTURE}, {"gemini-3.1-pro-preview", "gemini-3.8-flash", "gemini-3.8-flash-tts"})
    assert [c.identifiant for c in textes] == ["gemini-3.8-flash", "gemini-3.1-pro-preview"]


def test_croisement_cles_et_taches():
    disponibles = {"gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-3.5-transcribe", "gemini-3.5-flash"}
    voix = modeles_pour({Capacite.TTS}, disponibles)
    # Dans l'ordre du catalogue : le modèle conseillé d'abord.
    assert [c.identifiant for c in voix] == ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"]
    assert all(c.compatible for c in voix)


def test_balises_demandees_ancien_modele_incompatible():
    choix = modeles_pour({Capacite.TTS, Capacite.TTS_BALISES}, {"gemini-3.8-flash-tts", "gemini-2.5-pro-preview-tts"})
    assert [(c.identifiant, c.compatible) for c in choix] == [
        ("gemini-3.8-flash-tts", True),
        ("gemini-2.5-pro-preview-tts", False),
    ]
    assert "Balises" in choix[1].raison


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
