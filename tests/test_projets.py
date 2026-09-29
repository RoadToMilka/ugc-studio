"""Projets (§3.2) : création, réouverture, prises, projets récents."""

import pytest

from ugc_studio.audio import wav_depuis_pcm
from ugc_studio.projets import ErreurProjet, GestionnaireProjets, nom_de_dossier

WAV = wav_depuis_pcm(b"\x00\x00" * 24_000)  # 1 seconde de silence


@pytest.fixture
def gestion(tmp_path):
    return GestionnaireProjets(tmp_path / "recents.json")


def _infos():
    return dict(modele="m", voix="Kore", style="", texte_api="t", script=[{"texte": "t"}], duree_s=1.0)


def test_nom_de_dossier_valide_sous_windows():
    assert nom_de_dossier('Sérum: "Glowzy"?') == "Sérum Glowzy"
    assert nom_de_dossier("CON") == "Projet CON"
    assert nom_de_dossier("  ...  ") == "Projet"


def test_creer_puis_rouvrir(gestion, tmp_path):
    projet = gestion.creer("Sérum Glowzy", tmp_path, "nl-BE")
    assert (projet.dossier / "projet.json").exists()
    assert (projet.dossier / "prises").is_dir()
    projet.script = [{"texte": "Salut "}, {"balise": "laugh"}]
    projet.voix.voix = "Puck"
    gestion.enregistrer()

    autre = GestionnaireProjets(tmp_path / "recents.json")
    rouvert = autre.ouvrir(projet.dossier)
    assert rouvert.nom == "Sérum Glowzy" and rouvert.langue == "nl-BE"
    assert rouvert.script == [{"texte": "Salut "}, {"balise": "laugh"}]
    assert rouvert.voix.voix == "Puck"


def test_deux_projets_du_meme_nom(gestion, tmp_path):
    a = gestion.creer("Test", tmp_path)
    b = gestion.creer("Test", tmp_path)
    assert a.dossier != b.dossier
    assert b.dossier.name == "Test (2)"


def test_nom_vide_refuse(gestion, tmp_path):
    with pytest.raises(ErreurProjet):
        gestion.creer("   ", tmp_path)


def test_dossier_sans_projet(gestion, tmp_path):
    with pytest.raises(ErreurProjet, match="projet.json"):
        gestion.ouvrir(tmp_path)


def test_prises(gestion, tmp_path):
    projet = gestion.creer("P", tmp_path)
    p1 = gestion.ajouter_prise(WAV, **_infos())
    p2 = gestion.ajouter_prise(WAV, **_infos())
    assert (p1.nom, p2.nom) == ("Prise 1", "Prise 2")
    assert (projet.dossier / p2.fichier).read_bytes() == WAV
    gestion.modifier_prise(p1.identifiant, nom="Meilleure", note=5)
    gestion.supprimer_prise(p2.identifiant)
    assert not (projet.dossier / p2.fichier).exists()
    p3 = gestion.ajouter_prise(WAV, **_infos())
    assert p3.fichier.endswith("prise-002.wav")  # numéro libéré réutilisable, jamais de doublon
    rouvert = GestionnaireProjets(tmp_path / "recents.json").ouvrir(projet.dossier)
    assert [p.nom for p in rouvert.prises] == ["Meilleure", "Prise 2"]
    assert rouvert.prises[0].note == 5


def test_projets_recents(gestion, tmp_path):
    a = gestion.creer("A", tmp_path)
    b = gestion.creer("B", tmp_path)
    gestion.ouvrir(a.dossier)
    assert [nom for nom, _ in gestion.recents()] == ["A", "B"]
    assert gestion.dernier_projet() == a.dossier


def test_notification_du_projet_ouvert(gestion, tmp_path):
    vus = []
    gestion.abonner(vus.append)
    projet = gestion.creer("A", tmp_path)
    gestion.fermer()
    assert vus == [projet, None]
