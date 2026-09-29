"""Connexions API (§4.1) : la clé va dans le coffre-fort, jamais dans un fichier."""

import pytest

from ugc_studio.connexions import CoffreMemoire, ErreurConnexion, GestionnaireConnexions, apercu_cle
from ugc_studio.journal import masquer

CLE = "AIzaSyD" + "x" * 28 + "4f2c"


@pytest.fixture
def coffre():
    return CoffreMemoire()


@pytest.fixture
def gestion(tmp_path, coffre):
    return GestionnaireConnexions(tmp_path / "connexions.json", coffre)


def test_apercu():
    assert apercu_cle(CLE) == "AIza…4f2c"
    assert apercu_cle("court") == "••••"


def test_ajout_cle_dans_le_coffre_pas_dans_le_fichier(gestion, coffre, tmp_path):
    connexion = gestion.ajouter("google", "Google perso", f"  {CLE}\n")
    assert connexion.par_defaut  # première clé du fournisseur
    assert connexion.apercu == "AIza…4f2c"
    assert coffre.secrets[connexion.compte_coffre] == CLE  # espaces du copier-coller retirés
    contenu = (tmp_path / "connexions.json").read_text(encoding="utf-8")
    assert CLE not in contenu
    assert "Google perso" in contenu
    assert gestion.lire_cle(connexion.identifiant) == CLE


def test_cle_masquee_dans_le_journal_une_fois_chargee(gestion):
    connexion = gestion.ajouter("google", "Perso", "cle-au-format-inhabituel-123456")
    gestion.lire_cle(connexion.identifiant)
    assert "inhabituel" not in masquer("appel avec cle-au-format-inhabituel-123456")


def test_plusieurs_cles_et_cle_par_defaut(gestion):
    a = gestion.ajouter("google", "Perso", CLE)
    b = gestion.ajouter("google", "Perso", CLE[:-1] + "9")
    assert b.nom == "Perso (2)"  # noms uniques
    assert not b.par_defaut
    gestion.definir_par_defaut(b.identifiant)
    assert gestion.connexion_par_defaut("google").identifiant == b.identifiant
    assert not gestion.connexion(a.identifiant).par_defaut


def test_suppression_de_la_cle_par_defaut(gestion, coffre):
    a = gestion.ajouter("google", "A", CLE)
    b = gestion.ajouter("google", "B", CLE[:-1] + "8")
    gestion.supprimer(a.identifiant)
    assert a.compte_coffre not in coffre.secrets
    assert gestion.connexion(b.identifiant).par_defaut


def test_renommer_et_remplacer(gestion, coffre):
    connexion = gestion.ajouter("google", "A", CLE)
    gestion.enregistrer_test(connexion.identifiant, True, "ok", ["gemini-3.8-flash-tts"])
    gestion.renommer(connexion.identifiant, "  Google pro ")
    nouvelle = "AIza" + "z" * 31 + "aaaa"
    gestion.remplacer_cle(connexion.identifiant, nouvelle)
    connexion = gestion.connexion(connexion.identifiant)
    assert connexion.nom == "Google pro"
    assert connexion.apercu == "AIza…aaaa"
    assert connexion.dernier_test is None  # la nouvelle clé doit être retestée
    assert coffre.secrets[connexion.compte_coffre] == nouvelle
    with pytest.raises(ErreurConnexion):
        gestion.renommer(connexion.identifiant, "   ")


def test_modeles_disponibles_apres_un_test_reussi(gestion):
    a = gestion.ajouter("google", "A", CLE)
    assert gestion.modeles_disponibles() == set()
    gestion.enregistrer_test(a.identifiant, True, "ok", ["gemini-3.8-flash-tts", "gemini-3.5-transcribe"])
    assert gestion.modeles_disponibles("google") == {"gemini-3.8-flash-tts", "gemini-3.5-transcribe"}
    gestion.enregistrer_test(a.identifiant, False, "refusée")
    assert gestion.modeles_disponibles() == set()


def test_rechargement_depuis_le_fichier(tmp_path, coffre):
    premiere = GestionnaireConnexions(tmp_path / "c.json", coffre)
    connexion = premiere.ajouter("google", "A", CLE)
    premiere.enregistrer_test(connexion.identifiant, True, "Clé valide", ["m1"])
    seconde = GestionnaireConnexions(tmp_path / "c.json", coffre)
    rechargee = seconde.connexion(connexion.identifiant)
    assert rechargee.dernier_test.ok and rechargee.dernier_test.message == "Clé valide"
    assert rechargee.modeles == ["m1"]


def test_cle_absente_du_coffre(gestion, coffre):
    connexion = gestion.ajouter("google", "A", CLE)
    coffre.secrets.clear()
    with pytest.raises(ErreurConnexion, match="introuvable"):
        gestion.lire_cle(connexion.identifiant)


def test_notification_des_changements(gestion):
    appels = []
    gestion.abonner(lambda: appels.append(1))
    gestion.ajouter("google", "A", CLE)
    assert appels
