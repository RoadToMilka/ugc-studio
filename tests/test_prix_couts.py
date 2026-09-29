"""Catalogue des prix (§4.2), taux de change et suivi des coûts (§4.3)."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ugc_studio.couts import JournalCouts, filtrer, totaux
from ugc_studio.prix import TAUX_PAR_DEFAUT, CataloguePrix, analyser_taux_bce, lire_decimal


@pytest.fixture
def catalogue(tmp_path):
    return CataloguePrix(tmp_path / "prix.json")


def test_prix_par_defaut(catalogue):
    prix = catalogue.prix("gemini-3.8-flash-tts")
    assert (prix.entree, prix.sortie, prix.personnalise) == (Decimal("0.50"), Decimal("9.00"), False)
    assert catalogue.prix("gemini-3.5-transcribe").sortie == Decimal("12.00")
    assert catalogue.taux_usd_eur == TAUX_PAR_DEFAUT


def test_calcul_du_cout(catalogue):
    catalogue.definir_taux(Decimal("0.90"))
    # 1 000 tokens de texte à 0,50 $/M + 20 000 tokens audio à 9 $/M = 0,1805 $ → × 0,90 = 0,16245 €
    assert catalogue.cout_eur("gemini-3.8-flash-tts", 1_000, 20_000) == Decimal("0.16245")


def test_le_prix_du_jour_de_l_appel_est_applique(catalogue):
    catalogue.definir_taux(Decimal("1"))
    avant = catalogue.cout_eur("gemini-3.8-flash-tts", 0, 1_000_000, le=date(2026, 12, 31))
    apres = catalogue.cout_eur("gemini-3.8-flash-tts", 0, 1_000_000, le=date(2027, 1, 1))
    assert (avant, apres) == (Decimal("9.00"), Decimal("18.00"))
    prochain = catalogue.prochain_tarif_google("gemini-3.8-flash-tts")
    assert (prochain.depuis, prochain.sortie) == (date(2027, 1, 1), Decimal("18.00"))


def test_prix_inconnu(catalogue):
    assert catalogue.cout_eur("modele-sans-prix", 1000, 50) is None
    assert catalogue.cout_eur("modele-sans-prix", 0, 0) == 0  # rien consommé : gratuit


def test_prix_modifie_puis_retabli(tmp_path, catalogue):
    catalogue.definir_prix("gemini-3.8-flash-tts", Decimal("0.60"), Decimal("10.00"))
    recharge = CataloguePrix(tmp_path / "prix.json")
    assert recharge.prix("gemini-3.8-flash-tts").sortie == Decimal("10.00")
    assert recharge.prix("gemini-3.8-flash-tts").personnalise
    recharge.retablir_defauts()
    assert recharge.prix("gemini-3.8-flash-tts").sortie == Decimal("9.00")


def test_changement_google_posterieur_l_emporte_sur_le_prix_saisi(catalogue):
    catalogue.definir_prix("gemini-3.8-flash-tts", Decimal("0.60"), Decimal("10.00"))  # saisi le 01/10/2026
    assert catalogue.prix("gemini-3.8-flash-tts", le=date(2026, 12, 31)).sortie == Decimal("10.00")
    en_2027 = catalogue.prix("gemini-3.8-flash-tts", le=date(2027, 1, 1))
    assert (en_2027.sortie, en_2027.personnalise) == (Decimal("18.00"), False)


def test_prix_identique_au_catalogue_non_retenu(catalogue):
    catalogue.definir_prix("gemini-3.8-flash-tts", Decimal("0.5"), Decimal("9"))
    assert not catalogue.prix("gemini-3.8-flash-tts").personnalise


def test_prix_saisi_identique_au_nouveau_tarif_n_est_pas_personnalise(tmp_path):
    # Ex. prix de Transcribe saisi à la main en v0.2 (il n'était pas encore dans le catalogue).
    (tmp_path / "prix.json").write_text(
        '{"version_format": 1, "modeles": {"gemini-3.5-transcribe": {"entree": "2", "sortie": "12"}}}',
        encoding="utf-8",
    )
    assert not CataloguePrix(tmp_path / "prix.json").prix("gemini-3.5-transcribe").personnalise


def test_modeles_listes(catalogue):
    principaux = catalogue.identifiants()
    assert principaux[:3] == ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-3.5-transcribe"]
    assert "gemini-2.5-pro-preview-tts" not in principaux  # ancienne génération : seulement si accessible
    avec_cle = catalogue.identifiants({"gemini-2.5-pro-preview-tts", "gemini-4-flash-tts"})
    assert avec_cle[-2:] == ["gemini-2.5-pro-preview-tts", "gemini-4-flash-tts"]


def test_cout_d_une_minute(catalogue):
    catalogue.definir_taux(Decimal("1"))
    # 250 tokens de texte à 0,50 $/M + 1 500 tokens audio à 9 $/M = 0,013625 $
    assert catalogue.cout_reference_eur("gemini-3.8-flash-tts") == Decimal("0.013625")
    hausse = catalogue.prochain_tarif_google("gemini-3.8-flash-tts")
    assert catalogue.cout_reference_eur("gemini-3.8-flash-tts", hausse) == Decimal("0.02725")
    assert catalogue.cout_reference_eur("modele-sans-prix") is None


def test_lire_decimal():
    assert lire_decimal("0,50") == Decimal("0.50")
    assert lire_decimal(" 9 ") == Decimal("9")
    assert lire_decimal("") is None
    with pytest.raises(ValueError):
        lire_decimal("-1")
    with pytest.raises(ValueError):
        lire_decimal("abc")


def test_taux_bce():
    xml = (
        "<gesmes:Envelope><Cube><Cube time='2026-09-28'>"
        "<Cube currency='USD' rate='1.1650'/><Cube currency='JPY' rate='170.10'/>"
        "</Cube></Cube></gesmes:Envelope>"
    )
    taux, jour = analyser_taux_bce(xml)
    assert taux == Decimal("0.8584")  # 1 / 1,1650
    assert jour == "2026-09-28"


def test_journal_des_couts(tmp_path, catalogue):
    couts = JournalCouts(tmp_path / "couts", catalogue)
    notifications = []
    couts.abonner(notifications.append)
    appel = couts.enregistrer("google", "gemini-3.8-flash-tts", "voix", 1_000, 20_000, projet="Sérum")
    assert appel.cout_eur == catalogue.cout_eur("gemini-3.8-flash-tts", 1_000, 20_000)
    assert couts.cout_session == appel.cout_eur
    assert notifications == [appel]
    fichiers = list((tmp_path / "couts").glob("*.jsonl"))
    assert len(fichiers) == 1
    relu = JournalCouts(tmp_path / "couts", catalogue).lire()
    assert relu == [appel]


def test_appel_sans_prix_compte_a_part(tmp_path, catalogue):
    couts = JournalCouts(tmp_path / "couts", catalogue)
    couts.enregistrer("google", "modele-sans-prix", "transcription", 500, 100)
    total = totaux(couts.lire())
    assert total.nombre == 1 and total.sans_prix == 1 and total.cout_eur == 0
    assert couts.cout_session == 0


def test_appel_enregistre_au_prix_de_son_jour(tmp_path, catalogue):
    couts = JournalCouts(tmp_path / "couts", catalogue)
    zone = timezone(timedelta(hours=1))
    avant = couts.enregistrer("google", "gemini-3.8-flash-tts", "voix", 0, 1000, quand=datetime(2026, 12, 31, 23, 0, tzinfo=zone))
    apres = couts.enregistrer("google", "gemini-3.8-flash-tts", "voix", 0, 1000, quand=datetime(2027, 1, 1, 9, 0, tzinfo=zone))
    assert apres.cout_eur == 2 * avant.cout_eur  # hausse de Google au 01/01/2027


def test_filtres_et_totaux(tmp_path, catalogue):
    couts = JournalCouts(tmp_path / "couts", catalogue)
    zone = timezone(timedelta(hours=2))
    couts.enregistrer("google", "gemini-3.8-flash-tts", "voix", 100, 1000, "A", datetime(2026, 8, 31, 23, 0, tzinfo=zone))
    couts.enregistrer("google", "gemini-3.8-flash-tts", "voix", 100, 1000, "B", datetime(2026, 9, 1, 10, 0, tzinfo=zone))
    couts.enregistrer("google", "gemini-3.8-flash-lite-tts", "voix", 100, 1000, "A", datetime(2026, 9, 2, 10, 0, tzinfo=zone))
    tous = couts.lire()
    assert len(tous) == 3
    assert len(couts.lire(depuis=date(2026, 9, 1))) == 2  # le fichier d'août n'est pas relu
    assert len(filtrer(tous, projet="A")) == 2
    assert len(filtrer(tous, modele="gemini-3.8-flash-lite-tts")) == 1
    assert len(filtrer(tous, depuis=date(2026, 9, 2), jusqu_a=date(2026, 9, 2))) == 1
    total = totaux(tous)
    assert total.tokens_entree == 300 and total.tokens_sortie == 3000


def test_ligne_abimee_ignoree(tmp_path, catalogue):
    dossier = tmp_path / "couts"
    couts = JournalCouts(dossier, catalogue)
    couts.enregistrer("google", "gemini-3.8-flash-tts", "voix", 1, 1)
    fichier = next(dossier.glob("*.jsonl"))
    with open(fichier, "a", encoding="utf-8") as f:
        f.write("{ligne coupée\n")
    assert len(couts.lire()) == 1
