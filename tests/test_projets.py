"""Projets (§3.2) : création, réouverture, prises, projets récents."""

import pytest

import json

from ugc_studio.audio import wav_depuis_pcm
from ugc_studio.projets import ErreurProjet, GestionnaireProjets, Projet, RepliqueProjet, nom_de_dossier
from ugc_studio.prononciation import Prononciation
from ugc_studio.sous_titres import ReglagesSousTitres

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
    projet.repliques = [
        RepliqueProjet([{"texte": "Salut "}, {"balise": "laugh"}], "excited", "excité"),
        RepliqueProjet([{"texte": "Le lien est en dessous."}]),
    ]
    projet.prononciations = [Prononciation("Glowzy", "Glo-zi")]
    projet.voix.voix = "Puck"
    gestion.enregistrer()

    autre = GestionnaireProjets(tmp_path / "recents.json")
    rouvert = autre.ouvrir(projet.dossier)
    assert rouvert.nom == "Sérum Glowzy" and rouvert.langue == "nl-BE"
    assert rouvert.repliques == projet.repliques
    assert rouvert.prononciations == [Prononciation("Glowzy", "Glo-zi")]
    # Script complet (sous-titres) : les répliques bout à bout.
    assert rouvert.script == [{"texte": "Salut "}, {"balise": "laugh"}, {"texte": " Le lien est en dessous."}]
    assert rouvert.voix.voix == "Puck"


def test_projet_de_l_etape_3_converti(gestion, tmp_path):
    """Format 1 : un seul script, et le style dans les réglages de voix → une seule réplique."""
    dossier = tmp_path / "Ancien"
    dossier.mkdir()
    (dossier / "projet.json").write_text(
        json.dumps(
            {
                "version_format": 1,
                "nom": "Ancien",
                "voix": {"modele": "gemini-3.8-flash-tts", "voix": "Leda", "style": "warm"},
                "script": [{"texte": "Bonjour"}],
                "prises": [],
            }
        ),
        encoding="utf-8",
    )
    projet = gestion.ouvrir(dossier)
    assert projet.repliques == [RepliqueProjet([{"texte": "Bonjour"}], "warm")]
    assert projet.voix.voix == "Leda" and projet.prononciations == []
    gestion.enregistrer()
    enregistre = json.loads((dossier / "projet.json").read_text(encoding="utf-8"))
    assert enregistre["version_format"] == Projet.VERSION_FORMAT
    assert "script" not in enregistre and "style" not in enregistre["voix"]
    assert projet.transcription is None and projet.remplacements == []
    assert projet.sous_titres == ReglagesSousTitres()  # format 4 : réglages par défaut


def test_noms_de_variantes_de_la_v1_0_0_sans_tiret(gestion, tmp_path):
    """Jusqu'à la v1.0.0, une variante s'appelait « Prise 3 — variante B » : à l'ouverture, elle
    prend la forme actuelle, « Prise 3 (variante B) ». Un nom choisi à la main ne change jamais."""
    dossier = tmp_path / "Ancien"
    dossier.mkdir()
    prises = [
        dict(identifiant="a", nom="Prise 3 — variante B", fichier="prises/prise-003.wav", date="", **_infos()),
        dict(identifiant="b", nom="Mon essai — final", fichier="prises/prise-004.wav", date="", **_infos()),
    ]
    (dossier / "projet.json").write_text(
        json.dumps({"version_format": 4, "nom": "Ancien", "prises": prises}), encoding="utf-8"
    )
    projet = gestion.ouvrir(dossier)
    assert [p.nom for p in projet.prises] == ["Prise 3 (variante B)", "Mon essai — final"]


def test_reglages_des_sous_titres_enregistres(gestion, tmp_path):
    projet = gestion.creer("Sous-titres", tmp_path)
    projet.sous_titres.majuscules, projet.sous_titres.lignes_max = True, 1
    gestion.enregistrer()
    rouvert = GestionnaireProjets(tmp_path / "recents.json").ouvrir(projet.dossier)
    assert rouvert.sous_titres.majuscules and rouvert.sous_titres.lignes_max == 1


def test_nouveau_projet_avec_une_replique_vide(gestion, tmp_path):
    projet = gestion.creer("Vide", tmp_path)
    assert projet.repliques == [RepliqueProjet()]
    assert projet.script == []


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
    gestion.creer("B", tmp_path)
    gestion.ouvrir(a.dossier)
    assert [nom for nom, _ in gestion.recents()] == ["A", "B"]
    assert gestion.dernier_projet() == a.dossier


def test_notification_du_projet_ouvert(gestion, tmp_path):
    vus = []
    gestion.abonner(vus.append)
    projet = gestion.creer("A", tmp_path)
    gestion.fermer()
    assert vus == [projet, None]
