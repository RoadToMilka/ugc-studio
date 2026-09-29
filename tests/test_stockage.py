"""Fichiers JSON : écriture sûre et fichiers abîmés mis de côté."""

from ugc_studio.preferences import Preferences
from ugc_studio.stockage import ecrire_json, lire_json


def test_aller_retour_avec_accents(tmp_path):
    chemin = tmp_path / "styles.json"
    donnees = {"nom": "Témoignage chaleureux", "prix": [0.5, 9.0]}
    ecrire_json(chemin, donnees)
    assert lire_json(chemin, None) == donnees
    assert "Témoignage" in chemin.read_text(encoding="utf-8")  # lisible, pas « é »


def test_fichier_absent(tmp_path):
    assert lire_json(tmp_path / "absent.json", {"defaut": True}) == {"defaut": True}


def test_fichier_illisible_mis_de_cote(tmp_path):
    chemin = tmp_path / "prix.json"
    chemin.write_text("{ ceci n'est pas du JSON", encoding="utf-8")
    assert lire_json(chemin, {}) == {}
    assert not chemin.exists()
    copies = list(tmp_path.glob("prix.json.illisible-*"))
    assert len(copies) == 1
    assert copies[0].read_text(encoding="utf-8").startswith("{ ceci")


def test_pas_de_fichier_temporaire_restant(tmp_path):
    ecrire_json(tmp_path / "a.json", [1, 2, 3])
    assert [f.name for f in tmp_path.iterdir()] == ["a.json"]


def test_preferences(tmp_path):
    chemin = tmp_path / "preferences.json"
    preferences = Preferences(chemin)
    assert preferences.lire("module", "voix") == "voix"
    preferences.ecrire("module", "reglages")
    preferences.enregistrer()
    assert Preferences(chemin).lire("module") == "reglages"
